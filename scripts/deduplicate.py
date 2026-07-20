from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any


GENERIC_TOKENS = {
    "about", "after", "amid", "and", "are", "as", "at", "before", "been", "but",
    "by", "during", "for", "from", "had", "has", "have", "her", "his", "how",
    "in", "into", "is", "it", "its", "latest", "more", "new", "news", "not", "of",
    "on", "or", "over", "report", "said", "says", "than", "the", "their", "they",
    "this", "that", "today", "to", "update", "was", "were", "who", "why", "will", "with",
}


def _tokens(title: str) -> set[str]:
    """Return useful title terms while keeping short names such as JD and VP."""
    text = unicodedata.normalize("NFKC", title).casefold()
    text = re.sub(r"\bu[\W_]*s\b", "us", text)
    return {
        token for token in re.findall(r"[^\W_]+", text, flags=re.UNICODE)
        if len(token) > 1 and token not in GENERIC_TOKENS
    }


def meaningful_tokens(title: str) -> set[str]:
    """Public token helper shared by duplicate and event matching."""
    return _tokens(title)


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
    left_tokens, right_tokens = _tokens(a), _tokens(b)
    token = token_similarity(a, b)
    char = char_ngram_similarity(a, b)
    sequence = SequenceMatcher(None, a, b).ratio()
    shared = len(left_tokens & right_tokens)
    containment = shared / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
    return (
        (token >= 0.78 and (char >= 0.68 or sequence >= 0.86))
        or (containment >= 0.80 and token >= 0.50)
        or (token >= 0.50 and sequence >= 0.76)
    )


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

    output: list[dict[str, Any]] = []
    # Daily inputs are small enough to compare all candidates. The old
    # first-letter buckets missed equivalent headlines led by different terms,
    # such as "Oil Prices Cross $90" and "Brent Breaks Past $90".
    for article in sorted(by_url.values(), key=lambda item: item["publishedAt"], reverse=True):
        duplicate = next((item for item in output if near_duplicate(item, article)), None)
        if duplicate:
            _merge_article(duplicate, article)
        else:
            output.append(article)
    return output
