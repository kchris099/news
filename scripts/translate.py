from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .utilities import iso_z, stable_hash

ENGLISH_CODES = {"en", "en-us", "en-gb", "english"}


async def translate_articles(
    articles: list[dict[str, Any]],
    settings: dict[str, Any],
    cache: dict[str, Any],
) -> None:
    provider = os.getenv("TRANSLATION_PROVIDER", settings.get("translation", {}).get("provider", "none")).lower()
    if provider in {"", "none", "disabled"}:
        return
    if provider != "deepl":
        raise ValueError(f"Unsupported translation provider: {provider}")
    api_key = os.getenv("DEEPL_API_KEY")
    if not api_key:
        return
    endpoint = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
    semaphore = asyncio.Semaphore(2)

    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.get("userAgent", "Worldline/1.0")}) as client:
        async def translate_one(article: dict[str, Any]) -> None:
            language = str(article.get("language") or "").casefold()
            if language in ENGLISH_CODES or language.startswith("en-"):
                return
            key = stable_hash(article["id"], article["title"], "deepl", length=32)
            cached = cache.get(key)
            if cached and cached.get("sourceTitle") == article["title"]:
                article["translatedTitle"] = cached.get("translatedTitle")
                article["translationProvider"] = "DeepL"
                article["translationGeneratedAt"] = cached.get("generatedAt")
                return
            async with semaphore:
                try:
                    response = await client.post(
                        endpoint,
                        data={"text": article["title"], "target_lang": "EN-US"},
                        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
                    )
                    response.raise_for_status()
                    translated = response.json()["translations"][0]["text"].strip()
                    if translated and translated.casefold() != article["title"].casefold():
                        generated_at = iso_z()
                        article["translatedTitle"] = translated
                        article["translationProvider"] = "DeepL"
                        article["translationGeneratedAt"] = generated_at
                        cache[key] = {
                            "sourceTitle": article["title"],
                            "translatedTitle": translated,
                            "generatedAt": generated_at,
                        }
                except (httpx.HTTPError, KeyError, IndexError, ValueError):
                    return

        await asyncio.gather(*(translate_one(article) for article in articles))
