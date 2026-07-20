from datetime import datetime, timezone

from scripts.utilities import date_key_for_timestamp, local_date_keys, local_day_window


def test_exactly_seven_local_dates():
    now = datetime(2026, 7, 20, 0, 30, tzinfo=timezone.utc)
    dates = local_date_keys("America/Los_Angeles", 7, now)
    assert dates == ["2026-07-19", "2026-07-18", "2026-07-17", "2026-07-16", "2026-07-15", "2026-07-14", "2026-07-13"]


def test_country_time_zones_can_have_different_today():
    now = datetime(2026, 7, 20, 0, 30, tzinfo=timezone.utc)
    assert local_date_keys("America/New_York", 1, now)[0] == "2026-07-19"
    assert local_date_keys("Asia/Tokyo", 1, now)[0] == "2026-07-20"


def test_daylight_saving_spring_day_is_23_hours():
    start, end = local_day_window("2026-03-08", "America/New_York")
    assert (end - start).total_seconds() == 23 * 3600


def test_daylight_saving_fall_day_is_25_hours():
    start, end = local_day_window("2026-11-01", "America/New_York")
    assert (end - start).total_seconds() == 25 * 3600


def test_timestamp_is_assigned_to_country_local_date():
    timestamp = datetime(2026, 7, 20, 0, 15, tzinfo=timezone.utc)
    assert date_key_for_timestamp(timestamp, "America/New_York") == "2026-07-19"
    assert date_key_for_timestamp(timestamp, "Asia/Tokyo") == "2026-07-20"
