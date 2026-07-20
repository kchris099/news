from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .classify import classify_article
from .cluster import cluster_articles
from .deduplicate import deduplicate_articles
from .feed_parser import fetch_feed
from .gdelt_client import fetch_gdelt
from .google_news_client import fetch_google_news
from .normalize import normalize_article, normalize_title
from .rank import rank_and_balance
from .translate import translate_articles
from .utilities import (
    AsyncFetcher, date_key_for_timestamp, iso_z, load_json, local_date_keys,
    parse_iso, write_json_atomic,
)
from .validate_output import validate_day, validate_manifest

LOGGER = logging.getLogger("worldline")


def flatten_existing_articles(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    output: list[dict[str, Any]] = []
    for article in payload.get("articles", []):
        clone = dict(article)
        related = clone.pop("related", []) or []
        for item in [clone, *related]:
            restored = dict(item)
            restored["normalizedTitle"] = normalize_title(restored.get("title", ""))
            restored["sourceQuality"] = float(restored.get("sourceQuality", 1.0))
            restored.setdefault("dataSources", ["retained"])
            output.append(restored)
    return output


def suspicious_drop(new_count: int, old_count: int, settings: dict[str, Any]) -> bool:
    if old_count <= 0:
        return False
    minimum = int(settings.get("minimumSafeArticleCount", 8))
    ratio = float(settings.get("suspiciousDropRatio", 0.35))
    threshold = max(minimum, round(old_count * ratio))
    return new_count < threshold


def health_for_day(global_health: list[dict[str, Any]], date_health: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [*global_health, *date_health]


def publisher_count(articles: list[dict[str, Any]]) -> int:
    return len({article.get("sourceDomain") or article.get("sourceName") for article in articles if article.get("sourceName")})


async def collect_country(
    root: Path,
    country: dict[str, Any],
    settings: dict[str, Any],
    ranking: dict[str, Any],
    providers: dict[str, Any],
    fetcher: AsyncFetcher,
    translation_cache: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    code = country["code"]
    date_keys = local_date_keys(country["timeZone"], settings["archiveDays"])
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

    feed_tasks = [fetch_feed(fetcher, source, code) for source in country.get("sources", []) if source.get("enabled", True)]
    if providers.get("googleNews", {}).get("enabled", True):
        feed_tasks.append(fetch_google_news(fetcher, country, providers, None))
    feed_results = await asyncio.gather(*feed_tasks)
    global_health = [health for _, health in feed_results]

    for raw_articles, _ in feed_results:
        for raw in raw_articles:
            article = normalize_article(raw, settings)
            if not article:
                continue
            timestamp = parse_iso(article["publishedAt"])
            if not timestamp:
                continue
            date_key = date_key_for_timestamp(timestamp, country["timeZone"])
            if date_key in date_keys:
                buckets[date_key].append(article)

    async def date_sources(date_key: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        tasks = []
        if providers.get("googleNews", {}).get("enabled", True):
            tasks.append(fetch_google_news(fetcher, country, providers, date_key))
        if providers.get("gdelt", {}).get("enabled", True):
            tasks.append(fetch_gdelt(fetcher, country, providers, date_key))
        results = await asyncio.gather(*tasks)
        raw: list[dict[str, Any]] = []
        health: list[dict[str, Any]] = []
        for articles, status in results:
            raw.extend(articles)
            health.append(status)
        return date_key, raw, health

    date_results = await asyncio.gather(*(date_sources(date_key) for date_key in date_keys))
    date_health_map: dict[str, list[dict[str, Any]]] = {}
    for date_key, raw_articles, health in date_results:
        date_health_map[date_key] = health
        for raw in raw_articles:
            article = normalize_article(raw, settings)
            if not article:
                continue
            timestamp = parse_iso(article["publishedAt"])
            if timestamp and date_key_for_timestamp(timestamp, country["timeZone"]) == date_key:
                buckets[date_key].append(article)

    country_manifest = {"name": country["name"], "timeZone": country["timeZone"], "dates": {}}
    all_health: list[dict[str, Any]] = []
    generated_at = iso_z()

    for date_key in date_keys:
        daily_path = root / "data" / code / f"{date_key}.json"
        existing = load_json(daily_path, None)
        existing_live = existing if existing and not existing.get("samplePreview") else None
        candidates = [*buckets[date_key], *flatten_existing_articles(existing_live)]
        unique = deduplicate_articles(candidates)
        for article in unique:
            classify_article(article, country)
        clustered = cluster_articles(unique)
        await translate_articles(clustered, settings, translation_cache)
        daily_limit = min(int(settings.get("perDayTarget", 45)), int(settings.get("maxArticleCountPerDay", 60)))
        ranked = rank_and_balance(clustered, country, ranking, daily_limit)
        daily_health = health_for_day(global_health, date_health_map.get(date_key, []))
        all_health.extend(daily_health)
        failures = [item for item in daily_health if item.get("status") != "success"]
        old_count = len(existing_live.get("articles", [])) if existing_live else 0

        if existing_live and suspicious_drop(len(ranked), old_count, settings):
            retained = dict(existing_live)
            retained["status"] = "retained"
            retained["lastAttemptAt"] = generated_at
            retained["warning"] = f"Latest collection produced {len(ranked)} articles versus {old_count} retained articles."
            retained["sourceHealth"] = daily_health
            retained["samplePreview"] = False
            payload = retained
        else:
            status = "partial" if ranked and failures else "current" if ranked else "empty"
            payload = {
                "schemaVersion": 1,
                "countryCode": code,
                "countryName": country["name"],
                "timeZone": country["timeZone"],
                "date": date_key,
                "generatedAt": generated_at,
                "lastAttemptAt": generated_at,
                "lastSuccessfulUpdate": generated_at if ranked else (existing_live or {}).get("lastSuccessfulUpdate"),
                "status": status,
                "samplePreview": False,
                "articleCount": len(ranked),
                "publisherCount": publisher_count(ranked),
                "sourceHealth": daily_health,
                "articles": ranked,
            }
        errors = validate_day(payload, country)
        if errors:
            raise ValueError(f"Validation failed for {code}/{date_key}: {'; '.join(errors[:8])}")
        write_json_atomic(daily_path, payload)
        country_manifest["dates"][date_key] = {
            "articleCount": len(payload.get("articles", [])),
            "publisherCount": publisher_count(payload.get("articles", [])),
            "lastSuccessfulUpdate": payload.get("lastSuccessfulUpdate"),
            "lastAttemptAt": generated_at,
            "status": payload["status"],
            "path": f"data/{code}/{date_key}.json",
        }

    allowed = set(date_keys)
    country_dir = root / "data" / code
    if country_dir.exists():
        for path in country_dir.glob("*.json"):
            if path.stem not in allowed:
                path.unlink()
    return country_manifest, all_health


async def run(root: Path, only_countries: set[str] | None = None) -> None:
    countries = load_json(root / "config" / "countries.json", [])
    settings = load_json(root / "config" / "settings.json", {})
    ranking = load_json(root / "config" / "ranking.json", {})
    providers = load_json(root / "config" / "sources.json", {})
    if only_countries:
        countries = [country for country in countries if country["code"] in only_countries]
    http_cache = load_json(root / "data" / "http-cache.json", {})
    translation_cache = load_json(root / "data" / "translation-cache.json", {})
    generated_at = iso_z()
    manifest = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "archiveDays": settings["archiveDays"],
        "defaultCountry": settings["defaultCountry"],
        "overallStatus": "current",
        "samplePreview": False,
        "countries": {},
    }
    all_health: list[dict[str, Any]] = []

    async with AsyncFetcher(settings, http_cache) as fetcher:
        for country in countries:
            LOGGER.info("Collecting %s", country["name"])
            country_manifest, health = await collect_country(
                root, country, settings, ranking, providers, fetcher, translation_cache
            )
            manifest["countries"][country["code"]] = country_manifest
            all_health.extend(health)

    if only_countries:
        existing_manifest = load_json(root / "data" / "manifest.json", {})
        for code, value in existing_manifest.get("countries", {}).items():
            manifest["countries"].setdefault(code, value)

    ordered_manifest = {}
    full_countries = load_json(root / "config" / "countries.json", [])
    for country in full_countries:
        if country["code"] in manifest["countries"]:
            ordered_manifest[country["code"]] = manifest["countries"][country["code"]]
    manifest["countries"] = ordered_manifest

    country_map = {country["code"]: country for country in full_countries}
    failures = sum(1 for item in all_health if item.get("status") != "success")
    retained = any(
        entry.get("status") == "retained"
        for country_entry in manifest["countries"].values()
        for entry in country_entry.get("dates", {}).values()
    )
    if failures or retained:
        manifest["overallStatus"] = "partial"
    errors = validate_manifest(manifest, full_countries, settings)
    if errors:
        raise ValueError("Manifest validation failed: " + "; ".join(errors[:10]))
    write_json_atomic(root / "data" / "manifest.json", manifest)
    write_json_atomic(root / "data" / "source-health.json", {"generatedAt": generated_at, "sources": all_health})
    write_json_atomic(root / "data" / "http-cache.json", http_cache)
    write_json_atomic(root / "data" / "translation-cache.json", translation_cache)
    LOGGER.info("Generation complete: %s source checks, %s failures", len(all_health), failures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect and generate Worldline headline archives")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--countries", help="Comma-separated country codes, for example US,GB")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    only = {item.strip().upper() for item in args.countries.split(",")} if args.countries else None
    asyncio.run(run(args.root, only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
