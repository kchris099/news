import json
from pathlib import Path

from scripts.validate_output import validate_day, validate_repository

ROOT = Path(__file__).resolve().parents[2]


def test_sample_repository_manifest_and_days_validate():
    assert validate_repository(ROOT) == []


def test_invalid_image_scheme_is_rejected():
    country = json.loads((ROOT / "config" / "countries.json").read_text(encoding="utf-8"))[0]
    date_key = next(iter(json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))["countries"]["US"]["dates"]))
    payload = json.loads((ROOT / "data" / "US" / f"{date_key}.json").read_text(encoding="utf-8"))
    payload["articles"][0]["imageUrl"] = "http://example.com/image.jpg"
    errors = validate_day(payload, country)
    assert "article imageUrl must use https" in errors
