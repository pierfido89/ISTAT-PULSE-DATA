#!/usr/bin/env python3
"""Live integration acceptance for six independent official ISTAT PDFs.

Strict conditions verify REAL values from PDF table rows, not only
synthetic fixtures or counts. No remote AI, no publication, no APK.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.pulse_editorial_ai import _read_input
    from scripts.pulse_research_engine import research_report
except ModuleNotFoundError:
    from pulse_editorial_ai import _read_input
    from pulse_research_engine import research_report


def verify_six(input_files: list[Path]) -> dict:
    if len(input_files) != 6:
        raise ValueError("Exactly six distinct officially sourced workbenches required")
    articles = []
    for p in input_files:
        records = _read_input(p)
        if len(records) != 1:
            raise ValueError(f"Expected one reviewed primary PDF per file: {p}")
        articles.extend(records)
    report = research_report(articles, limit=10)
    if len({x["source_url"] for x in report["publication_coverage"]}) != 6:
        raise ValueError("Cross-source provenance not unique")
    for p in report["publication_coverage"]:
        if not (p["full_text_layer_attached"]
                and p["complete_text_layer"]
                and p["pdf_pages_scanned"] == p["pdf_pages_total"]
                and p["pdf_pages_scanned"] > 0):
            raise ValueError(f"PDF not fully read: {p['source_url']}")
    if len(report["research_stories"]) != 16:
        raise ValueError(f"Expected 16 proven research stories, got {len(report['research_stories'])}")
    counts = report["verified_observations_by_contract"]
    expected = {
        "tourism_verifiable_table_rows": 18,
        "labor_category_rows": 9,
        "price_index_rows": 3,
        "demography_rounded_rows": 8,
        "education_annual_values": 12,
        "environment_territorial_rate_rows": 20,
    }
    if counts != expected:
        raise ValueError(f"Missing verified items: {counts} != {expected}")
    if (len(report["historical_signals"]) != 4
            or len(report["territorial_signals"]) != 4
            or len(report["demography_signals"]) != 1
            or len(report["labor_signals"]) != 3
            or len(report["price_signals"]) != 1
            or len(report["research_candidates"]) != 3):
        raise ValueError("Cross-domain contract counts do not match")
    residence = next(c for c in report["research_candidates"]
                     if c["segment"] == "Esercizi alberghieri · residenti")
    vals = residence["evidence"]
    if not (vals[0]["value"] == 12_464_038 and vals[0]["change_pct"] == -4.3
            and vals[1]["value"] == 32_162_873 and vals[1]["change_pct"] == 1.7):
        raise ValueError("Tourism official source baseline not verified")
    national_labor = next(x for x in report["labor_signals"]
                          if x["population_group"] == "totale")
    employed = next(x for x in national_labor["indicator_evidence"]
                    if x["indicator"] == "Occupati")
    if employed["observed_total"] != 24_352_000:
        raise ValueError("Labor thousands-vs-units conversion wrong")
    price = report["price_signals"][0]
    rates = {x["price_index_code"]: x["reported_yoy_change_pct"]
             for x in price["evidence"]}
    if rates != {"NIC": 3.3, "IPCA": 3.2, "FOI": 3.4}:
        raise ValueError("CPI sources are misread or merged")
    pop = report["demography_signals"][0]
    totals = {x["indicator_code"]: x for x in pop["evidence"]}
    if not (totals["births"]["value"] == 355
            and totals["deaths"]["value"] == 652
            and totals["population_dec31"]["value"] == 58943
            and all(v["rounded_at_thousands"] for v in totals.values())):
        raise ValueError("Demographic provisional/rounded figures lost")
    italy_edu = next(h for h in report["historical_signals"] if
                     h["territory"] == "Italia" and
                     h["population_scope"] == "residenti 25-64 anni")
    if not (italy_edu["periods"] == [2022, 2023, 2024]
            and italy_edu["first_value"] == "20.3"
            and italy_edu["last_value"] == "22.3"
            and italy_edu["absolute_change"] == "2.0"
            and italy_edu["absolute_change_unit"] == "percentage_points"
            and italy_edu["percent_change_from_first"] is None):
        raise ValueError("Official historical education comparison not verified")
    waste = next(t for t in report["territorial_signals"]
                 if t["indicator"] == "raccolta differenziata rifiuti urbani")
    if not (waste["low"]["name"] == "Sud"
            and waste["low"]["value"] == "59.9"
            and waste["high"]["name"] == "Nord-est"
            and waste["high"]["value"] == "77.8"
            and waste["gap"] == "17.9"
            and waste["gap_unit"] == "percentage_points"):
        raise ValueError("Official territorial comparison not verified")
    if any(r.get("pulse_score") is not None
           for r in report["research_candidates"]):
        raise ValueError("Research priority may not impersonate PULSE Score")
    return {
        "validation": "six_real_ISTAT_PDFs_exact_numeric_assertions_passed",
        "source_documents": len(report["publication_coverage"]),
        "pdf_pages_total": sum(p["pdf_pages_total"] for p in report["publication_coverage"]),
        "verified_numeric_observations": sum(counts.values()),
        "verified_by_contract": counts,
        "historical_signals": len(report["historical_signals"]),
        "territorial_signals": len(report["territorial_signals"]),
        "research_stories": len(report["research_stories"]),
        "publication": False, "api_cost": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Six-source PULSE Research acceptance")
    parser.add_argument("inputs", nargs=6, type=Path)
    args = parser.parse_args(argv)
    result = verify_six(args.inputs)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
