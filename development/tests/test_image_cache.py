import asyncio

from scripts.aggregate_news import sanitize_article_images, sanitize_image_cache
from scripts.feed_parser import enrich_missing_images
from scripts.google_news_client import enrich_google_images


class NeverFetch:
    async def get(self, *args, **kwargs):
        raise AssertionError("unsafe cached image should not be attached")


def test_image_cache_scrubber_drops_unsafe_urls():
    cache = {
        "https://publisher.example/story": {"imageUrl": "http://cdn.example/image.jpg"},
        "https://publisher.example/valid": {"imageUrl": "https://cdn.example/image.jpg"},
    }

    sanitize_image_cache(cache)

    assert cache["https://publisher.example/story"]["imageUrl"] is None
    assert cache["https://publisher.example/valid"]["imageUrl"] == "https://cdn.example/image.jpg"


def test_publisher_cache_hit_cannot_attach_unsafe_image():
    article = {
        "url": "https://publisher.example/story",
        "dataSource": "publisher-rss",
    }
    cache = {article["url"]: {"imageUrl": "http://cdn.example/image.jpg"}}

    asyncio.run(enrich_missing_images(NeverFetch(), [article], cache))

    assert article.get("imageUrl") is None


def test_google_cache_hit_cannot_attach_unsafe_image():
    article = {
        "url": "https://news.google.com/rss/articles/token",
        "dataSource": "google-news",
        "dataSources": ["google-news"],
        "sourceDomain": "publisher.example",
    }
    cache = {
        article["url"]: {
            "articleUrl": "https://publisher.example/story",
            "imageUrl": "http://cdn.example/image.jpg",
        }
    }

    asyncio.run(enrich_google_images(NeverFetch(), [article], cache, "en-US"))

    assert article["url"] == "https://publisher.example/story"
    assert article.get("imageUrl") is None


def test_final_article_image_sanitizer_cleans_related_articles():
    articles = [{
        "imageUrl": "http://cdn.example/image.jpg",
        "related": [{"imageUrl": "http://cdn.example/related.jpg"}],
    }]

    sanitize_article_images(articles)

    assert articles[0]["imageUrl"] is None
    assert articles[0]["related"][0]["imageUrl"] is None
