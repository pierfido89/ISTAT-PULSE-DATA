#!/usr/bin/env python3
"""Pilot second-domain source: official ISTAT monthly labor release.

Uses only the official ISTAT download, extracts an auditable table 1
(absolute values in thousands and official annual rates), reads the
complete PDF text-layer and writes an isolated research workbench.
No Ollama, no API billing, no production feeds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
import sys

try:
    from scripts.pulse_research_labor import SOURCE_URL, extract_istat_labor_pdf
    from scripts.pulse_research_reading import read_pdf_publication
    from scripts.pulse_editorial_pairs import FORBIDDEN_OUTPUTS
    from scripts.pulse_evidence import fetch_bounded
except ModuleNotFoundError:
    from pulse_research_labor import SOURCE_URL, extract_istat_labor_pdf
    from pulse_research_reading import read_pdf_publication
    from pulse_editorial_pairs import FORBIDDEN_OUTPUTS
    from pulse_evidence import fetch_bounded


def make_labor_workbench() -> dict:
    raw, content_type, final_url = fetch_bounded(SOURCE_URL, timeout=30)
    if urlsplit(final_url).hostname not in ("www.istat.it", "istat.it"):
        raise ValueError("Source redirected outside ISTAT")
    if not (content_type.lower().startswith("application/pdf")
            or raw.startswith(b"%PDF-")):
        raise ValueError("Not an official ISTAT PDF response")
    rows = extract_istat_labor_pdf(raw, final_url)
    if len(rows) != 9:
        raise ValueError("Labor table format not independently verified")
    reading = read_pdf_publication(raw, final_url)
    if not reading["complete_text_layer"]:
        raise ValueError("Partial PDF text: cannot claim full-source reading")
    return {
        "schema_version": "pulse-research-workbench-3.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "verified_labor_source_official_download",
        "articles": [{
            "id": "SAMPLE-ISTAT-LABOR-2026-08",
            "headline": "Occupati e disoccupati, agosto 2026",
            "public_source": {
                "url": final_url,
                "role": "primary_statistical_source",
                "domain": "istat.it",
                "download_verified": True,
            },
            "source_sha256": reading["source_sha256"],
            "document_reading": reading,
            "document_findings": rows,
            "verified_series": [],
            "publication_status": "research_workbench_only",
        }]
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verified second-domain labor PDF research")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.name.lower() in FORBIDDEN_OUTPUTS:
        parser.error("Refusing production feed filename")
    try:
        doc = make_labor_workbench()
    except (ValueError, OSError, RuntimeError) as exc:
        print("Labor source not verified: " + str(exc), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    reading = doc["articles"][0]["document_reading"]
    print(json.dumps({
        "file": str(args.output),
        "verified_labor_rows": len(doc["articles"][0]["document_findings"]),
        "pdf_pages_read": reading["pdf_pages_scanned"],
        "pdf_pages_total": reading["pdf_pages_total"],
        "complete_text_layer": reading["complete_text_layer"],
        "publication": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
