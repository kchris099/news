import asyncio

from scripts.translate import needs_translation, translate_articles


def test_non_latin_headline_is_translated_even_when_feed_marks_it_english():
    assert needs_translation({"language": "en", "title": "「いかのおすし」で子どもを守って"})
    assert not needs_translation({"language": "en", "title": "Japan headlines"})


def test_translation_is_optional_and_original_is_preserved(monkeypatch):
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)
    article = {"id": "a", "title": "Original headline", "language": "ja", "translatedTitle": None}
    asyncio.run(translate_articles([article], {"translation": {"provider": "none"}}, {}))
    assert article["title"] == "Original headline"
    assert article["translatedTitle"] is None
