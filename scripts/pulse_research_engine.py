#!/usr/bin/env python3
"""PULSE Research Engine 3.0: read ALL verified findings in a workbench.

No model, network, API, APK, publishing, or PULSE Score. Detects sourced
journalistic story angles within the subset supported by an explicit
relationship contract (currently same-source tourist arrivals+presences).
Missing history/territory is reported, not fabricated. Ranking is a
transparent editorial QUEUE heuristic, never a statistical significance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

try:
    from scripts.pulse_editorial_ai import _read_input, candidates
    from scripts.pulse_editorial_pairs import paired_candidates, grounded_story, FORBIDDEN_OUTPUTS
    from scripts.pulse_research_comparisons import historical_signals, territorial_signals
    from scripts.pulse_research_reading import match_passages, research_narrative_leads
    from scripts.pulse_research_labor import labor_research_signals
except ModuleNotFoundError:
    from pulse_editorial_ai import _read_input, candidates
    from pulse_editorial_pairs import paired_candidates, grounded_story, FORBIDDEN_OUTPUTS
    from pulse_research_comparisons import historical_signals, territorial_signals
    from pulse_research_reading import match_passages, research_narrative_leads
    from pulse_research_labor import labor_research_signals

MAX_RESEARCH_PAIRS = 10


def angle_options(pair: dict) -> list[dict]:
    """Every offered angle requires its OWN independently checked witness."""
    a, p = pair["evidence"]
    story = grounded_story(pair)
    derived = story["calculated_metric"]
    options = []
    opposite = a["change_pct"] * p["change_pct"] < 0
    if opposite:
        options.append({
            "id": "opposite_directions",
            "title": "Arrivi e presenze in direzioni opposte",
            "proven_by": ["arrival_change_pct", "nights_change_pct"],
            "description": "Contrast between two official same-quarter YoY changes",
        })
    elif a["change_pct"] * p["change_pct"] > 0:
        options.append({
            "id": "parallel_changes",
            "title": "Arrivi e presenze nella stessa direzione",
            "proven_by": ["arrival_change_pct", "nights_change_pct"],
            "description": "Two official changes with the same sign",
        })
    if derived:
        options.append({
            "id": "average_stay_calculated",
            "title": "Permanenza media calcolata",
            "proven_by": ["arrival_total", "nights_total", "methodology"],
            "description": "Auditable presences/arrivals ratio; not a source-published table cell",
            "derived_metric": derived,
        })
    return options


def _ranking(pair: dict, options: list[dict]) -> dict:
    """NOT PULSE Score: rule-based editor ordering, no inference of significance."""
    a, p = pair["evidence"]
    reasons = []
    points = 0
    if any(x["id"] == "opposite_directions" for x in options):
        points += 45
        reasons.append("two_official_yoy_rates_with_opposite_signs")
    elif any(x["id"] == "parallel_changes" for x in options):
        points += 15
        reasons.append("two_official_yoy_rates_with_same_sign")
    if any(x["id"] == "average_stay_calculated" for x in options):
        points += 25
        reasons.append("reproducible_derived_ratio_from_matched_totals")
    if pair["population"] in ("residenti", "non residenti"):
        points += 10
        reasons.append("specific_documented_customer_population")
    # Real difference in rates, but its magnitude is NOT a test of
    # significance or a formal PULSE pattern.
    spread = abs(float(a["change_pct"]) - float(p["change_pct"]))
    if spread >= 5:
        points += 10
        reasons.append("official_yoy_percentage_points_apart_at_least_five")
    elif spread >= 2:
        points += 5
        reasons.append("official_yoy_percentage_points_apart_at_least_two")
    return {
        "priority_points": points,
        "queue_tier": "alta" if points >= 70 else "media" if points >= 40 else "bassa",
        "rule_id": "paired_tourism_queue_v1",
        "ranking_reasons": reasons,
        "not_pulse_score": True,
        "not_statistical_significance": True,
    }


def research_report(articles: list[dict], limit: int = MAX_RESEARCH_PAIRS) -> dict:
    if not 1 <= limit <= MAX_RESEARCH_PAIRS:
        raise ValueError("Invalid candidate limit")
    pool = {}
    extracted_count = 0
    for article in articles:
        extracted_count += len(article.get("document_findings") or [])
        for item in candidates(article, limit=20):
            pool[item["candidate_id"]] = item
    pairs = paired_candidates(articles, limit=MAX_RESEARCH_PAIRS)
    history = historical_signals(articles)
    territory = territorial_signals(articles)
    labor = labor_research_signals(articles)
    readings = {}
    publication_coverage = []
    for article in articles:
        reading = article.get("document_reading")
        source_url = (article.get("public_source") or {}).get("url")
        evidence_hashes = {
            str(f.get("source_sha256"))
            for f in (article.get("document_findings") or [])
            if isinstance(f, dict) and f.get("verified") is True
        }
        authentic = (
            isinstance(reading, dict)
            and reading.get("source_url") == source_url
            and (
                reading.get("source_sha256") in evidence_hashes
                or reading.get("source_sha256") == article.get("source_sha256")
            )
            and len(str(reading.get("source_sha256") or "")) == 64
        )
        if authentic:
            readings[(source_url, reading["source_sha256"])] = reading
        publication_coverage.append({
            "article_id": article.get("id"),
            "source_url": source_url,
            "full_text_layer_attached": authentic,
            "pdf_pages_total": reading.get("pdf_pages_total") if authentic else None,
            "pdf_pages_scanned": reading.get("pdf_pages_scanned") if authentic else None,
            "text_pages_scanned": reading.get("text_pages_scanned") if authentic else None,
            "passages_count": reading.get("passages_count") if authentic else 0,
            "complete_text_layer": reading.get("complete_text_layer") if authentic else False,
            "coverage_warnings": reading.get("coverage_warnings", []) if authentic else [
                "no_matching_full_pdf_text_layer"
            ],
        })
    records = []
    for pair in pairs:
        story = grounded_story(pair)
        options = angle_options(pair)
        if not options:
            continue
        record = {
            "pair_id": pair["id"], "source_article_id": pair["source_article_id"],
            "period": pair["period"], "segment": pair["segment"],
            "source_url": pair["evidence"][0]["source_url"],
            "source_sha256": pair["evidence"][0]["source_sha256"],
            "source_locations": [fact["source_location"] for fact in pair["evidence"]],
            "headline_grounded": story["headline"],
            "lead_grounded": story["lead"],
            "body_grounded": story["body"],
            "evidence": pair["evidence"],
            "narrative_context": match_passages(
                readings.get((pair["evidence"][0]["source_url"],
                              pair["evidence"][0]["source_sha256"]), {}),
                ["arrivi", "presenze"], max_results=5
            ),
            "context_is_not_numeric_proof": True,
            "angles": options,
            "ranking": _ranking(pair, options),
            "candidate_status": "requires_human_editorial_review",
            "publication_status": "research_only",
            "pulse_score": None,
        }
        records.append(record)
    records.sort(key=lambda r: (
        -r["ranking"]["priority_points"], r["pair_id"]
    ))
    narrative_leads = []
    for reading in readings.values():
        narrative_leads.extend(
            research_narrative_leads(reading, max_results=20)
        )
    # Narrative leads are NOT statistically verified article candidates.
    # They belong to a separate editor's research queue, never in the
    # verified-angle list consumed by Editorial Intelligence.
    narrative_leads.sort(key=lambda r: (
        -r["editorial_heuristic_points"], r["source_url"], r["source_location"]
    ))
    has_history = any(article.get("verified_series") for article in articles)
    has_territory = any(
        isinstance(f, dict) and (
            f.get("territory")
            or (isinstance(f.get("segment"), dict)
                and f["segment"].get("territory"))
        )
        for article in articles
        for f in (article.get("document_findings") or [])
    )
    research_stories = [
        {
            "id": r["pair_id"], "story_type": "paired_indicators",
            "editorial_priority_points": r["ranking"]["priority_points"],
            "source_url": r["source_url"],
            "source_locations": r["source_locations"],
            "research_only": True,
        } for r in records
    ]
    research_stories.extend({
        "id": r["id"], "story_type": "historical_annual_comparison",
        "editorial_priority_points": 35,
        "source_url": r["source_url"],
        "source_locations": [r["source_location"]],
        "research_only": True,
    } for r in history)
    research_stories.extend({
        "id": r["id"], "story_type": "territorial_rate_comparison",
        "editorial_priority_points": 40,
        "source_url": r["source_url"],
        "source_locations": [
            r["low"]["source_location"], r["high"]["source_location"]],
        "research_only": True,
    } for r in territory)
    research_stories.extend({
        "id": r["id"], "story_type": "labor_categories_yoy_evidence",
        "editorial_priority_points": 50,
        "source_url": r["source_url"],
        "source_locations": r["source_locations"],
        "research_only": True,
    } for r in labor)
    research_stories.sort(key=lambda r: (
        -r["editorial_priority_points"], r["story_type"], r["id"]
    ))
    return {
        "schema_version": "pulse-research-engine-3.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_research_only",
        "source_document_count": len(articles),
        "extracted_findings_count": extracted_count,
        "verified_single_findings_count": len(pool),
        "verified_paired_candidate_count": len(pairs),
        "research_candidates": records[:limit],
        "historical_signals": history,
        "territorial_signals": territory,
        "labor_signals": labor,
        "research_stories": research_stories,
        "publication_coverage": publication_coverage,
        "narrative_leads_unverified": narrative_leads,
        "narrative_lead_count": len(narrative_leads),
        "coverage": {
            "scope": "whole_pdf_text_layer_context_and_verified_structured_findings" if any(x["full_text_layer_attached"] for x in publication_coverage) else "structured_verified_findings_in_workbench_not_entire_pdf_prose",
            "historical_series_supplied": bool(has_history),
            "territorial_dimensions_supplied": bool(has_territory),
            "historical_comparison_stories": "verified_records_available" if history else "no_comparable_data",
            "territorial_comparison_stories": "verified_records_available" if territory else "no_comparable_data",
            "missing_evidence_policy": "withhold_inference",
            "narrative_paragraphs_are_context_not_statistical_proof": True,
            "research_stories_count": len(research_stories),
            "labor_evidenced_signals": len(labor),
            "narrative_leads_need_independent_verification": len(narrative_leads),
        },
        "checks": {
            "no_ai_or_network_required": True,
            "no_automatic_publication": True,
            "queue_points_not_pulse_score": True,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PULSE 3.0 research of verified workbench evidence")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_RESEARCH_PAIRS:
        parser.error("Limit must be from 1 to 10")
    if not args.inspect and not args.output:
        parser.error("Output required unless inspecting")
    if args.output and (
        args.output.name.lower() in FORBIDDEN_OUTPUTS or
        args.output.resolve() == args.input.resolve()
    ):
        parser.error("Refusing to overwrite input or production")
    report = research_report(_read_input(args.input), limit=args.limit)
    if args.inspect:
        print(json.dumps({
            "source_documents": report["source_document_count"],
            "findings_extracted": report["extracted_findings_count"],
            "findings_verified": report["verified_single_findings_count"],
            "matched_pairs": report["verified_paired_candidate_count"],
            "historical_signals": len(report["historical_signals"]),
            "labor_signals": len(report["labor_signals"]),
            "territorial_signals": len(report["territorial_signals"]),
            "narrative_leads_unverified": len(report["narrative_leads_unverified"]),
            "pdf_coverage": report["publication_coverage"],
            "narrative_leads_unverified": len(report["narrative_leads_unverified"]),
            "top_candidates": [
                {"segment": c["segment"], "tier": c["ranking"]["queue_tier"],
                 "angles": [a["id"] for a in c["angles"]]}
                for c in report["research_candidates"]
            ],
            "coverage": report["coverage"],
            "requires_ollama": False,
        }, ensure_ascii=False))
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "file": str(args.output),
            "verified_pairs": report["verified_paired_candidate_count"],
            "editorial_candidates": len(report["research_candidates"]),
            "historical_signals": len(report["historical_signals"]),
            "territorial_signals": len(report["territorial_signals"]),
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
