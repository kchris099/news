from scripts.aggregate_news import keep_existing_article, keep_provider_article


COUNTRY = {
    "code": "US",
    "sources": [
        {"id": "cnn", "name": "CNN", "homepage": "https://www.cnn.com/", "qualityWeight": 1.1},
        {"id": "nyt", "name": "The New York Times", "homepage": "https://www.nytimes.com/", "qualityWeight": 1.2},
    ],
}


def test_provider_articles_from_unlisted_domains_are_excluded():
    article = {"dataSource": "gdelt", "publisherUrl": "https://finance.yahoo.com/", "sourceQuality": 0.78}
    assert not keep_provider_article(article, COUNTRY)


def test_provider_articles_use_curated_publisher_metadata():
    article = {"dataSource": "google-news", "publisherUrl": "https://www.cnn.com/", "sourceName": "Google News"}
    assert keep_provider_article(article, COUNTRY)
    assert article["sourceName"] == "CNN"
    assert article["sourceQuality"] == 1.1


def test_retained_articles_cannot_reintroduce_unlisted_domains():
    article = {"dataSources": ["gdelt"], "sourceDomain": "finance.yahoo.com"}
    assert not keep_existing_article(article, COUNTRY)
