#!/usr/bin/env python3
"""Independently verified ISTAT population/education/environment workbenches.

One exact reviewed source URL per domain. Official HTTPS fetch, SHA-256
provenance, strict table layout, whole-PDF read, isolated JSON.
Refuse publishing or partial/failed numeric validation. No AI calls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

try:
    from scripts.pulse_research_new_domains import SOURCES, extract_source_pdf
    from scripts.pulse_research_reading import read_pdf_publication
    from scripts.pulse_editorial_pairs import FORBIDDEN_OUTPUTS
    from scripts.pulse_evidence import fetch_bounded
except ModuleNotFoundError:
    from pulse_research_new_domains import SOURCES, extract_source_pdf
    from pulse_research_reading import read_pdf_publication
    from pulse_editorial_pairs import FORBIDDEN_OUTPUTS
    from pulse_evidence import fetch_bounded


def make_workbench(domain: str) -> dict:
    if domain not in SOURCES:
        raise ValueError("Unreviewed ISTAT domain")
    raw, content_type, final_url = fetch_bounded(SOURCES[domain], timeout=30)
    if final_url != SOURCES[domain] or not raw.startswith(b"%PDF-"):
        raise ValueError("Official PDF URL, document type or redirect changed")
    findings = extract_source_pdf(raw, final_url, domain)
    target = {"popolazione": 8, "istruzione": 4, "ambiente": 20}[domain]
    if len(findings) != target:
        raise ValueError(
            f"Verified numerical table incomplete for {domain}: {len(findings)}/{target}"
        )
    reading = read_pdf_publication(raw, final_url)
    if not reading["complete_text_layer"]:
        raise ValueError("Not all PDF pages have extractable textual coverage")
    return {
        "schema_version": "pulse-research-workbench-3.3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "local_source_verified_research_not_app_feed",
        "articles": [{
            "id": f"ISTAT-RESEARCH-{domain}-"
                  f"{reading['source_sha256'][:12]}",
            "headline": {
                "popolazione": "Indicatori demografici — anno 2025 (provvisori)",
                "istruzione": "Livelli di istruzione e ritorni occupazionali 2024",
                "ambiente": "Raccolta differenziata 2024-2025",
            }[domain],
            "public_source": {
                "url": final_url, "domain": "istat.it",
                "role": "primary_statistical_source", "download_verified": True
            },
            "source_sha256": reading["source_sha256"],
            "document_reading": reading,
            "document_findings": findings if domain != "istruzione" else [],
            "verified_series": findings if domain == "istruzione" else [],
            "publication_status": "workbench_only",
            "patterns": [],
        }],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Source-verified extractions: population, education, environment"
    )
    p.add_argument("--domain", required=True, choices=sorted(SOURCES))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.name.lower() in FORBIDDEN_OUTPUTS:
        p.error("Refusing production feed file")
    try:
        doc = make_workbench(args.domain)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ISTAT {args.domain} non verificato: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    a = doc["articles"][0]
    print(json.dumps({
        "domain": args.domain,
        "file": str(args.output),
        "verified_numeric_items": len(a["document_findings"]) +
                                  len(a["verified_series"]),
        "pdf_pages_read": a["document_reading"]["pdf_pages_scanned"],
        "pdf_pages_total": a["document_reading"]["pdf_pages_total"],
        "historical_series": len(a["verified_series"]),
        "territorial_rate_observations": len(a["document_findings"])
             if args.domain == "ambiente" else 0,
        "published": False
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
