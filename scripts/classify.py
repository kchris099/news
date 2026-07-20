from __future__ import annotations

import re
from typing import Any

CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "Business": ("business", "economy", "economic", "market", "stocks", "bank", "company", "trade", "inflation", "earnings", "finance"),
    "Technology": ("technology", "tech", "software", "artificial intelligence", " ai ", "chip", "cyber", "internet", "startup", "smartphone"),
    "Culture": ("culture", "film", "movie", "music", "book", "museum", "art", "television", "festival", "celebrity"),
    "Sports": ("sports", "football", "soccer", "baseball", "basketball", "tennis", "cricket", "olympic", "league", "match", "tournament"),
    "Science & Health": ("science", "health", "medical", "hospital", "disease", "vaccine", "research", "climate", "space", "nasa", "doctor"),
}

WORLD_TERMS = ("united nations", "foreign", "international", "global", "war", "diplomatic", "border", "refugee", "sanctions")


def classify_article(article: dict[str, Any], country: dict[str, Any]) -> None:
    text = f" {article.get('title', '')} {article.get('description') or ''} ".casefold()
    aliases = [str(alias).casefold() for alias in country.get("aliases", []) if alias]
    domestic_hits = sum(1 for alias in aliases if alias and alias in text)
    if article.get("sourceCountry") == country["code"] and article.get("dataSources") != ["gdelt"]:
        domestic_hits += 1
    if domestic_hits:
        article["coverageCountries"] = [country["code"]]

    hint = article.pop("categoryHint", None)
    if hint in CATEGORY_RULES or hint in {"Domestic", "World"}:
        article["category"] = hint
        return

    scores: dict[str, int] = {}
    for category, terms in CATEGORY_RULES.items():
        matches = 0
        for term in terms:
            if term.strip() != term:
                matches += int(term in text)
            else:
                matches += len(re.findall(rf"\b{re.escape(term)}\b", text))
        scores[category] = matches

    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score >= 2:
        article["category"] = best_category
    elif domestic_hits >= 1:
        article["category"] = "Domestic"
    elif sum(1 for term in WORLD_TERMS if term in text) >= 1:
        article["category"] = "World"
    else:
        article["category"] = "General"
