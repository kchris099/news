from pathlib import Path

import pytest

from scripts.feed_parser import extract_page_image, parse_feed_bytes

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


def test_video_media_does_not_hide_thumbnail_image():
    content = b'''<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>Video story</title><link>https://example.com/video-story</link><pubDate>Sun, 19 Jul 2026 14:30:00 GMT</pubDate><media:content url="https://cdn.example.com/story.mp4" medium="video" type="video/mp4" /><media:thumbnail url="https://cdn.example.com/story.jpg" /></item></channel></rss>'''
    articles = parse_feed_bytes(content, SOURCE, "US")
    assert articles[0]["imageUrl"] == "https://cdn.example.com/story.jpg"


def test_enclosure_url_is_supported():
    content = b'''<?xml version="1.0"?><rss version="2.0"><channel><item><title>Enclosure story</title><link>https://example.com/enclosure-story</link><pubDate>Sun, 19 Jul 2026 14:30:00 GMT</pubDate><enclosure url="https://cdn.example.com/story.jpg" type="image/jpeg" /></item></channel></rss>'''
    articles = parse_feed_bytes(content, SOURCE, "US")
    assert articles[0]["imageUrl"] == "https://cdn.example.com/story.jpg"


def test_page_image_metadata_accepts_content_before_property():
    content = b'''<html><head><meta content="https://cdn.example.com/story.jpg" property="og:image"><meta name="twitter:image" content="https://cdn.example.com/other.jpg"></head></html>'''
    assert extract_page_image(content, "https://example.com/story") == "https://cdn.example.com/story.jpg"


def test_malformed_xml_without_entries_fails():
    with pytest.raises(ValueError):
        parse_feed_bytes(b"<rss><channel><item>", SOURCE, "US")


def test_empty_source_response_returns_no_articles():
    payload = b"<?xml version='1.0'?><rss version='2.0'><channel><title>Empty</title></channel></rss>"
    assert parse_feed_bytes(payload, SOURCE, "US") == []


def test_google_news_entries_keep_publisher_identity():
    source = {"id": "google-news", "name": None, "qualityWeight": 0.82}
    content = b'''<?xml version="1.0"?><rss><channel><item><title>Headline</title><link>https://news.google.com/rss/articles/example</link><source url="https://www.cnn.com/">CNN</source><pubDate>Sun, 19 Jul 2026 20:00:00 GMT</pubDate></item></channel></rss>'''
    articles = parse_feed_bytes(content, source, "US", "google-news")
    assert articles[0]["sourceName"] == "CNN"
    assert articles[0]["publisherUrl"] == "https://www.cnn.com/"
