from copy import deepcopy

from scripts.cluster import cluster_articles, same_event


def article(title, domain, hour):
    return {
        "id": domain, "title": title, "normalizedTitle": title.casefold(), "canonicalUrl": f"https://{domain}/x",
        "publishedAt": f"2026-07-19T{hour:02d}:00:00Z", "sourceName": domain, "sourceDomain": domain,
        "sourceQuality": 1.0, "imageUrl": None, "description": None, "dataSources": ["publisher-rss"],
    }


def test_same_event_requires_named_overlap_and_similarity():
    left = article("Tokyo Metro resumes service after Shinjuku power outage", "a.example", 12)
    right = article("Shinjuku power outage disrupts Tokyo Metro service", "b.example", 13)
    assert same_event(left, right)


def test_separate_updates_far_apart_are_not_clustered():
    left = article("Tokyo Metro resumes service after Shinjuku power outage", "a.example", 1)
    right = article("Tokyo Metro reviews Shinjuku outage response", "b.example", 23)
    assert not same_event(left, right)


def test_cluster_keeps_related_coverage():
    a = article("Paris rail workers approve national agreement", "a.example", 12)
    b = article("National agreement approved by Paris rail workers", "b.example", 13)
    result = cluster_articles([a, b])
    assert len(result) == 1
    assert len(result[0]["related"]) == 1


def test_oil_headlines_with_different_leads_are_same_event():
    left = article("Oil Prices Cross $90 a Barrel as U.S.-Iran Conflict Widens", "nytimes.com", 12)
    right = article("Brent Breaks Past $90 as U.S.-Iran Conflict Rages On", "cnbc.com", 14)
    assert same_event(left, right)


def test_vance_baby_headlines_with_different_detail_are_same_event():
    left = article("JD and Usha Vance Welcome Fourth Child", "nytimes.com", 12)
    right = article("JD Vance and wife Usha welcome fourth child, reveal baby boy's name", "foxnews.com", 13)
    assert same_event(left, right)


def test_shared_number_without_shared_event_terms_is_not_enough():
    left = article("90 students graduate from city schools", "a.example", 12)
    right = article("90 homes damaged in coastal storm", "b.example", 13)
    assert not same_event(left, right)
