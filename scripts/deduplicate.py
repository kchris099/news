from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any


def _tokens(title: str) -> set[str]:
    return {token for token in re.findall(r"\w+", title.casefold()) if len(token) > 2}


def token_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def char_ngram_similarity(left: str, right: str, n: int = 3) -> float:
    def grams(value: str) -> set[str]:
        compact = re.sub(r"\s+", " ", value.casefold()).strip()
        return {compact[index:index + n] for index in range(max(0, len(compact) - n + 1))}
    a, b = grams(left), grams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _time_delta_hours(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = datetime.fromisoformat(left["publishedAt"].replace("Z", "+00:00"))
    b = datetime.fromisoformat(right["publishedAt"].replace("Z", "+00:00"))
    return abs((a - b).total_seconds()) / 3600


def near_duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if _time_delta_hours(left, right) > 36:
        return False
    a = left.get("normalizedTitle") or left["title"].casefold()
    b = right.get("normalizedTitle") or right["title"].casefold()
    if a == b:
        return True
    token = token_similarity(a, b)
    char = char_ngram_similarity(a, b)
    sequence = SequenceMatcher(None, a, b).ratio()
    return (token >= 0.82 and (char >= 0.72 or sequence >= 0.88)) or (token >= 0.55 and sequence >= 0.78)


def _merge_article(primary: dict[str, Any], duplicate: dict[str, Any]) -> dict[str, Any]:
    primary["dataSources"] = sorted(set(primary.get("dataSources", []) + duplicate.get("dataSources", [])))
    if not primary.get("description") and duplicate.get("description"):
        primary["description"] = duplicate["description"]
    if not primary.get("imageUrl") and duplicate.get("imageUrl"):
        primary["imageUrl"] = duplicate["imageUrl"]
    primary["sourceQuality"] = max(float(primary.get("sourceQuality", 1)), float(duplicate.get("sourceQuality", 1)))
    return primary


def deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for article in sorted(articles, key=lambda item: item["publishedAt"], reverse=True):
        key = article["canonicalUrl"]
        if key in by_url:
            by_url[key] = _merge_article(by_url[key], article)
        else:
            by_url[key] = article

    candidates = list(by_url.values())
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in candidates:
        tokens = sorted(_tokens(article.get("normalizedTitle") or article["title"]))
        bucket = tokens[0][0] if tokens else "_"
        buckets[bucket].append(article)

    output: list[dict[str, Any]] = []
    for group in buckets.values():
        kept: list[dict[str, Any]] = []
        for article in group:
            duplicate = next((item for item in kept if near_duplicate(item, article)), None)
            if duplicate:
                _merge_article(duplicate, article)
            else:
                kept.append(article)
        output.extend(kept)
    return output
