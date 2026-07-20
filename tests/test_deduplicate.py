from copy import deepcopy

from scripts.deduplicate import deduplicate_articles, near_duplicate

BASE = {
    "id": "1", "title": "Major storm closes schools across the region", "normalizedTitle": "major storm closes schools across the region",
    "canonicalUrl": "https://example.com/storm", "publishedAt": "2026-07-19T12:00:00Z",
    "dataSources": ["publisher-rss"], "sourceQuality": 1.0, "sourceName": "Example", "sourceDomain": "example.com",
    "description": None, "imageUrl": None,
}


def test_exact_url_duplicate_merges_data_sources():
    other = deepcopy(BASE)
    other["id"] = "2"
    other["dataSources"] = ["google-news"]
    result = deduplicate_articles([deepcopy(BASE), other])
    assert len(result) == 1
    assert result[0]["dataSources"] == ["google-news", "publisher-rss"]


def test_near_duplicate_headlines_are_detected():
    other = deepcopy(BASE)
    other["title"] = "Major storm shuts schools throughout the region"
    other["normalizedTitle"] = "major storm shuts schools throughout the region"
    other["canonicalUrl"] = "https://other.example/storm"
    assert near_duplicate(BASE, other)


def test_generic_shared_words_do_not_merge_unrelated_stories():
    other = deepcopy(BASE)
    other["title"] = "Regional bank reports quarterly earnings"
    other["normalizedTitle"] = "regional bank reports quarterly earnings"
    other["canonicalUrl"] = "https://other.example/bank"
    assert not near_duplicate(BASE, other)
