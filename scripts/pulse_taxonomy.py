"""ISTAT PULSE taxonomy 1.0 — conservative, deterministic classification.

The registry lives in data/taxonomy/pulse_taxonomy_v1.json and is mirrored
byte-for-byte in Android app assets. This module never changes PULSE Score.
Model-assisted decisions may replace provisional suggestions after validation.
"""
from __future__ import annotations
from pathlib import Path
import json
import re
import unicodedata

TAXONOMY_VERSION = "1.0"
UNCLASSIFIED = "NON_CLASSIFICATO"
ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "taxonomy" / "pulse_taxonomy_v1.json"


def normalize(value: str) -> str:
    ascii_text = "".join(ch for ch in unicodedata.normalize("NFD", (value or "").casefold())
                         if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def load_topics(catalog: Path = CATALOG) -> list[dict]:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    if data.get("version") != TAXONOMY_VERSION:
        raise ValueError("Unsupported taxonomy version")
    groups = data.get("groups", [])
    topics = [topic for group in groups for topic in group.get("categories", [])]
    if len(groups) != 7 or len(topics) != 57 or len({t["code"] for t in topics}) != 57:
        raise ValueError("Taxonomy incomplete, must have 7 groups and 57 unique codes")
    return topics


def classify(text: str, topics: list[dict] | None = None) -> dict:
    topics = topics if topics is not None else load_topics()
    content = f" {normalize(text[:2400])} "
    ranked = []
    for topic in topics:
        match = {normalize(k) for k in topic.get("keywords", [])}
        hits = sum(1 for key in match if key and f" {key} " in content)
        ranked.append((hits, topic["code"]))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    top_hits, code = ranked[0] if ranked else (0, UNCLASSIFIED)
    runner_up = ranked[1][0] if len(ranked) > 1 else 0
    if top_hits < 2 or top_hits <= runner_up:
        return {
            "primary_category": UNCLASSIFIED,
            "classification_status": "review_needed",
            "classification_reason": "Evidence insufficient to assign a unique thematic category",
        }
    return {
        "primary_category": code,
        "classification_status": "provisional",
        "classification_reason": f"Deterministic taxonomy keyword rule ({top_hits} matching terms); human/AI validation pending",
    }


def enrich_article(article: dict, topics: list[dict] | None = None) -> dict:
    topics = topics if topics is not None else load_topics()
    valid_codes = {topic["code"] for topic in topics}
    existing = article.get("primary_category")
    output = dict(article)
    # Preserve a prior validated decision; never overwrite it with a weaker rule.
    if existing in valid_codes and article.get("classification_status") == "validated":
        output.setdefault("taxonomy_version", TAXONOMY_VERSION)
        output.setdefault("classification_method", "manual")
        output.setdefault("secondary_categories", [])
        return output
    combined = " ".join(str(article.get(field) or "") for field in (
        "topic", "headline", "summary", "pulse_title", "pulse_summary"
    ))
    result = classify(combined, topics)
    output.update(result)
    output["taxonomy_version"] = TAXONOMY_VERSION
    output["classification_method"] = "rules"
    output["secondary_categories"] = []
    # territories, source, score and statistical evidence remain untouched.
    return output
