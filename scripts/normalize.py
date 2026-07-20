from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import bleach
from dateutil import parser as date_parser

from .utilities import normalize_url, safe_image_url, safe_url, source_domain, stable_hash

_WHITESPACE = re.compile(r"\s+")


def clean_text(value: Any, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = bleach.clean(str(value), tags=[], attributes={}, strip=True)
    text = html.unescape(text)
    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        return None
    return text[:max_length].rstrip() if max_length and len(text) > max_length else text


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return _WHITESPACE.sub(" ", text).strip()


def parse_publication_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = date_parser.parse(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if parsed.year < 1990 or parsed > now.replace(microsecond=0) + timedelta(days=2):
        return None
    return parsed


def normalize_article(raw: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    title = clean_text(raw.get("title"), 500)
    url = safe_url(raw.get("url"))
    published = parse_publication_date(raw.get("publishedAt"))
    source_name = clean_text(raw.get("sourceName"), 160)
    if not title or not url or not published or not source_name:
        return None
    canonical = normalize_url(url, settings.get("trackingParameters", []))
    if not canonical:
        return None
    normalized_title = normalize_title(title)
    article_id = stable_hash(
        raw.get("publisherArticleId") or "",
        canonical,
        normalized_title,
        source_name.casefold(),
    )
    image_url = safe_image_url(raw.get("imageUrl"))
    data_source = clean_text(raw.get("dataSource"), 40) or "publisher-rss"
    article_domain = source_domain(raw.get("publisherUrl")) or source_domain(canonical)
    article = {
        "id": article_id,
        "title": title,
        "translatedTitle": None,
        "description": clean_text(raw.get("description"), 500),
        "url": url,
        "canonicalUrl": canonical,
        "sourceName": source_name,
        "sourceDomain": article_domain,
        "sourceCountry": clean_text(raw.get("sourceCountry"), 8),
        "editionCountry": clean_text(raw.get("editionCountry"), 8),
        "coverageCountries": [],
        "language": clean_text(raw.get("language"), 20),
        "publishedAt": published.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "imageUrl": image_url,
        "imageAlt": None,
        "category": "General",
        "topics": [],
        "retrievedAt": clean_text(raw.get("retrievedAt"), 40),
        "dataSources": [data_source],
        "clusterId": None,
        "translationProvider": None,
        "translationGeneratedAt": None,
        "sourceQuality": float(raw.get("sourceQuality", 1.0)),
        "categoryHint": clean_text(raw.get("categoryHint"), 40),
        "normalizedTitle": normalized_title,
    }
    return article
