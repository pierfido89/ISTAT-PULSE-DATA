"""Bounded extraction of explicit absolute values plus YoY changes.

This is not a historical series: a 2026 total and its published 2025/26
percentage variation must never be presented as two measured year values.
"""
from __future__ import annotations
import hashlib
import io
import re

NUM = re.compile(r"^[+-]?\d{1,3}(?:[. ]\d{3})*(?:,\d+)?$")
PERCENT = re.compile(r"^[+-]?\d{1,3}(?:,\d+)?$")
PERIOD = re.compile(r"20\d{2}\s*[-/]\s*(?:20)?\d{2}")

def _value(cell):
    text = str(cell or "").strip().replace("\u00a0", " ")
    if not NUM.fullmatch(text):
        return None
    try:
        return float(text.replace(" ", "").replace(".", "").replace(",", "."))
    except ValueError:
        return None

def _pct(cell):
    token = str(cell or "").strip().replace("%", "")
    if not PERCENT.fullmatch(token):
        return None
    try:
        n = float(token.replace(",", "."))
        return n if -100 <= n <= 100 else None
    except ValueError:
        return None

def extract_mixed_table_rows(rows, *, caption, url, location, source_sha256):
    lower = re.sub(r"\s+", " ", caption or "").casefold()
    # The same document must explicitly define BOTH the total and YoY columns.
    if not (("valori assoluti" in lower or "valore assoluto" in lower) and
            ("variazioni %" in lower or "variazioni percentuali" in lower) and
            PERIOD.search(lower)):
        return []
    results, section, residents = [], "", ""
    for pos, row in enumerate(rows):
        values = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
        cells = [v for v in values if v]
        if len(cells) == 1 and re.search(r"(alberghier|esercizi ricettivi)", cells[0], re.I):
            section, residents = cells[0][:100], ""
            continue
        if len(values) < 10:
            continue
        qualifier = values[0].casefold()
        if qualifier in ("residenti", "non residenti", "totale"):
            residents = qualifier
        # Strictly aligned columns: resident group, indicator, four absolute
        # monthly/quarter totals, four independently reported YoY percent changes.
        indicator = values[1]
        if indicator.casefold() not in ("arrivi", "presenze"):
            continue
        quarter_total = _value(values[5])
        reported_pct = _pct(values[9])
        if quarter_total is None or reported_pct is None or not section:
            continue
        result = {
            "indicator": indicator,
            "unit": "arrivi" if indicator.casefold() == "arrivi" else "notti",
            "segment": {"structure": section, "residence": residents},
            "reference_period": "2026-Q2" if ("ii trimestre" in lower and "2026" in lower) else None,
            "observed_total": quarter_total,
            "reported_yoy_change_pct": reported_pct,
            "comparison_label": "variazione tendenziale pubblicata dalla fonte",
            "source_url": url,
            "source_sha256": source_sha256,
            "location": f"{location}:row:{pos+1}",
            "extraction_method": "explicit_absolute_total_and_yoy_table",
            "verified": True,
            "editorial_status": "candidate_not_published",
        }
        if not result["reference_period"]:
            # Do not invent periods when the caption is missing.
            continue
        results.append(result)
        if len(results) >= 40:
            break
    # Only retain independent combinations; table layouts may repeat headers.
    seen, deduped = set(), []
    for item in results:
        key = (item["indicator"], tuple(item["segment"].items()),
               item["reference_period"], item["observed_total"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped

def extract_mixed_text_lines(text, *, url, page_number, source_sha256):
    """Fallback when the native PDF table grid splits labels from number cells.

    ISTAT's actual PDF includes labels on separate intervening lines. This
    parser still requires explicit caption, source, row and segment evidence.
    """
    lines = [re.sub(r"\\s+", " ", line).strip() for line in (text or "").splitlines()]
    lower = " ".join(lines).casefold()
    if not ("prospetto " in lower and
            ("valori assoluti" in lower or "valore assoluto" in lower) and
            ("variazioni percentuali" in lower or "variazioni %" in lower) and
            PERIOD.search(lower) and "ii trimestre" in lower and "2026" in lower):
        return []
    out, section, residence = [], "", ""
    residence_labels = {"residenti", "non residenti", "totale"}
    for index, line in enumerate(lines):
        low = line.casefold()
        if low in ("esercizi alberghieri", "esercizi extra-alberghieri",
                   "totale esercizi ricettivi"):
            section, residence = line, ""
            continue
        if low in residence_labels:
            residence = low
            continue
        bits = line.split()
        if not section or len(bits) != 9 or bits[0].casefold() not in ("arrivi", "presenze"):
            continue
        # Exactly four observed totals followed by four reported YoY changes.
        totals = [_value(v) for v in bits[1:5]]
        changes = [_pct(v) for v in bits[5:9]]
        if any(v is None for v in totals+changes):
            continue
        # The PDF sometimes places the residence label AFTER the Arrivi
        # line. Its immediately following dedicated row labels the pair.
        group = residence
        if bits[0].casefold() == "arrivi" and index+1 < len(lines):
            next_line = lines[index+1].casefold()
            if next_line in residence_labels:
                group = next_line
                residence = next_line
        if not group:
            # Fail closed: never infer demographics from row position alone.
            continue
        out.append({
            "indicator": bits[0],
            "unit": "arrivi" if bits[0].casefold() == "arrivi" else "notti",
            "segment": {"structure": section, "residence": group},
            "reference_period": "2026-Q2",
            "observed_total": totals[3],
            "reported_yoy_change_pct": changes[3],
            "comparison_label": "variazione tendenziale pubblicata dalla fonte",
            "source_url": url,
            "source_sha256": source_sha256,
            "location": f"page:{page_number}:text:line:{index+1}",
            "extraction_method": "explicit_absolute_total_and_yoy_table",
            "verified": True,
            "editorial_status": "candidate_not_published",
        })
        if len(out) >= 40:
            break
    return out


def extract_pdf_mixed_findings(data, url, source_sha256="", max_pages=12):
    import pdfplumber
    digest = source_sha256 or hashlib.sha256(data).hexdigest()
    output = []
    with pdfplumber.open(io.BytesIO(data)) as doc:
        for page_number, page in enumerate(doc.pages[:max_pages], 1):
            text = page.extract_text() or ""
            output.extend(extract_mixed_text_lines(
                text, url=url, page_number=page_number, source_sha256=digest
            ))
            if len(output) >= 40:
                return output[:40]
            for table_number, table in enumerate(page.extract_tables()[:10], 1):
                # Include the page caption; use strict row structure to avoid
                # treating prose or chart axis labels as table observations.
                output.extend(extract_mixed_table_rows(
                    table, caption=text, url=url,
                    location=f"page:{page_number}:table:{table_number}",
                    source_sha256=digest
                ))
                if len(output) >= 40:
                    return output[:40]
    return output
