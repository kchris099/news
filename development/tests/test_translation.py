import asyncio

from scripts.translate import translate_articles


def test_translation_is_optional_and_original_is_preserved(monkeypatch):
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)
    article = {"id": "a", "title": "Original headline", "language": "ja", "translatedTitle": None}
    asyncio.run(translate_articles([article], {"translation": {"provider": "none"}}, {}))
    assert article["title"] == "Original headline"
    assert article["translatedTitle"] is None
