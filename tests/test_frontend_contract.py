from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
