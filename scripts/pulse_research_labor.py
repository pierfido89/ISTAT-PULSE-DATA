"""Evidence-only extractor: ISTAT 'Occupati e disoccupati' monthly PDF.

The source table PROSPETTO 1 gives seasonally adjusted totals in
THOUSANDS and published month-on-month / year-on-year changes. This
extractor supports that specifically described layout, refuses layout
changes rather than guessing, and returns no data from prose claims.
"""
from __future__ import annotations

import hashlib
import io
import re
from urllib.parse import urlsplit

SOURCE_URL = (
    "https://www.istat.it/wp-content/uploads/2026/10/"
    "CS_Occupati-e-disoccupati_AGOSTO_2026.pdf"
)
MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3,
    "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9,
    "ottobre": 10, "novembre": 11, "dicembre": 12,
}
ROW = re.compile(
    r"^\s*(Occupati|Disoccupati|Inattivi\s+15\s*-\s*64\s+anni)"
    r"\s+(\d{1,3}(?:\.\d{3})*)"
    r"\s+([+-]?\d{1,4})\s+([+-]?\d{1,3},\d)"
    r"\s+([+-]?\d{1,4})\s+([+-]?\d{1,3},\d)"
    r"\s+([+-]?\d{1,4})\s+([+-]?\d{1,3},\d)\s*$",
    re.I,
)
MONTH_ROW = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(20\d{2})\b", re.I
)
GROUP = {"MASCHI": "maschi", "FEMMINE": "femmine", "TOTALE": "totale"}
EXPECTED_INDICATORS = {"Occupati", "Disoccupati", "Inattivi 15-64 anni"}


def _normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def extract_istat_labor_table(text: str, *, url: str, source_sha256: str,
                               page_number: int) -> list[dict]:
    """Fail closed unless all title, unit, period, fields and rows match."""
    if not text or not isinstance(text, str):
        return []
    source = urlsplit(url)
    if not (source.scheme == "https" and
            source.hostname in {"istat.it", "www.istat.it"} and
            re.fullmatch("[0-9a-f]{64}", source_sha256 or "")):
        return []
    lines = [_normalize_line(x) for x in text.splitlines()]
    joined = " ".join(lines).casefold()
    if not all(marker in joined for marker in (
        "prospetto 1.", "popolazione per genere e condizione professionale",
        "dati destagionalizzati", "variazioni tendenziali"
    )):
        return []
    if not re.search(r"\bmigliaia\s+di\s+unit[aà]\b", joined):
        return []
    period_match = MONTH_ROW.search(joined)
    if not period_match:
        return []
    period = (
        f"{period_match.group(2)}-{MONTHS[period_match.group(1).casefold()]:02}"
    )
    group = None
    out = []
    for line_number, line in enumerate(lines, 1):
        upper = line.upper()
        if upper in GROUP:
            group = GROUP[upper]
            continue
        match = ROW.fullmatch(line)
        if not match or not group:
            continue
        label = _normalize_line(match.group(1))
        label = next((x for x in EXPECTED_INDICATORS
                      if x.casefold() == label.casefold()), "")
        if not label:
            continue
        absolute_thousands = int(match.group(2).replace(".", ""))
        yoy_percent = float(match.group(8).replace(",", "."))
        previous_month_change_thousands = int(match.group(3))
        previous_year_change_thousands = int(match.group(7))
        if absolute_thousands <= 0 or abs(yoy_percent) > 100:
            continue
        out.append({
            "indicator": label,
            "unit": "persone",
            "source_table_unit": "migliaia_di_persone",
            "unit_multiplier": 1000,
            "observed_total": absolute_thousands * 1000,
            "reported_yoy_change_pct": yoy_percent,
            "reported_monthly_change_thousands": previous_month_change_thousands,
            "reported_yoy_change_thousands": previous_year_change_thousands,
            "source_count_thousands": absolute_thousands,
            "segment": {"territory": "Italia", "sex": group},
            "reference_period": period,
            "reference_comparison": "same_month_previous_year",
            "source_url": url,
            "source_sha256": source_sha256,
            "location": f"page:{page_number}:text:line:{line_number}",
            "extraction_method": "explicit_labor_monthly_table1_absolute_thousands_and_yoy",
            "verified": True,
            "publication_status": "workbench_only",
        })
    # Need the expected complete 3x3 table, otherwise the page was
    # split or reflowed: do not silently misattribute rows.
    keys = {(row["segment"]["sex"], row["indicator"]) for row in out}
    expected = {(sex, label) for sex in GROUP.values()
                for label in EXPECTED_INDICATORS}
    return out if len(out) == len(keys) == len(expected) and keys == expected else []


def extract_istat_labor_pdf(raw: bytes, url: str = SOURCE_URL) -> list[dict]:
    """Source-wide evidence locator; caller must have authenticated download."""
    if not raw.startswith(b"%PDF-"):
        raise ValueError("Not a PDF")
    source = urlsplit(url)
    if not (source.scheme == "https" and source.hostname in
            {"istat.it", "www.istat.it"}):
        raise ValueError("Only HTTPS ISTAT source allowed")
    import pdfplumber
    source_sha256 = hashlib.sha256(raw).hexdigest()
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page_number, page in enumerate(pdf.pages[:20], 1):
            rows = extract_istat_labor_table(
                page.extract_text() or "", url=url,
                source_sha256=source_sha256, page_number=page_number
            )
            if rows:
                return rows
    return []


def labor_research_signals(articles: list[dict]) -> list[dict]:
    """A sourced, noncausal comparison of employment categories by sex.

    Labor levels are NEVER combined as rates or treated as a
    population total, and reported YoY rates keep their own denominators.
    """
    outputs = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        source_url = (article.get("public_source") or {}).get("url")
        source_sha = article.get("source_sha256")
        if not source_url or not source_sha:
            continue
        groups = {}
        for row in article.get("document_findings") or []:
            if not isinstance(row, dict) or not (
                row.get("verified") is True
                and row.get("extraction_method")
                == "explicit_labor_monthly_table1_absolute_thousands_and_yoy"
                and row.get("source_url") == source_url
                and row.get("source_sha256") == source_sha
                and row.get("unit") == "persone"
                and row.get("unit_multiplier") == 1000
                and row.get("source_table_unit") == "migliaia_di_persone"
                and row.get("location")
                and row.get("indicator") in EXPECTED_INDICATORS
                and row.get("reference_comparison") == "same_month_previous_year"
                and re.fullmatch(r"20\d\d-(?:0[1-9]|1[0-2])",
                                 str(row.get("reference_period") or ""))
            ):
                continue
            group = row.get("segment")
            if not isinstance(group, dict) or group.get("territory") != "Italia" \
                    or group.get("sex") not in GROUP.values():
                continue
            try:
                observed = int(row["observed_total"])
                original = int(row["source_count_thousands"])
                rate = float(row["reported_yoy_change_pct"])
            except (ValueError, TypeError, KeyError):
                continue
            if observed <= 0 or observed != original * 1000 \
                    or not -100 <= rate <= 100:
                continue
            key = (row["reference_period"], group["sex"])
            groups.setdefault(key, {}).setdefault(row["indicator"], []).append(row)
        for (period, group), rows in groups.items():
            if not all(len(rows.get(kind, [])) == 1
                       for kind in ("Occupati", "Disoccupati", "Inattivi 15-64 anni")):
                continue
            selected = [rows[k][0] for k in ("Occupati", "Disoccupati",
                                              "Inattivi 15-64 anni")]
            if len({r["location"] for r in selected}) != 3:
                continue
            if len({r["source_sha256"] for r in selected}) != 1:
                continue
            outputs.append({
                "id": f"LABOR-{period}-{group}",
                "story_type": "labor_categories_yoy_evidence",
                "period": period,
                "population_group": group,
                "indicator_evidence": selected,
                "comparison": "different_category_yoy_changes_not_one_common_rate",
                "source_url": source_url,
                "source_sha256": source_sha,
                "source_locations": [r["location"] for r in selected],
                "publication_status": "research_only",
                "human_review_required": True,
                "not_official_pulse_pattern": True,
            })
    return outputs
