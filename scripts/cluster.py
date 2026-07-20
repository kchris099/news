from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .deduplicate import char_ngram_similarity, meaningful_tokens, token_similarity
from .utilities import stable_hash

GENERIC = {"news", "update", "latest", "today", "report", "says", "new", "after", "with", "from", "over", "amid"}


def named_terms(title: str) -> set[str]:
    # Normalize U.S./US before splitting so the abbreviation is comparable
    # across publishers, and keep two-character entities such as JD and VP.
    title = re.sub(r"\bu[\W_]*s\b", "US", title, flags=re.IGNORECASE)
    words = re.findall(r"[A-Za-z\u0080-\uffff]+|\d+(?:\.\d+)?", title)
    capitalized = {
        re.sub(r"[^\w]", "", word).casefold()
        for word in words
        if word[:1].isupper() and len(word) >= 2 and word.casefold() not in GENERIC
    }
    numbers = {word for word in words if any(char.isdigit() for char in word)}
    return capitalized | numbers


def same_event(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("sourceDomain") == right.get("sourceDomain"):
        return False
    a_time = datetime.fromisoformat(left["publishedAt"].replace("Z", "+00:00"))
    b_time = datetime.fromisoformat(right["publishedAt"].replace("Z", "+00:00"))
    if abs((a_time - b_time).total_seconds()) > 18 * 3600:
        return False

    left_terms, right_terms = named_terms(left["title"]), named_terms(right["title"])
    shared_named = left_terms & right_terms
    left_tokens = meaningful_tokens(left["title"])
    right_tokens = meaningful_tokens(right["title"])
    shared_tokens = left_tokens & right_tokens
    token = token_similarity(left["title"], right["title"])
    char = char_ngram_similarity(left["title"], right["title"])
    coverage = len(shared_tokens) / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
    shared_numbers = {term for term in shared_tokens if any(char.isdigit() for char in term)}
    shared_non_numeric = shared_tokens - shared_numbers

    # Related coverage often uses different verbs and nouns, but repeats the
    # same people, place, or concrete fact. Use those signals before falling
    # back to stricter lexical similarity rules.
    if len(shared_named) >= 2 and coverage >= 0.42:
        return True
    if shared_numbers and len(shared_non_numeric) >= 2 and coverage >= 0.28:
        return True
    return (len(shared_named) >= 1 and token >= 0.58 and char >= 0.48) or (token >= 0.58 and char >= 0.48)


def _representative_score(article: dict[str, Any]) -> float:
    score = float(article.get("sourceQuality", 1.0))
    score += 0.35 if article.get("imageUrl") else 0
    score += 0.25 if article.get("description") else 0
    score -= 0.45 if "google-news" in article.get("dataSources", []) else 0
    score -= 0.35 if article.get("dataSources") == ["gdelt"] else 0
    return score


def cluster_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for article in sorted(articles, key=lambda item: item["publishedAt"], reverse=True):
        target = next((cluster for cluster in clusters if any(same_event(article, existing) for existing in cluster)), None)
        if target is None:
            clusters.append([article])
        else:
            target.append(article)

    output: list[dict[str, Any]] = []
    for group in clusters:
        domains = [item.get("sourceDomain") or item.get("sourceName") for item in group]
        cluster_id = stable_hash(*sorted(str(domain) for domain in domains), *(sorted(item["normalizedTitle"][:80] for item in group)), length=20)
        for item in group:
            item["clusterId"] = cluster_id
        representative = max(group, key=_representative_score)
        related = sorted((item for item in group if item is not representative), key=lambda item: item["publishedAt"], reverse=True)
        representative["related"] = related
        representative["independentSourceCount"] = len(set(domains))
        output.append(representative)
    return output
