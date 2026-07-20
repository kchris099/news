from __future__ import annotations

import calendar
import html
import re
from datetime import datetime, timezone
from typing import Any

import feedparser

from .utilities import AsyncFetcher, iso_z


def _entry_image(entry: Any) -> str | None:
    for media in entry.get("media_content", []) or []:
        url = media.get("url")
        medium = str(media.get("medium", "")).lower()
        width = int(media.get("width", 0) or 0)
        height = int(media.get("height", 0) or 0)
        if url and medium != "audio" and (not width or width >= 120) and (not height or height >= 90):
            return url
    for thumb in entry.get("media_thumbnail", []) or []:
        if thumb.get("url"):
            return thumb["url"]
    for enclosure in entry.get("enclosures", []) or []:
        if str(enclosure.get("type", "")).startswith("image/") and enclosure.get("href"):
            return enclosure["href"]
    summary = entry.get("summary") or entry.get("description") or ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', summary, flags=re.I)
    return html.unescape(match.group(1)) if match else None


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
        source_name = source.get("name") or entry.get("source", {}).get("title") or parsed.feed.get("title") or "Unknown source"
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
            "retrievedAt": retrieved,
            "dataSource": data_source,
        })
    if parsed.bozo and not output:
        raise ValueError(f"Malformed feed: {parsed.bozo_exception}")
    return output


async def fetch_feed(fetcher: AsyncFetcher, source: dict[str, Any], edition_country: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    attempted = iso_z()
    try:
        response = await fetcher.get(source["url"], expected=("xml", "rss", "atom", "text/plain"))
        articles = [] if response.status_code == 304 else parse_feed_bytes(response.content, source, edition_country)
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
