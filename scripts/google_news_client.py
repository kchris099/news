from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from .feed_parser import parse_feed_bytes
from .utilities import AsyncFetcher, iso_z


def top_stories_url(country: dict[str, Any], providers: dict[str, Any]) -> str:
    base = providers["googleNews"].get("topStoriesBase", "https://news.google.com/rss")
    params = {
        "hl": country["googleNewsLocale"],
        "gl": country["googleNewsCountry"],
        "ceid": f'{country["googleNewsCountry"]}:{country["googleNewsLanguage"]}',
    }
    return f"{base}?{urlencode(params)}"


def date_search_url(country: dict[str, Any], date_key: str, providers: dict[str, Any]) -> str:
    start = date.fromisoformat(date_key)
    end = start + timedelta(days=1)
    country_name = country["name"]
    query = f'("{country_name}" OR sourcecountry:{country["googleNewsCountry"]}) after:{start.isoformat()} before:{end.isoformat()}'
    base = providers["googleNews"].get("searchBase", "https://news.google.com/rss/search")
    params = {
        "q": query,
        "hl": country["googleNewsLocale"],
        "gl": country["googleNewsCountry"],
        "ceid": f'{country["googleNewsCountry"]}:{country["googleNewsLanguage"]}',
    }
    return f"{base}?{urlencode(params)}"


async def fetch_google_news(fetcher: AsyncFetcher, country: dict[str, Any], providers: dict[str, Any], date_key: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_id = f'google-news-{country["code"]}' + (f'-{date_key}' if date_key else '-top')
    source = {
        "id": source_id, "name": "Google News", "language": country["primaryLanguage"],
        "qualityWeight": 0.82, "sourceCountry": country["code"],
    }
    url = date_search_url(country, date_key, providers) if date_key else top_stories_url(country, providers)
    attempted = iso_z()
    try:
        response = await fetcher.get(url, expected=("xml", "rss", "text/plain"))
        articles = [] if response.status_code == 304 else parse_feed_bytes(response.content, source, country["code"], "google-news")
        for article in articles:
            article["sourceName"] = article.get("sourceName") or "Google News"
        return articles, {
            "sourceId": source_id, "sourceName": "Google News", "status": "success",
            "lastAttemptAt": attempted, "lastSuccessAt": iso_z(), "articlesRetrieved": len(articles),
            "responseTimeMs": response.elapsed_ms, "errorType": None, "errorMessage": None,
        }
    except Exception as exc:
        return [], {
            "sourceId": source_id, "sourceName": "Google News", "status": "failed",
            "lastAttemptAt": attempted, "lastSuccessAt": None, "articlesRetrieved": 0,
            "responseTimeMs": None, "errorType": exc.__class__.__name__, "errorMessage": str(exc)[:180],
        }
