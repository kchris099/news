from __future__ import annotations

import asyncio
import json
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from .feed_parser import extract_page_image, parse_feed_bytes
from .utilities import AsyncFetcher, iso_z, safe_image_url, source_domain


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


def _google_article_token(url: str) -> str | None:
    path = urlsplit(url).path
    match = re.search(r"/(?:rss/)?articles/([^/]+)$", path)
    return match.group(1) if match else None


async def _google_decoding_params(fetcher: AsyncFetcher, article_url: str) -> dict[str, str] | None:
    token = _google_article_token(article_url)
    if not token:
        return None
    try:
        response = await fetcher.get(article_url, expected=("html", "xhtml", "text/plain"))
        text = response.content.decode("utf-8", errors="replace")
        signature = re.search(r'data-n-a-sg="([^"]+)"', text)
        timestamp = re.search(r'data-n-a-ts="([^"]+)"', text)
        if not signature or not timestamp:
            return None
        return {"token": token, "signature": signature.group(1), "timestamp": timestamp.group(1)}
    except Exception:
        return None


async def _resolve_google_urls(
    fetcher: AsyncFetcher,
    params: list[dict[str, str]],
    locale: str,
) -> dict[str, str]:
    if not params:
        return {}
    requests = []
    for item in params:
        request = (
            '["garturlreq",[["X","X",["X","X"],null,null,1,1,'
            f'"{locale}",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],'
            f'1,1,null,0,0,null,0],"{item["token"]}",{item["timestamp"]},"{item["signature"]}"]'
        )
        requests.append(["Fbv4je", request])
    payload = f"f.req={quote(json.dumps([requests], separators=(",", ":")))}"
    try:
        response = await fetcher.client.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            content=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Referer": "https://news.google.com/",
            },
        )
        response.raise_for_status()
        body = response.text.split("\n\n", 1)[-1]
        rows = json.loads(body)
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}
    except Exception:
        return {}

    resolved: dict[str, str] = {}
    result_rows = [row for row in rows if isinstance(row, list) and len(row) > 2 and row[0] == "wrb.fr" and row[1] == "Fbv4je"]
    for item, row in zip(params, result_rows):
        try:
            result = json.loads(row[2])
            direct_url = result[1] if result[0] == "garturlres" else None
            if isinstance(direct_url, str) and direct_url.startswith("https://"):
                resolved[item["token"]] = direct_url
        except (IndexError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return resolved


async def _resolve_google_url(
    fetcher: AsyncFetcher,
    params: dict[str, str],
    locale: str,
) -> str | None:
    """Resolve one token when a batched response omits a row.

    Google occasionally returns fewer response rows than requests. Mapping
    those partial rows by position can associate one publisher's URL with a
    different headline, so retry the affected tokens individually.
    """
    return (await _resolve_google_urls(fetcher, [params], locale)).get(params["token"])


async def enrich_google_images(
    fetcher: AsyncFetcher,
    articles: list[dict[str, Any]],
    image_cache: dict[str, Any],
    locale: str,
    limit: int = 24,
) -> None:
    candidates = [
        article for article in articles
        if not article.get("imageUrl")
        and (article.get("dataSource") == "google-news" or "google-news" in (article.get("dataSources") or []))
        and _google_article_token(str(article.get("url") or ""))
    ]
    candidates = sorted(candidates, key=lambda item: str(item.get("publishedAt") or ""), reverse=True)[:max(0, limit)]
    pending: list[dict[str, Any]] = []
    for article in candidates:
        cached = image_cache.get(article["url"]) or {}
        expected_domain = str(article.get("sourceDomain") or "").lower().removeprefix("www.")
        cached_domain = source_domain(cached.get("articleUrl"))
        cache_matches_source = (
            not expected_domain
            or not cached_domain
            or cached_domain == expected_domain
            or cached_domain.endswith(f".{expected_domain}")
        )
        if cached.get("articleUrl") and cache_matches_source:
            article["url"] = cached["articleUrl"]
            if "canonicalUrl" in article:
                article["canonicalUrl"] = cached["articleUrl"]
            cached_image = safe_image_url(cached.get("imageUrl"))
            if cached_image:
                article["imageUrl"] = cached_image
        else:
            pending.append(article)

    gate = asyncio.Semaphore(4)

    async def get_params(article: dict[str, Any]) -> dict[str, str] | None:
        async with gate:
            return await _google_decoding_params(fetcher, article["url"])

    param_results = await asyncio.gather(*(get_params(article) for article in pending))
    pending_params = [(article, params) for article, params in zip(pending, param_results) if params]
    batch_params = [params for _, params in pending_params]
    resolved = await _resolve_google_urls(fetcher, batch_params, locale)
    if len(resolved) != len(batch_params):
        individual = await asyncio.gather(
            *(_resolve_google_url(fetcher, params, locale) for params in batch_params)
        )
        resolved = {
            params["token"]: direct_url
            for params, direct_url in zip(batch_params, individual)
            if direct_url
        }
    else:
        # A full batched response can still be positionally misaligned when
        # Google silently substitutes one result. Re-resolve any token whose
        # destination does not match the publisher domain.
        mismatched = []
        for article, params in pending_params:
            direct_url = resolved.get(params["token"])
            expected_domain = str(article.get("sourceDomain") or "").lower().removeprefix("www.")
            direct_domain = source_domain(direct_url)
            if (
                direct_url
                and expected_domain
                and direct_domain
                and direct_domain != expected_domain
                and not direct_domain.endswith(f".{expected_domain}")
            ):
                mismatched.append(params)
        if mismatched:
            individual = await asyncio.gather(
                *(_resolve_google_url(fetcher, params, locale) for params in mismatched)
            )
            for params, direct_url in zip(mismatched, individual):
                if direct_url:
                    resolved[params["token"]] = direct_url

    async def fetch_image(article: dict[str, Any], params: dict[str, str]) -> None:
        direct_url = resolved.get(params["token"])
        if not direct_url:
            return
        expected_domain = str(article.get("sourceDomain") or "").lower().removeprefix("www.")
        direct_domain = source_domain(direct_url)
        if expected_domain and direct_domain and direct_domain != expected_domain and not direct_domain.endswith(f".{expected_domain}"):
            return
        image_url = None
        try:
            response = await asyncio.wait_for(
                fetcher.get(
                    direct_url,
                    expected=("html", "xhtml", "text/plain"),
                    max_bytes=max(fetcher.max_bytes, 8_000_000),
                ),
                timeout=8.0,
            )
            image_url = extract_page_image(response.content, direct_url)
        except Exception:
            pass
        original_url = article["url"]
        image_cache[original_url] = {
            "articleUrl": direct_url,
            "imageUrl": image_url,
            "checkedAt": iso_z(),
        }
        article["url"] = direct_url
        if "canonicalUrl" in article:
            article["canonicalUrl"] = direct_url
        if image_url:
            article["imageUrl"] = image_url

    await asyncio.gather(*(fetch_image(article, params) for article, params in pending_params))


async def fetch_google_news(fetcher: AsyncFetcher, country: dict[str, Any], providers: dict[str, Any], date_key: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_id = f'google-news-{country["code"]}' + (f'-{date_key}' if date_key else '-top')
    source = {
        "id": source_id, "name": None, "language": country["primaryLanguage"],
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
