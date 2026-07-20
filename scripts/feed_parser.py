from __future__ import annotations

import asyncio
import calendar
import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import feedparser

from .utilities import AsyncFetcher, iso_z, safe_image_url


class _PageImageParser(HTMLParser):
    _IMAGE_META_NAMES = {
        "og:image", "og:image:url", "og:image:secure_url",
        "twitter:image", "twitter:image:src", "thumbnail",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            name = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            if name in self._IMAGE_META_NAMES and values.get("content"):
                self.candidates.append(values["content"])
        elif tag.lower() == "link" and "image_src" in values.get("rel", "").lower().split():
            if values.get("href"):
                self.candidates.append(values["href"])


def extract_page_image(content: bytes, page_url: str) -> str | None:
    parser = _PageImageParser()
    try:
        parser.feed(content.decode("utf-8", errors="replace"))
    except (ValueError, TypeError):
        return None
    for candidate in parser.candidates:
        image_url = safe_image_url(urljoin(page_url, html.unescape(candidate).strip()))
        if image_url:
            return image_url
    return None


async def enrich_missing_images(
    fetcher: AsyncFetcher,
    articles: list[dict[str, Any]],
    image_cache: dict[str, Any],
    limit: int = 24,
) -> None:
    candidates = [
        article for article in articles
        if not article.get("imageUrl") and article.get("dataSource") == "publisher-rss"
        and article.get("url") and "news.google.com" not in str(article["url"]).lower()
    ]
    candidates = sorted(candidates, key=lambda item: str(item.get("publishedAt") or ""), reverse=True)[:max(0, limit)]

    async def enrich(article: dict[str, Any]) -> None:
        page_url = str(article["url"])
        cached = image_cache.get(page_url) or {}
        cached_image = safe_image_url(cached.get("imageUrl"))
        if cached_image:
            article["imageUrl"] = cached_image
            return
        try:
            response = await asyncio.wait_for(
                fetcher.get(
                    page_url,
                    expected=("html", "xhtml", "text/plain"),
                    max_bytes=max(fetcher.max_bytes, 8_000_000),
                    retry_attempts=1,
                ),
                timeout=8.0,
            )
            if response.status_code == 304:
                return
            image_url = extract_page_image(response.content, page_url)
        except Exception:
            return
        if image_url:
            image_cache[page_url] = {"imageUrl": image_url, "checkedAt": iso_z()}
            article["imageUrl"] = image_url

    await asyncio.gather(*(enrich(article) for article in candidates))


def _media_image_url(media: Any) -> str | None:
    if not isinstance(media, dict):
        return None
    url = media.get("url") or media.get("href")
    if not url:
        return None
    medium = str(media.get("medium", "")).lower()
    media_type = str(media.get("type", "")).lower()
    if medium in {"audio", "video"} or media_type.startswith(("audio/", "video/")):
        return None
    return str(url) if safe_image_url(str(url)) else None


def _html_image(summary: str) -> str | None:
    for tag in re.findall(r"<img\b[^>]*>", summary, flags=re.I):
        attributes = {
            key.lower(): value
            for key, value in re.findall(r"([\w:-]+)\s*=\s*[\"'](.*?)[\"']", tag, flags=re.I)
        }
        for name in ("src", "data-src", "data-original", "data-image"):
            value = attributes.get(name)
            if value and not value.startswith("data:"):
                return html.unescape(value)
        srcset = attributes.get("srcset") or attributes.get("data-srcset")
        if srcset:
            values = [item.strip().split()[0] for item in srcset.split(",") if item.strip()]
            if values:
                return html.unescape(values[-1])
    return None


def _entry_image(entry: Any) -> str | None:
    for media in entry.get("media_content", []) or []:
        url = _media_image_url(media)
        width = int(media.get("width", 0) or 0)
        height = int(media.get("height", 0) or 0)
        if url and (not width or width >= 120) and (not height or height >= 90):
            return url
    for thumb in entry.get("media_thumbnail", []) or []:
        url = _media_image_url(thumb)
        if url:
            return url
    for enclosure in entry.get("enclosures", []) or []:
        media_type = str(enclosure.get("type", "")).lower()
        url = _media_image_url(enclosure)
        if url and (media_type.startswith("image/") or not media_type):
            return url
    image = entry.get("image") or {}
    url = _media_image_url(image)
    if url:
        return url
    html_values = [entry.get("summary"), entry.get("description")]
    html_values.extend(item.get("value") for item in entry.get("content", []) or [] if isinstance(item, dict))
    for value in html_values:
        if value:
            url = _html_image(str(value))
            if url:
                return url
    return None


def _published(entry: Any) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed") or entry.get("created_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return entry.get("published") or entry.get("updated") or entry.get("created")


def parse_feed_bytes(content: bytes, source: dict[str, Any], edition_country: str, data_source: str = "publisher-rss") -> list[dict[str, Any]]:
    parsed = feedparser.parse(content, resolve_relative_uris=True, sanitize_html=False)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Malformed feed: {parsed.bozo_exception}")
    retrieved = iso_z()
    output: list[dict[str, Any]] = []
    for entry in parsed.entries:
        title = str(entry.get("title", "")).strip()
        link = entry.get("link")
        if not title or not link:
            continue
        entry_source = entry.get("source", {}) or {}
        source_name = source.get("name") or entry_source.get("title") or parsed.feed.get("title") or "Unknown source"
        output.append({
            "title": title,
            "url": link,
            "publisherArticleId": entry.get("id") or entry.get("guid"),
            "description": entry.get("summary") or entry.get("description"),
            "imageUrl": _entry_image(entry),
            "publishedAt": _published(entry),
            "sourceName": source_name,
            "sourceId": source.get("id"),
            "sourceCountry": source.get("sourceCountry") or edition_country,
            "editionCountry": edition_country,
            "language": source.get("language") or parsed.feed.get("language"),
            "categoryHint": source.get("categoryHint"),
            "sourceQuality": float(source.get("qualityWeight", 1.0)),
            "publisherUrl": entry_source.get("href") or entry_source.get("url"),
            "retrievedAt": retrieved,
            "dataSource": data_source,
        })
    if parsed.bozo and not output:
        raise ValueError(f"Malformed feed: {parsed.bozo_exception}")
    return output


async def fetch_feed(fetcher: AsyncFetcher, source: dict[str, Any], edition_country: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    attempted = iso_z()
    try:
        response = await fetcher.get(
            source["url"],
            expected=("xml", "rss", "atom", "text/plain"),
            retry_attempts=1,
        )
        data_source = str(source.get("dataSource") or "publisher-rss")
        articles = [] if response.status_code == 304 else parse_feed_bytes(response.content, source, edition_country, data_source)
        health = {
            "sourceId": source.get("id"), "sourceName": source.get("name"), "status": "success",
            "lastAttemptAt": attempted, "lastSuccessAt": iso_z(), "articlesRetrieved": len(articles),
            "responseTimeMs": response.elapsed_ms, "errorType": None, "errorMessage": None,
        }
        return articles, health
    except Exception as exc:
        return [], {
            "sourceId": source.get("id"), "sourceName": source.get("name"), "status": "failed",
            "lastAttemptAt": attempted, "lastSuccessAt": None, "articlesRetrieved": 0,
            "responseTimeMs": None, "errorType": exc.__class__.__name__, "errorMessage": str(exc)[:180],
        }
