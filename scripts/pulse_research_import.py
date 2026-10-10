#!/usr/bin/env python3
"""Generic local official PDF -> PULSE Research workbench.

Read *any* publication's extractable text layer, not just the tourism
pilot. NEVER claim numeric verification from PDF prose; the output has
zero verified structured findings until a source-specific audited
extractor is applied. Source URL is provenance supplied by the editor,
NOT independently fetched/verified by this offline command.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
import sys

try:
    from scripts.pulse_research_reading import read_pdf_publication, MAX_PAGES
    from scripts.pulse_editorial_pairs import FORBIDDEN_OUTPUTS
except ModuleNotFoundError:
    from pulse_research_reading import read_pdf_publication, MAX_PAGES
    from pulse_editorial_pairs import FORBIDDEN_OUTPUTS

MAX_PDF_BYTES = 60_000_000


def import_publication(pdf_path: Path, source_url: str,
                       title: str = "", max_pages: int = MAX_PAGES) -> dict:
    if not pdf_path.is_file() or pdf_path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("Local PDF missing or larger than 60 MB")
    parsed = urlsplit(source_url)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("An official HTTPS publication URL is required")
    raw = pdf_path.read_bytes()
    reading = read_pdf_publication(raw, source_url, max_pages=max_pages)
    identifier = reading["source_sha256"][:16]
    article = {
        "id": f"RESEARCH-PDF-{identifier}",
        "headline": str(title).strip()[:200] or pdf_path.stem[:200],
        "public_source": {
            "url": source_url,
            "domain": parsed.hostname.lower(),
            "role": "primary_statistical_source",
            "url_verified_against_download": False,
        },
        "source_sha256": reading["source_sha256"],
        "document_findings": [],
        "verified_series": [],
        "document_reading": reading,
        "patterns": [],
        "publication_status": "research_workbench_only",
        "verification_status": "narrative_only_needs_independent_numeric_extraction",
    }
    return {
        "schema_version": "pulse-research-workbench-3.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "local_no_network_pdf_import",
        "purpose": "research_not_for_app_feed",
        "articles": [article],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Whole-publication offline import; no OCR or fact invention")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args(argv)
    if (args.output.name.lower() in FORBIDDEN_OUTPUTS
            or args.output.resolve() == args.pdf.resolve()):
        parser.error("Refusing to overwrite original publication or production feed")
    try:
        imported = import_publication(
            args.pdf, args.source_url, args.title, args.max_pages)
    except (ValueError, RuntimeError, OSError) as exc:
        print("Importazione rifiutata: " + str(exc), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(imported, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reading = imported["articles"][0]["document_reading"]
    print(json.dumps({
        "output": str(args.output),
        "pdf_pages_scanned": reading["pdf_pages_scanned"],
        "pdf_pages_total": reading["pdf_pages_total"],
        "narrative_passages": reading["passages_count"],
        "verified_numeric_findings": 0,
        "coverage_warnings": reading["coverage_warnings"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
