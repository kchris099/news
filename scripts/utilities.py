from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx

LOGGER = logging.getLogger(__name__)
SAFE_SCHEMES = {"http", "https"}
NON_THUMBNAIL_EXTENSIONS = {
    ".3gp", ".avi", ".m3u8", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg",
    ".mpg", ".ogg", ".ogv", ".svg", ".gif", ".ts", ".wav", ".webm", ".wmv",
}
VIDEO_HOSTS = {"youtube.com", "youtu.be", "vimeo.com", "dailymotion.com"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime | None = None) -> str:
    value = value or utc_now()
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def local_date_keys(time_zone: str, days: int, now: datetime | None = None) -> list[str]:
    current = (now or utc_now()).astimezone(ZoneInfo(time_zone)).date()
    return [(current - timedelta(days=offset)).isoformat() for offset in range(days)]


def local_day_window(date_key: str, time_zone: str) -> tuple[datetime, datetime]:
    local_date = date.fromisoformat(date_key)
    zone = ZoneInfo(time_zone)
    start = datetime.combine(local_date, time.min, zone)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def date_key_for_timestamp(value: datetime, time_zone: str) -> str:
    return value.astimezone(ZoneInfo(time_zone)).date().isoformat()


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def stable_hash(*parts: str, length: int = 24) -> str:
    data = "\x1f".join(part or "" for part in parts).encode("utf-8", errors="ignore")
    return hashlib.sha256(data).hexdigest()[:length]


def safe_url(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        split = urlsplit(value.strip())
    except ValueError:
        return None
    if split.scheme.lower() not in SAFE_SCHEMES or not split.netloc:
        return None
    host = split.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return None
    return urlunsplit((split.scheme.lower(), split.netloc, split.path or "/", split.query, ""))


def safe_image_url(value: str | None) -> str | None:
    """Return an HTTPS URL suitable for a static article thumbnail."""
    valid = safe_url(value)
    if not valid or urlsplit(valid).scheme != "https":
        return None
    split = urlsplit(valid)
    path = split.path.lower()
    if any(path.endswith(extension) for extension in NON_THUMBNAIL_EXTENSIONS):
        return None
    host = (split.hostname or "").lower().removeprefix("www.")
    if host in VIDEO_HOSTS or any(host.endswith(f".{domain}") for domain in VIDEO_HOSTS):
        return None
    return valid


def normalize_url(value: str | None, tracking_parameters: Iterable[str]) -> str | None:
    valid = safe_url(value)
    if not valid:
        return None
    split = urlsplit(valid)
    blocked = {item.lower() for item in tracking_parameters}
    query = [
        (key, val)
        for key, val in parse_qsl(split.query, keep_blank_values=True)
        if key.lower() not in blocked and not key.lower().startswith("utm_")
    ]
    host = (split.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = f":{split.port}" if split.port else ""
    path = re.sub(r"/{2,}", "/", split.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((split.scheme.lower(), host + port, path, urlencode(sorted(query)), ""))


def source_domain(value: str | None) -> str | None:
    valid = safe_url(value)
    if not valid:
        return None
    host = (urlsplit(valid).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def compact_error(exc: Exception, max_length: int = 180) -> str:
    message = re.sub(r"\s+", " ", str(exc)).strip()
    return message[:max_length] if message else exc.__class__.__name__


@dataclass(slots=True)
class FetchResult:
    url: str
    content: bytes
    content_type: str
    elapsed_ms: int
    etag: str | None
    last_modified: str | None
    status_code: int


class AsyncFetcher:
    def __init__(self, settings: dict[str, Any], cache_headers: dict[str, Any] | None = None) -> None:
        self.timeout = float(settings.get("requestTimeoutSeconds", 18))
        self.max_bytes = int(settings.get("maxResponseBytes", 5_000_000))
        self.attempts = int(settings.get("retryAttempts", 3))
        self.base_delay = float(settings.get("retryBaseSeconds", 1.0))
        self.user_agent = settings.get("userAgent", "Worldline/1.0")
        self.cache_headers = cache_headers if cache_headers is not None else {}
        limits = httpx.Limits(max_connections=int(settings.get("maxConcurrency", 8)), max_keepalive_connections=6)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=limits,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, application/json;q=0.9, */*;q=0.5"},
        )

    async def __aenter__(self) -> "AsyncFetcher":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.client.aclose()

    async def get(
        self,
        url: str,
        expected: tuple[str, ...] = (),
        max_bytes: int | None = None,
        retry_attempts: int | None = None,
    ) -> FetchResult:
        safe = safe_url(url)
        if not safe:
            raise ValueError("Unsafe or invalid request URL")
        response_limit = max_bytes or self.max_bytes
        headers: dict[str, str] = {}
        cached = self.cache_headers.get(safe, {})
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("lastModified"):
            headers["If-Modified-Since"] = cached["lastModified"]

        last_error: Exception | None = None
        attempts = max(1, int(retry_attempts or self.attempts))
        for attempt in range(attempts):
            try:
                started = asyncio.get_running_loop().time()
                async with self.client.stream("GET", safe, headers=headers) as response:
                    if response.status_code == 304:
                        elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000)
                        return FetchResult(
                            url=str(response.url), content=b"", content_type=response.headers.get("content-type", ""),
                            elapsed_ms=elapsed_ms, etag=response.headers.get("etag") or cached.get("etag"),
                            last_modified=response.headers.get("last-modified") or cached.get("lastModified"), status_code=304,
                        )
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > response_limit:
                        raise ValueError("Response exceeded configured size limit")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > response_limit:
                            raise ValueError("Response exceeded configured size limit")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    content_type = response.headers.get("content-type", "").lower()
                    if expected and not any(token in content_type for token in expected):
                        if not content.lstrip().startswith((b"<", b"{", b"[")):
                            raise ValueError(f"Unexpected response type: {content_type or 'unknown'}")
                    elapsed_ms = round((asyncio.get_running_loop().time() - started) * 1000)
                    result = FetchResult(
                        url=str(response.url), content=content, content_type=content_type,
                        elapsed_ms=elapsed_ms, etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"), status_code=response.status_code,
                    )
                    self.cache_headers[safe] = {
                        "etag": result.etag,
                        "lastModified": result.last_modified,
                        "checkedAt": iso_z(),
                    }
                    return result
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError, RuntimeError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in {408, 429, 500, 502, 503, 504}
                if attempt + 1 >= attempts or not retryable:
                    break
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.25)
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    retry_after = exc.response.headers.get("retry-after")
                    try:
                        delay = max(delay, float(retry_after)) if retry_after else max(delay, 5.0)
                    except ValueError:
                        delay = max(delay, 5.0)
                await asyncio.sleep(delay)
        raise RuntimeError(compact_error(last_error or RuntimeError("Request failed")))
