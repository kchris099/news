from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from .utilities import AsyncFetcher, iso_z, local_day_window


def build_gdelt_url(country: dict[str, Any], date_key: str, providers: dict[str, Any]) -> str:
    config = providers["gdelt"]
    start, end = local_day_window(date_key, country["timeZone"])
    query = f'sourcecountry:{country["gdeltSourceCountry"]}'
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": int(config.get("maxRecordsPerDate", 250)),
        "sort": config.get("sort", "HybridRel"),
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    return f'{config["endpoint"]}?{urlencode(params)}'


async def fetch_gdelt(fetcher: AsyncFetcher, country: dict[str, Any], providers: dict[str, Any], date_key: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_id = f'gdelt-{country["code"]}-{date_key}'
    attempted = iso_z()
    try:
        # GDELT is an optional backfill provider and rate-limits aggressively.
        # Let the scheduler move on to other dates/providers after one attempt
        # instead of retrying the same URL while the rest of the refresh waits.
        response = await fetcher.get(
            build_gdelt_url(country, date_key, providers),
            expected=("json", "text/plain"),
            retry_attempts=1,
        )
        payload = {"articles": []} if response.status_code == 304 else json.loads(response.content.decode("utf-8-sig"))
        retrieved = iso_z()
        articles: list[dict[str, Any]] = []
        for item in payload.get("articles", []):
            domain = str(item.get("domain") or "").lower().removeprefix("www.")
            articles.append({
                "title": item.get("title"), "url": item.get("url"), "description": None,
                "imageUrl": item.get("socialimage"), "publishedAt": item.get("seendate"),
                "sourceName": item.get("domain") or "GDELT source", "sourceId": source_id,
                "publisherUrl": f"https://{domain}" if domain else None,
                "sourceCountry": item.get("sourcecountry") or country["code"],
                "editionCountry": country["code"], "language": item.get("language"),
                "sourceQuality": 0.78, "retrievedAt": retrieved, "dataSource": "gdelt",
            })
        return articles, {
            "sourceId": source_id, "sourceName": "GDELT", "status": "success",
            "lastAttemptAt": attempted, "lastSuccessAt": iso_z(), "articlesRetrieved": len(articles),
            "responseTimeMs": response.elapsed_ms, "errorType": None, "errorMessage": None,
        }
    except Exception as exc:
        return [], {
            "sourceId": source_id, "sourceName": "GDELT", "status": "failed",
            "lastAttemptAt": attempted, "lastSuccessAt": None, "articlesRetrieved": 0,
            "responseTimeMs": None, "errorType": exc.__class__.__name__, "errorMessage": str(exc)[:180],
        }
