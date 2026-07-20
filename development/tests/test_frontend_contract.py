from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_project_page_assets_use_relative_paths():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'href="/assets/' not in html
    assert 'src="/assets/' not in html
    assert 'href="assets/css/styles.css"' in html
    assert 'src="assets/js/app.js?v=5"' in html


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


def test_bare_entry_route_ignores_saved_country():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    restore_initial_state = js[js.index("function restoreInitialState"):js.index("function restoreStateFromUrl")]
    assert "state.countryCode = urlCountry || state.settings.defaultCountry || 'US';" in restore_initial_state
    assert "normalizeCountry(savedCountry)" not in restore_initial_state
    assert "if (params.has('country') || params.has('date')) writeUrl('replace');" in restore_initial_state


def test_bare_entry_route_resets_after_back_forward_cache_restore():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "window.addEventListener('pageshow', handlePageShow);" in js
    page_show = js[js.index("async function handlePageShow"):js.index("async function init")]
    assert "event.persisted" in page_show
    assert "location.search" in page_show
    assert "restoreInitialState();" in page_show


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


def test_initial_shell_avoids_fullscreen_loading_splash_without_control_flash():
    css = (ROOT / "assets" / "css" / "styles.css").read_text(encoding="utf-8")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "html.app-loading body::before" not in css
    assert "html.app-loading body > *" not in css
    assert "html.app-loading .country-tabs" in css
    assert "html.app-loading .date-tabs" in css
    assert '<span class="sr-only">Loading headlines</span>' in html


def test_headline_clamps_match_rank_and_breakpoint_rules():
    css = (ROOT / "assets" / "css" / "styles.css").read_text(encoding="utf-8")
    lead_title = css[css.index(".lead-title {"):css.index(".lead-title a")]
    story_title = css[css.index(".story-title {"):css.index(".story-title a")]
    mobile = css[css.index("@media (max-width: 767px)"):css.index("@media (max-width: 639px)")]
    assert "-webkit-line-clamp: 3" in lead_title
    assert "line-height: 1.24" in lead_title
    assert "-webkit-line-clamp: 4" in story_title
    assert ".lead-title { font-size: clamp(2.05rem, 7vw, 3rem); line-clamp: 4; -webkit-line-clamp: 4; }" in mobile
    assert "z-index: 3" in lead_title
    assert "z-index: 2" in story_title
    assert "padding-bottom: 0" in css


def test_production_copy_does_not_use_legacy_missing_archive_warning():
    for relative_path in ("index.html", "about.html", "assets/js/app.js"):
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "Archive File Missing" not in content
        assert "This archive file is currently unavailable." not in content


def test_non_english_headlines_have_client_translation_fallback():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    assert "translate.googleapis.com/translate_a/single" in js
    assert "tl=en" in js
    assert "TRANSLATION_CACHE_KEY" in js
    assert "isNonEnglishArticle" in js


def test_translated_headlines_use_an_accessible_blue_dot():
    js = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "assets" / "css" / "styles.css").read_text(encoding="utf-8")
    assert "translation-dot" in js
    assert "Translated headline" in js
    assert ".translation-dot" in css
    assert "translation-label" not in js
    assert "translation-label" not in css
