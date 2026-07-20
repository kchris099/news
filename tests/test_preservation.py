from scripts.aggregate_news import suspicious_drop

SETTINGS = {"minimumSafeArticleCount": 8, "suspiciousDropRatio": 0.35}


def test_suspicious_drop_protects_existing_archive():
    assert suspicious_drop(5, 40, SETTINGS)


def test_reasonable_refresh_can_replace_existing_archive():
    assert not suspicious_drop(30, 40, SETTINGS)


def test_no_existing_archive_does_not_trigger_retention():
    assert not suspicious_drop(0, 0, SETTINGS)
