from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from math import exp
from typing import Any


def _recency_score(published_at: str, now: datetime) -> float:
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    hours = max(0.0, (now - published).total_seconds() / 3600)
    return exp(-hours / 18)


def score_article(article: dict[str, Any], country: dict[str, Any], ranking: dict[str, Any], now: datetime | None = None) -> float:
    weights = ranking["weights"]
    now = now or datetime.now(timezone.utc)
    sources = int(article.get("independentSourceCount", 1))
    score = weights["independentSources"] * min(3, max(0, sources - 1)) / 2
    score += weights["recency"] * _recency_score(article["publishedAt"], now)
    score += weights["sourceQuality"] * float(article.get("sourceQuality", 1.0))
    score += weights["validImage"] if article.get("imageUrl") else 0
    score += weights["usefulDescription"] if article.get("description") else 0
    score += weights["domesticRelevance"] if country["code"] in article.get("coverageCountries", []) else 0
    score += weights["aggregatorPenalty"] if "google-news" in article.get("dataSources", []) else 0
    score += weights["syndicationPenalty"] if article.get("isSyndicated") else 0
    return round(score, 5)


def rank_and_balance(articles: list[dict[str, Any]], country: dict[str, Any], ranking: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    for article in articles:
        article["rankingScore"] = score_article(article, country, ranking)
    ordered = sorted(articles, key=lambda item: (item["rankingScore"], item["publishedAt"]), reverse=True)
    balance = ranking["balancing"]
    window_size = int(balance.get("firstWindowSize", 12))
    publisher_cap = int(balance.get("maxPerPublisherInFirstWindow", 3))
    aggregator_cap = int(balance.get("maxAggregatorOnlyInFirstWindow", 4))
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    publisher_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    aggregator_count = 0

    for article in ordered:
        if len(selected) >= limit:
            break
        if len(selected) < window_size:
            publisher = article.get("sourceDomain") or article.get("sourceName", "unknown")
            aggregator_only = article.get("dataSources") in (["google-news"], ["gdelt"])
            if publisher_counts[publisher] >= publisher_cap or (aggregator_only and aggregator_count >= aggregator_cap):
                deferred.append(article)
                continue
            diversity_bonus = 0.0 if category_counts[article.get("category", "General")] else ranking["weights"].get("categoryDiversity", 0)
            article["rankingScore"] = round(article["rankingScore"] + diversity_bonus, 5)
            publisher_counts[publisher] += 1
            category_counts[article.get("category", "General")] += 1
            aggregator_count += int(aggregator_only)
        selected.append(article)

    for article in deferred:
        if len(selected) >= limit:
            break
        selected.append(article)

    for article in selected:
        article.pop("normalizedTitle", None)
        article.pop("sourceQuality", None)
        article.pop("independentSourceCount", None)
        article.pop("isSyndicated", None)
    return selected
