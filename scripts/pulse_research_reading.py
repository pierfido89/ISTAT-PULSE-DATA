"""Whole-publication PDF reading for the PULSE Research Engine.

Retains verifiable page/line provenance for the ENTIRE text layer.
Narrative lines are *context only*, not checked statistical evidence.
No LLM, OCR, embeddings, remote API or automatic publishing. The caller
must authenticate the official download and supply its exact URL.
"""
from __future__ import annotations

import hashlib
import io
import re

MAX_PAGES = 160
MAX_TEXT_CHARS = 950_000
MAX_LINE_CHARS = 420
MAX_PASSAGES = 500
MIN_PASSAGE_CHARS = 35

SECTION_RE = re.compile(
    r"(?i)^(?:[A-ZÀ-Ü][A-ZÀ-Ü\s,;/:'’()\-]{9,}|"
    r"(?:\d{1,2}\.)?\s*(?:principali risultati|metodologia|"
    r"glossario|definizioni|nota metodologica|"
    r"principali evidenze|quadro generale|analisi|risultati|"
    r"approfondimento|confronto|tendenze)[^\n]{0,100})$"
)
NUMBER = re.compile(r"\d")


def _normal(line: str) -> str:
    return re.sub(r"\s+", " ", line or "").strip()


def _extract_lines(page_text: str, page_number: int) -> list[dict]:
    result = []
    for number, raw in enumerate(page_text.splitlines(), 1):
        normalized = _normal(raw)
        if not normalized:
            continue
        result.append({
            "page": page_number,
            "line": number,
            "source_location": f"page:{page_number}:text:line:{number}",
            "text": normalized[:MAX_LINE_CHARS],
            "was_truncated": len(normalized) > MAX_LINE_CHARS,
        })
    return result


def read_pdf_publication(data: bytes, source_url: str,
                         *, max_pages: int = MAX_PAGES) -> dict:
    if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
        raise ValueError("Expected real PDF bytes")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        raise ValueError("Expected authenticated HTTPS official PDF URL")
    if not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("Invalid page limit")
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("Free pdfplumber library not installed") from exc
    digest = hashlib.sha256(data).hexdigest()
    scanned, all_lines, passages = 0, 0, []
    page_index, used_chars = [], 0
    pages_without_text = []
    truncation = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        total_pages = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages[:max_pages], 1):
            raw = page.extract_text() or ""
            scanned += 1
            if not raw.strip():
                pages_without_text.append(page_number)
            lines = _extract_lines(raw, page_number)
            all_lines += len(lines)
            page_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            page_index.append({
                "page": page_number, "text_sha256": page_hash,
                "line_count": len(lines), "extractable_text": bool(raw.strip()),
            })
            if len(passages) >= MAX_PASSAGES:
                truncation.append("max_passages")
                continue
            paragraph = []
            start_line = None
            def flush():
                nonlocal used_chars, start_line
                if not paragraph or start_line is None:
                    return
                text = _normal(" ".join(paragraph))
                paragraph.clear()
                if len(text) < MIN_PASSAGE_CHARS:
                    start_line = None
                    return
                remaining = MAX_TEXT_CHARS - used_chars
                if remaining <= 0:
                    truncation.append("max_text_chars")
                    start_line = None
                    return
                # Sentences with figures are retained as text, NOT proof.
                stored = text[:min(remaining, 1000)]
                used_chars += len(stored)
                passages.append({
                    "source_location": f"page:{page_number}:text:line:{start_line}",
                    "page": page_number,
                    "text": stored,
                    "contains_numbers": bool(NUMBER.search(stored)),
                    "text_layer_only": True,
                    "proof_status": "verbatim_context_not_statistical_proof",
                    "source_sha256": digest,
                    "truncated": len(text) > len(stored),
                })
                start_line = None
            for line in lines:
                t = line["text"]
                heading = bool(SECTION_RE.fullmatch(t)) and len(t) < 135
                if heading:
                    flush()
                    if len(t) >= MIN_PASSAGE_CHARS and len(passages) < MAX_PASSAGES:
                        paragraph = [t]
                        start_line = line["line"]
                        flush()
                    continue
                if start_line is None:
                    start_line = line["line"]
                paragraph.append(t)
                # Short paragraphs preserve location and avoid giant prompts.
                if sum(len(x) for x in paragraph) >= 460 or t.endswith((".", ";", "!", "?")):
                    flush()
                if len(passages) >= MAX_PASSAGES or used_chars >= MAX_TEXT_CHARS:
                    break
            flush()
        if total_pages > scanned:
            truncation.append("max_pages")
    # Even one truncated section implies we did not finish full reading.
    truncated = bool(truncation) or bool(pages_without_text)
    return {
        "schema_version": "pulse-research-reading-1.0",
        "source_url": source_url,
        "source_sha256": digest,
        "pdf_pages_total": total_pages,
        "pdf_pages_scanned": scanned,
        "text_pages_scanned": scanned - len(pages_without_text),
        "lines_detected": all_lines,
        "pages_without_text_layer": pages_without_text,
        "page_index": page_index,
        "passages": passages,
        "passages_count": len(passages),
        "scanned_all_pdf_pages": scanned == total_pages,
        "complete_text_layer": not truncated,
        "coverage_warnings": sorted(set(truncation + (
            ["pages_without_extractable_text"] if pages_without_text else []))),
        "evidence_policy": "narrative_is_context_only_not_verified_numeric_claim",
    }


def match_passages(reading: dict, indicators: list[str],
                   max_results: int = 5) -> list[dict]:
    """Relevant narrative context only. Exact words, no inferred facts."""
    if not isinstance(reading, dict) or max_results < 1:
        return []
    words = [
        str(x).casefold().strip()
        for x in indicators if isinstance(x, str) and str(x).strip()
    ]
    if not words:
        return []
    matches = []
    for row in reading.get("passages") or []:
        if not isinstance(row, dict) or row.get("proof_status") != \
                "verbatim_context_not_statistical_proof":
            continue
        content = str(row.get("text") or "").casefold()
        hits = sum(bool(re.search(r"\b" + re.escape(term) + r"\b", content))
                   for term in words)
        if hits:
            matches.append((hits, row["page"], row["source_location"], row))
    matches.sort(key=lambda q: (-q[0], q[1], q[2]))
    return [record for _, _, _, record in matches[:max_results]]
