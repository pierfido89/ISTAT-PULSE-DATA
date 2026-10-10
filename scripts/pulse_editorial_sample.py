#!/usr/bin/env python3
"""Generate a *local workbench input*, not a PULSE publication.

Download only the official ISTAT tourism PDF and retain its precise table
provenance. No paid APIs, no local LLM requirement for this preparation step.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

OFFICIAL_URL = (
    "https://www.istat.it/wp-content/uploads/2026/09/"
    "Statistica-Flash_II_Trimestre_2026.pdf"
)


def build_workbench(*, official_url: str = OFFICIAL_URL) -> dict:
    if official_url != OFFICIAL_URL:
        raise ValueError("Only the reviewed ISTAT primary PDF is supported")
    try:
        from scripts.pulse_evidence import fetch_bounded
        from scripts.pulse_deep_tables import extract_pdf_mixed_findings
        from scripts.pulse_editorial_evidence import source_metadata_from_text, enrich
    except ModuleNotFoundError:
        from pulse_evidence import fetch_bounded
        from pulse_deep_tables import extract_pdf_mixed_findings
        from pulse_editorial_evidence import source_metadata_from_text, enrich
    raw, content_type, final_url = fetch_bounded(official_url, timeout=25)
    if not final_url.startswith("https://www.istat.it/"):
        raise ValueError("Unexpected redirect away from official ISTAT host")
    if not (content_type.lower().startswith("application/pdf") or raw.startswith(b"%PDF-")):
        raise ValueError("The official source did not return a PDF")
    findings = extract_pdf_mixed_findings(raw, final_url)
    if not findings:
        raise ValueError("No independently identified PDF table phenomena")
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            text = " ".join((p.extract_text() or "") for p in pdf.pages[:4])
    except ImportError as exc:
        raise RuntimeError("Missing free library: python -m pip install pdfplumber") from exc
    article = {
        "id": "SAMPLE-ISTAT-TOURISM-2026-Q2",
        "headline": "Flussi turistici, II trimestre 2026: evidenze statistiche",
        "summary": "Arrivi e presenze distinti per residenza dei clienti e tipo di struttura.",
        "public_source": {
            "url": final_url, "domain": "istat.it",
            "role": "primary_statistical_source"
        },
        "period_reference": "2026-Q2",
        "document_findings": findings,
        "verified_series": [],
        "patterns": [],
        "source_methodology": source_metadata_from_text(text),
        "publication_status": "workbench_only",
    }
    enrich(article)
    return {
        "schema_version": "pulse-editorial-ai-workbench-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "pilot_only_not_for_app_feed",
        "articles": [article]
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Prepare official ISTAT PDF pilot evidence")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.name in {"articles.json", "observer_articles.json", "index.json"}:
        p.error("Never overwrite production news or observer indexes")
    result = build_workbench()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"Source ISTAT: {len(result['articles'][0]['document_findings'])} phenomena, "
          f"workbench: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
