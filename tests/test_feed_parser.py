from pathlib import Path

import pytest

from scripts.feed_parser import parse_feed_bytes

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = {"id": "fixture", "name": "Fixture Publisher", "language": "en", "qualityWeight": 1.1}


def test_rss_parsing_with_namespaced_image():
    articles = parse_feed_bytes((FIXTURES / "rss.xml").read_bytes(), SOURCE, "US")
    assert len(articles) == 1
    article = articles[0]
    assert article["title"] == "City council approves transit plan"
    assert article["imageUrl"].endswith("transit.jpg")
    assert article["publishedAt"].startswith("2026-07-19T14:30:00")


def test_atom_parsing():
    articles = parse_feed_bytes((FIXTURES / "atom.xml").read_bytes(), SOURCE, "US")
    assert len(articles) == 1
    assert articles[0]["publisherArticleId"] == "tag:example.org,2026:2"
    assert articles[0]["imageUrl"].endswith("report.jpg")


def test_malformed_xml_without_entries_fails():
    with pytest.raises(ValueError):
        parse_feed_bytes(b"<rss><channel><item>", SOURCE, "US")


def test_empty_source_response_returns_no_articles():
    payload = b"<?xml version='1.0'?><rss version='2.0'><channel><title>Empty</title></channel></rss>"
    assert parse_feed_bytes(payload, SOURCE, "US") == []
