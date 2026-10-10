"""Build an evidence-grounded, positive editorial brief for local Qwen.

Each prompt contains the correct statistical subject and reference phrase.
Never infer a missing baseline value, cause, or historical pattern.
"""
from __future__ import annotations

import re


def _italian_number(value: object, decimals: int = 0) -> str:
    if decimals:
        return f"{float(value):.{decimals}f}".replace(".", ",")
    return f"{int(value):,}".replace(",", ".")


def _period(period: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"(20\d\d)-Q([1-4])", str(period or ""))
    if not match:
        return None
    year, quarter = map(int, match.groups())
    ordinal = ["primo", "secondo", "terzo", "quarto"][quarter-1]
    return f"{ordinal} trimestre {year}", f"{ordinal} trimestre {year - 1}"


def source_scope(fact: dict) -> dict:
    indicator = str(fact.get("indicator") or "").strip().casefold()
    segment = str(fact.get("segment") or "").casefold()
    if not ("alberghier" in segment and indicator in ("arrivi", "presenze")):
        return {}
    nonresident = bool(re.search(r"\bnon[\s-]?residenti\b", segment))
    resident = bool(re.search(r"\bresidenti\b", segment)) and not nonresident
    population = ("non residenti" if nonresident else "residenti" if resident else "totale")
    subject = "gli arrivi" if indicator == "arrivi" else "le presenze"
    clientele = (
        "dei clienti non residenti " if nonresident else
        "dei clienti residenti " if resident else ""
    )
    phrase = f"{subject} {clientele}negli esercizi alberghieri"
    return {
        "kind": "tourist_accommodation",
        "population": population,
        "indicator": indicator,
        "required_headline_term": indicator,
        "required_cohort_term": population if population != "totale" else None,
        "subject_phrase": phrase,
        "official_accommodation": "esercizi alberghieri",
    }


def editorial_brief(fact: dict) -> dict:
    scope = source_scope(fact)
    period = _period(fact.get("period") or "")
    out = {
        "indicator": fact["indicator"],
        "unit": fact["unit"],
        "reference_period": fact["period"],
        "published_value": fact["value"],
        "source_segment": fact.get("segment"),
        "reported_yoy_change_pct": fact.get("change_pct"),
        "evidence_location": fact.get("source_location"),
    }
    if scope:
        out["exact_statistical_subject"] = scope["subject_phrase"]
        out["population_scope"] = scope["population"]
        out["accommodation_scope"] = scope["official_accommodation"]
    if period:
        out["reference_period_in_italian"] = period[0]
        if fact.get("change_pct") is not None:
            out["official_comparison_period"] = period[1]
    if scope and period and fact.get("change_pct") is not None:
        change = float(fact["change_pct"])
        movement = "in calo" if change < 0 else "in aumento" if change > 0 else "invariati"
        pct = _italian_number(abs(change), decimals=1)
        # No inferred prior absolute values: this is a narrative grounding
        # sentence, not an additional statistical claim.
        qualifier = ("dell'" if pct[0] in "18" else "del ")
        signed = f"{movement} {qualifier}{pct}%"
        value = _italian_number(fact["value"])
        unit = " notti" if scope["indicator"] == "presenze" else ""
        verb = "sono state" if scope["indicator"] == "presenze" else "sono stati"
        out["canonical_reference_sentence"] = (
            f"Nel {period[0]}, {scope['subject_phrase']} {verb} "
            f"{value}{unit}, {signed} rispetto al {period[1]}."
        )
    return out
