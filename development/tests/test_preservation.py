from scripts.aggregate_news import (
    flatten_existing_articles,
    latest_refresh_dates,
    merge_country_manifest_dates,
    suspicious_drop,
)

SETTINGS = {"minimumSafeArticleCount": 8, "suspiciousDropRatio": 0.35}


def test_suspicious_drop_protects_existing_archive():
    assert suspicious_drop(5, 40, SETTINGS)


def test_reasonable_refresh_can_replace_existing_archive():
    assert not suspicious_drop(30, 40, SETTINGS)


def test_no_existing_archive_does_not_trigger_retention():
    assert not suspicious_drop(0, 0, SETTINGS)


def test_latest_refresh_preserves_previous_archive_days():
    current = {"name": "United States", "timeZone": "America/New_York", "dates": {
        "2026-07-20": {"status": "current"},
    }}
    previous = {"name": "United States", "timeZone": "America/New_York", "dates": {
        "2026-07-19": {"status": "retained"},
        "2026-07-18": {"status": "current"},
    }}
    result = merge_country_manifest_dates(
        current,
        previous,
        ["2026-07-20", "2026-07-19", "2026-07-18"],
    )
    assert list(result["dates"]) == ["2026-07-20", "2026-07-19", "2026-07-18"]
    assert result["dates"]["2026-07-20"]["status"] == "current"
    assert result["dates"]["2026-07-19"]["status"] == "retained"


def test_retained_articles_drop_non_image_media_urls():
    payload = {
        "articles": [{
            "title": "Video report", "imageUrl": "https://cdn.example.com/report.mp4",
            "publishedAt": "2026-07-19T12:00:00Z", "sourceQuality": 1.0,
        }],
    }
    assert flatten_existing_articles(payload)[0]["imageUrl"] is None


def test_latest_refresh_backfills_manifest_dates_missing_at_local_midnight(tmp_path):
    country_dir = tmp_path / "data" / "US"
    country_dir.mkdir(parents=True)
    (country_dir / "2026-07-18.json").write_text("{}", encoding="utf-8")
    previous = {"dates": {
        "2026-07-18": {"status": "current", "path": "data/US/2026-07-18.json"},
    }}

    assert latest_refresh_dates(
        tmp_path,
        ["2026-07-20", "2026-07-19", "2026-07-18"],
        previous,
    ) == ["2026-07-20", "2026-07-19"]
