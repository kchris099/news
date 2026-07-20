from copy import deepcopy
from datetime import datetime, timezone

from scripts.rank import rank_and_balance, score_article

RANKING = {
    "weights": {"independentSources": 2.8, "recency": 2.2, "sourceQuality": 1.8, "validImage": 0.55, "usefulDescription": 0.4, "domesticRelevance": 0.8, "categoryDiversity": 0.35, "aggregatorPenalty": -0.75, "syndicationPenalty": -0.45},
    "balancing": {"firstWindowSize": 12, "maxPerPublisherInFirstWindow": 2, "minimumDistinctPublishers": 3, "maxPerCluster": 1, "maxAggregatorOnlyInFirstWindow": 4},
}
COUNTRY = {"code": "US"}


def make_article(index, source="a.example", related=1):
    return {
        "id": str(index), "title": f"Story {index}", "canonicalUrl": f"https://{source}/{index}",
        "publishedAt": f"2026-07-19T{20-index:02d}:00:00Z", "sourceName": source, "sourceDomain": source,
        "sourceQuality": 1.0, "imageUrl": None, "description": None, "dataSources": ["publisher-rss"],
        "coverageCountries": [], "category": "World", "independentSourceCount": related,
        "normalizedTitle": f"story {index}", "related": [],
    }


def test_independent_coverage_increases_score():
    now = datetime(2026, 7, 19, 21, tzinfo=timezone.utc)
    one = make_article(1, related=1)
    three = make_article(2, related=3)
    three["publishedAt"] = one["publishedAt"]
    assert score_article(three, COUNTRY, RANKING, now) > score_article(one, COUNTRY, RANKING, now)


def test_first_window_enforces_publisher_cap():
    articles = [make_article(i, "same.example") for i in range(1, 6)] + [make_article(10, "other.example"), make_article(11, "third.example")]
    ranked = rank_and_balance(articles, COUNTRY, RANKING, 7)
    first = ranked[:5]
    assert sum(1 for item in first if item["sourceDomain"] == "same.example") <= 3
