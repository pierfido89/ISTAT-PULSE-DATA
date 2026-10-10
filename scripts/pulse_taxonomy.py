#!/usr/bin/env python3
"""Conservative, versioned offline topic classification; no LLM or network dependency."""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "pulse_taxonomy_v1.json"
UNCLASSIFIED = "NON_CLASSIFICATO"


def _norm(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", "".join(
        char for char in raw if not unicodedata.combining(char)
    ))).strip()


def _hits(text: str, phrase: str) -> bool:
    # Keyword hints are Italian stems or complete phrases. Match at a token
    # boundary: "pil" must not match "pilota", while "natalit" finds "natalità".
    hint = _norm(phrase)
    if not hint:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(hint), text) is not None


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    subs = [s for a in cfg["macroareas"] for s in a["subcategories"]]
    assert cfg["taxonomy_version"] == "1.0"
    assert len(cfg["macroareas"]) == 7 and len(subs) == 57
    assert len({s["code"] for s in subs}) == 57
    return cfg


def classify(title: str, summary: str = "", taxonomy: dict | None = None) -> dict:
    taxonomy = taxonomy or load_taxonomy()
    title_norm, summary_norm = _norm(title), _norm(summary)
    ranked = []
    for area in taxonomy["macroareas"]:
        for sub in area["subcategories"]:
            hints = sub.get("keywords", [])
            title_hits = sum(1 for h in hints if _hits(title_norm, h))
            summary_hits = sum(1 for h in hints if _hits(summary_norm, h))
            score = title_hits * 5 + summary_hits * 2
            if score:
                ranked.append((score, title_hits, sub["code"]))
    ranked.sort(key=lambda x: (-x[0], -x[1], x[2]))
    best = ranked[0] if ranked else None
    next_best = ranked[1] if len(ranked) > 1 else None
    ambiguous = best is not None and next_best is not None and (
        best[:2] == next_best[:2]
    )
    valid = best is not None and best[0] >= 5 and not ambiguous
    primary = best[2] if valid else UNCLASSIFIED
    secondary = []
    if valid:
        secondary = [score[2] for score in ranked[1:] if score[0] >= 5][:2]
    return {
        "taxonomy_version": taxonomy["taxonomy_version"],
        "primary_category": primary,
        "secondary_categories": secondary,
        "classification_method": "rules",
        "classification_status": "provisional" if valid else "review_needed",
        "classification_reason": (
            f"Keyword match in title/summary (score {best[0]}; manual review recommended)."
            if valid else "Insufficient or ambiguous topic evidence."
        )
    }


def enrich_articles(articles: list[dict], taxonomy: dict | None = None) -> None:
    """Mutates only taxonomy metadata; does not change publication eligibility."""
    taxonomy = taxonomy or load_taxonomy()
    for article in articles:
        title = article.get("headline", "") or article.get("pulse_title", "")
        description = " ".join(
            str(article.get(k) or "") for k in ("summary", "pulse_summary")
        )
        existing = article.get("taxonomy")
        if isinstance(existing, dict) and existing.get("classification_status") == "validated" \
            and existing.get("taxonomy_version") == taxonomy["taxonomy_version"]:
            continue
        article["taxonomy"] = classify(title, description, taxonomy)
