"""PULSE evidence extractor: bounded, provenance-preserving, fail-closed.

A source is never marked verified solely because numbers occur on a page.
Compares observations only from one explicitly labelled row and two years.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

YEAR = re.compile(r"(?:19|20)\d{2}")
PERCENT = re.compile(r"^([+-]?\d{1,3}(?:[.,]\d{1,2})?)\s*%?$")
MISSING = {"", "-", "—", ":", "..", "n.d.", "n/a"}
MAX_BYTES = 8_000_000


def normalized_percent(raw):
    token = str(raw).strip().replace("\u00a0", " ")
    if token.lower() in MISSING:
        return None
    m = PERCENT.fullmatch(token)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return n if 0 <= n <= 100 else None


def normalize_year(raw):
    token = str(raw).strip()
    return token if YEAR.fullmatch(token) else None


def validate_source_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Source must have an HTTPS URL")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private host blocked")
    return url


def fetch_bounded(url, timeout=12):
    validate_source_url(url)
    req = Request(url, headers={"User-Agent": "ISTAT-PULSE-Research/1.0"})
    with urlopen(req, timeout=timeout) as response:
        final_url = response.geturl()
        validate_source_url(final_url)
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Document exceeds bounded extraction limit")
        return data, response.headers.get("Content-Type", ""), final_url


def matrix_evidence(rows, source_url, source_hash, location, unit_hint=""):
    """Require strict rectangular rows, explicitly named percentage unit and two year columns."""
    results = []
    if not rows or len(rows) < 2:
        return results
    for header_idx in range(min(8, len(rows) - 1)):
        headers = [str(c).strip() if c is not None else "" for c in rows[header_idx]]
        years = [(idx, int(y)) for idx, h in enumerate(headers) if (y := normalize_year(h))]
        if len(years) < 2:
            continue
        years.sort(key=lambda entry: entry[1])
        left, right = years[-2:]
        if not 0 < right[1] - left[1] <= 5:
            continue
        units = (" ".join(headers) + " " + unit_hint).lower()
        unit_from_heading = bool(re.search(r"%|percentual|percent\b", units))
        for row_index, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            if len(row) <= max(left[0], right[0]) or not row:
                continue
            indicator = str(row[0] or "").strip()
            if not 4 <= len(indicator) <= 125:
                continue
            # Row's metadata must specify unit or the table must specify percentage.
            if not (unit_from_heading or "%" in indicator or "percent" in indicator.lower()):
                continue
            v0, v1 = normalized_percent(row[left[0]]), normalized_percent(row[right[0]])
            if v0 is None or v1 is None:
                continue
            results.append({
                "indicator": indicator,
                "unit": "%",
                "observations": [
                    {"period": str(left[1]), "value": v0, "raw": str(row[left[0]])},
                    {"period": str(right[1]), "value": v1, "raw": str(row[right[0]])}
                ],
                "delta": round(v1 - v0, 3),
                "comparison_unit": "punti percentuali",
                "source_url": source_url,
                "source_sha256": source_hash,
                "location": f"{location}:row:{row_index}",
                "extraction_method": "same_row_explicit_year_structured_table",
                "verified": True
            })
            if len(results) >= 20:
                return results
        if results:
            return results
    return results


def html_tables(data):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    for idx, table in enumerate(soup.find_all("table")[:30], 1):
        caption = table.find("caption")
        hint = caption.get_text(" ", strip=True) if caption else ""
        rows = []
        for tr in table.find_all("tr")[:160]:
            cells = tr.find_all(["th", "td"], recursive=False)
            rows.append([c.get_text(" ", strip=True) for c in cells])
        yield str(idx), rows, hint


def csv_tables(data):
    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    return [list(csv.reader(io.StringIO(text), dialect))]


def xlsx_tables(data):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for sheet in wb.worksheets[:30]:
            rows = [[c for c in row] for row in sheet.iter_rows(min_row=1, max_row=2000, max_col=40, values_only=True)]
            yield sheet.title, rows, sheet.title
    finally:
        wb.close()


def xls_tables(data):
    import xlrd
    wb = xlrd.open_workbook(file_contents=data)
    for sh in wb.sheets()[:30]:
        yield sh.name, [sh.row_values(i, 0, min(sh.ncols, 40)) for i in range(min(sh.nrows, 2000))], sh.name


def pdf_tables(data):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for p, page in enumerate(pdf.pages[:35], start=1):
            # Only table cells, never proximity-based numbers in running text.
            for t, table in enumerate(page.extract_tables()[:15], start=1):
                yield f"page:{p}:table:{t}", table, ""


def json_tables(data):
    doc = json.loads(data)
    if isinstance(doc, dict):
        # Require a conventional explicit table array. Never infer table shapes from arbitrary objects.
        for key in ("tables", "data"):
            tables = doc.get(key)
            if isinstance(tables, list) and tables and all(isinstance(x, list) for x in tables):
                yield key, tables, str(doc.get("unit", ""))
    elif isinstance(doc, list) and doc and all(isinstance(x, list) for x in doc):
        yield "root", doc, ""


def extract_bytes(data, url, content_type="", filename=""):
    validate_source_url(url)
    source_hash = hashlib.sha256(data).hexdigest()
    name = (filename or urlparse(url).path).lower().split("?")[0]
    ct = content_type.lower()
    mixed_findings = []
    if name.endswith(".pdf") or "application/pdf" in ct:
        tables = pdf_tables(data)
        try:
            from scripts.pulse_deep_tables import extract_pdf_mixed_findings
        except ModuleNotFoundError:
            from pulse_deep_tables import extract_pdf_mixed_findings
        try:
            mixed_findings = extract_pdf_mixed_findings(data, url, source_hash)
        except Exception:
            # Never confuse a PDF parsing failure with positive evidence.
            mixed_findings = []
    elif name.endswith(".xlsx") or "spreadsheetml" in ct:
        tables = xlsx_tables(data)
    elif name.endswith(".xls") or "ms-excel" in ct:
        tables = xls_tables(data)
    elif name.endswith((".csv", ".tsv")) or "text/csv" in ct:
        tables = ((str(i), matrix, "") for i, matrix in enumerate(csv_tables(data), 1))
    elif name.endswith(".json") or "application/json" in ct:
        tables = json_tables(data)
    elif "html" in ct or name.endswith((".html", ".htm")):
        tables = html_tables(data)
    else:
        return {"source_url": url, "source_sha256": source_hash, "evidence": [], "status": "unsupported_format"}
    evidence = []
    for location, rows, hint in tables:
        evidence.extend(matrix_evidence(rows, url, source_hash, location, hint))
        if len(evidence) >= 20:
            break
    return {
        "source_url": url,
        "source_sha256": source_hash,
        "evidence": evidence[:20],
        "findings": mixed_findings[:40],
        "findings_status": "explicit_document_facts" if mixed_findings else "none",
        "status": "verified" if evidence else "no_comparable_series"
    }


def extract_url(url):
    data, content_type, final_url = fetch_bounded(url)
    return extract_bytes(data, final_url, content_type)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="HTTPS URL or local file")
    parser.add_argument("--source-url", default="", help="Required original HTTPS URL for local files")
    args = parser.parse_args()
    if args.source.startswith("https://"):
        result = extract_url(args.source)
    else:
        if not args.source_url:
            parser.error("--source-url is required when reading a local file")
        result = extract_bytes(Path(args.source).read_bytes(), args.source_url, filename=args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
