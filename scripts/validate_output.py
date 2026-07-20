from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .utilities import date_key_for_timestamp, load_json, local_date_keys, parse_iso

VALID_STATUSES = {"current", "partial", "retained", "empty", "failed", "missing", "sample"}


class ValidationFailure(ValueError):
    pass


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    split = urlsplit(value)
    return split.scheme in {"http", "https"} and bool(split.netloc)


def validate_article(article: dict[str, Any], date_key: str, time_zone: str) -> list[str]:
    errors: list[str] = []
    for field in ("id", "title", "sourceName", "publishedAt", "url", "canonicalUrl"):
        if not article.get(field):
            errors.append(f"article missing {field}")
    if article.get("url") and not _valid_url(article["url"]):
        errors.append("article has unsafe url")
    if article.get("canonicalUrl") and not _valid_url(article["canonicalUrl"]):
        errors.append("article has unsafe canonicalUrl")
    if article.get("imageUrl") and not str(article["imageUrl"]).startswith("https://"):
        errors.append("article imageUrl must use https")
    try:
        published = datetime.fromisoformat(str(article["publishedAt"]).replace("Z", "+00:00"))
        if date_key_for_timestamp(published, time_zone) != date_key:
            errors.append("article does not belong to intended local date")
    except (KeyError, ValueError):
        errors.append("article has invalid publication timestamp")
    if article.get("translatedTitle") and article.get("translatedTitle") == article.get("title"):
        errors.append("translatedTitle duplicates title")
    return errors


def validate_day(payload: dict[str, Any], country: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    date_key = payload.get("date")
    if payload.get("countryCode") != country["code"]:
        errors.append("countryCode mismatch")
    if not date_key:
        errors.append("missing date")
        return errors
    if payload.get("status") not in VALID_STATUSES:
        errors.append("invalid status")
    articles = payload.get("articles")
    if not isinstance(articles, list):
        errors.append("articles must be a list")
        return errors
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for article in articles:
        errors.extend(validate_article(article, date_key, country["timeZone"]))
        if article.get("id") in seen_ids:
            errors.append("duplicate article id")
        if article.get("canonicalUrl") in seen_urls:
            errors.append("duplicate canonical URL")
        seen_ids.add(article.get("id"))
        seen_urls.add(article.get("canonicalUrl"))
    return errors


def validate_manifest(manifest: dict[str, Any], countries: list[dict[str, Any]], settings: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("archiveDays") != settings["archiveDays"]:
        errors.append("manifest archiveDays mismatch")
    if manifest.get("defaultCountry") != settings["defaultCountry"]:
        errors.append("manifest defaultCountry mismatch")
    generated_at = parse_iso(manifest.get("generatedAt"))
    by_code = {country["code"]: country for country in countries}
    for code, country in by_code.items():
        dates = manifest.get("countries", {}).get(code, {}).get("dates", {})
        # Validate a committed archive against the run that produced it. Using
        # the current wall clock makes a valid archive fail as soon as a
        # country crosses midnight between generation and validation.
        expected = local_date_keys(country["timeZone"], settings["archiveDays"], generated_at)
        if list(dates.keys()) != expected:
            errors.append(f"{code} does not expose exactly the expected seven ordered dates")
        for date_key in expected:
            entry = dates.get(date_key, {})
            if entry.get("status") not in VALID_STATUSES:
                errors.append(f"{code}/{date_key} has invalid status")
            if not entry.get("path"):
                errors.append(f"{code}/{date_key} missing path")
    return errors


def validate_repository(root: Path) -> list[str]:
    countries = load_json(root / "config" / "countries.json", [])
    settings = load_json(root / "config" / "settings.json", {})
    manifest = load_json(root / "data" / "manifest.json", {})
    errors = validate_manifest(manifest, countries, settings)
    generated_at = parse_iso(manifest.get("generatedAt"))
    for country in countries:
        for date_key in local_date_keys(country["timeZone"], settings["archiveDays"], generated_at):
            path = root / "data" / country["code"] / f"{date_key}.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                errors.append(f"{path.relative_to(root)}: {exc}")
                continue
            for error in validate_day(payload, country):
                errors.append(f"{path.relative_to(root)}: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated Worldline JSON files")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate_repository(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Generated JSON validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
