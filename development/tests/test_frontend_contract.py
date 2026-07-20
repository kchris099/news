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
    assert "state.dateFallback" not in change_country


def test_missing_today_falls_back_to_latest_prepared_archive_day():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function latestPreparedDate(countryCode, timeZone)" in js
    assert "usableStatuses" in js


def test_missing_today_uses_preparation_message_without_fallback_warning():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "News is being prepared. Check back later!" in js
    assert "This archive file is currently unavailable." not in js
    assert "Today's archive is not ready yet." not in js
    assert "function isTodayDate(dateKey)" in js


def test_frontend_filters_to_configured_active_countries():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "settings.activeCountries" in js
    assert "activeCodes.has(country.code)" in js


def test_production_copy_does_not_use_legacy_missing_archive_warning():
    for relative_path in ("index.html", "about.html", "assets/js/app.js"):
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "Archive File Missing" not in content
        assert "This archive file is currently unavailable." not in content
