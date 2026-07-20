from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_project_page_assets_use_relative_paths():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'href="/assets/' not in html
    assert 'src="/assets/' not in html
    assert 'href="assets/css/styles.css"' in html


def test_frontend_guarantees_seven_date_controls_from_time_zone():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Array.from({ length: 7 }" in js
    assert "dates found" not in js.lower()


def test_no_hard_coded_fallback_headlines_in_frontend():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "fallback headline" not in js.lower()


def test_country_switches_open_local_today():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    change_country = js[js.index("async function changeCountry"):js.index("function renderDateTabs")]
    assert "state.date = latestPreparedDate(country.code, country.timeZone);" in change_country
    assert "state.dateFallback = state.date !== dates[0];" in change_country


def test_missing_today_falls_back_to_latest_prepared_archive_day():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function latestPreparedDate(countryCode, timeZone)" in js
    assert "Today's archive is not ready yet." in js
    assert "usableStatuses" in js
