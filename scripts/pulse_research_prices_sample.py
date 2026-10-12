#!/usr/bin/env python3
"""Third real domain ISTAT prices August 2026 official PDF lab workbench."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
import sys

try:
    from scripts.pulse_research_prices import SOURCE_URL, extract_istat_cpi_pdf
    from scripts.pulse_research_reading import read_pdf_publication
    from scripts.pulse_editorial_pairs import FORBIDDEN_OUTPUTS
    from scripts.pulse_evidence import fetch_bounded
except ModuleNotFoundError:
    from pulse_research_prices import SOURCE_URL, extract_istat_cpi_pdf
    from pulse_research_reading import read_pdf_publication
    from pulse_editorial_pairs import FORBIDDEN_OUTPUTS
    from pulse_evidence import fetch_bounded


def make_prices_workbench() -> dict:
    raw, content_type, final_url = fetch_bounded(SOURCE_URL, timeout=30)
    if urlsplit(final_url).hostname not in ("www.istat.it", "istat.it"):
        raise ValueError("PDF redirected away from ISTAT")
    if not (content_type.lower().startswith("application/pdf")
            or raw.startswith(b"%PDF-")):
        raise ValueError("Not a PDF")
    rows = extract_istat_cpi_pdf(raw, final_url)
    if len(rows) != 3:
        raise ValueError("CPI Prospetto 1 not independently verified")
    reading = read_pdf_publication(raw, final_url)
    return {
        "schema_version": "pulse-research-workbench-3.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "verified_prices_source_official_download",
        "articles": [{
            "id": "SAMPLE-ISTAT-PRICES-2026-08",
            "headline": "Prezzi al consumo agosto 2026, dati definitivi",
            "public_source": {
                "url": final_url,
                "role": "primary_statistical_source",
                "domain": "istat.it", "download_verified": True,
            },
            "source_sha256": reading["source_sha256"],
            "document_reading": reading,
            "document_findings": rows,
            "verified_series": [],
            "publication_status": "research_workbench_only",
        }],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Verify ISTAT final CPI August 2026 PDF")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.name.lower() in FORBIDDEN_OUTPUTS:
        p.error("Refusing production feed filename")
    try:
        result = make_prices_workbench()
    except (OSError, RuntimeError, ValueError) as exc:
        print("CPI source not verified: " + str(exc), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reading = result["articles"][0]["document_reading"]
    print(json.dumps({
        "file": str(args.output),
        "verified_price_rows": len(result["articles"][0]["document_findings"]),
        "pdf_pages_read": reading["pdf_pages_scanned"],
        "pdf_pages_total": reading["pdf_pages_total"],
        "complete_text_layer": reading["complete_text_layer"],
        "published": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
