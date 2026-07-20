from scripts.aggregate_news import is_excluded_article, keep_existing_article, keep_provider_article


COUNTRY = {
    "code": "US",
    "sources": [
        {"id": "cnn", "name": "CNN", "homepage": "https://www.cnn.com/", "qualityWeight": 1.1},
        {"id": "nyt", "name": "The New York Times", "homepage": "https://www.nytimes.com/", "qualityWeight": 1.2},
    ],
}

KOREA = {
    "code": "KR",
    "excludedTitles": ["[알림] 연합뉴스 콘텐츠 저작권 고지"],
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


def test_korea_excludes_yonhap_copyright_notice_title():
    article = {"title": "[알림] 연합뉴스 콘텐츠 저작권 고지"}
    assert is_excluded_article(article, KOREA)
    assert not keep_existing_article(article, KOREA)


def test_korea_keeps_real_yonhap_headlines():
    article = {"title": "정부, 새로운 경제 정책 발표", "sourceDomain": "yna.co.kr"}
    assert not is_excluded_article(article, KOREA)
