"""Official ISTAT full-PDF evidence adapters: demography, education, environment.

Deliberately source-specific and fail-closed. Every numeric observation
requires an explicit unit/period and a cited page/line in an authenticated
PDF download. Never promote a narrative quotation to verified numbers.
"""
from __future__ import annotations

import hashlib
import io
import re
from urllib.parse import urlsplit

SOURCES = {
    "popolazione": "https://www.istat.it/wp-content/uploads/2026/03/Report_Indicatori-demografici_Anno-2025.pdf",
    "istruzione": "https://www.istat.it/wp-content/uploads/2025/12/Report-Livelli-di-istruzione-e-ritorni-occupazionali-Anno-2024.pdf",
    "ambiente": "https://www.istat.it/wp-content/uploads/2026/10/Report_Raccolta-differenziata_Anni-2024-2025.pdf",
}
SHA = re.compile(r"^[0-9a-f]{64}$")
DEC = r"([0-9]{1,3},[0-9])"
INT = r"([0-9]{1,3}(?:\.[0-9]{3})?)"
AREA = {
    "Nord-ovest": "ITC",
    "Nord-est": "ITH",
    "Centro": "ITI",
    "Sud": "ITF",
    "Isole": "ITG",
}
DEMOGRAPHY_COLUMNS = [
    ("population_jan1", "popolazione inizio anno"),
    ("births", "nascite"),
    ("deaths", "decessi"),
    ("immigration_abroad", "immigrazioni dall'estero"),
    ("emigration_abroad", "emigrazioni per l'estero"),
    ("migration_from_other_municipality", "trasferimenti da altri Comuni"),
    ("migration_to_other_municipality", "trasferimenti verso altri Comuni"),
    ("population_dec31", "popolazione fine anno"),
]
EDUCATION_ROWS = {
    "Quota di 25-64enni con almeno un titolo secondario superiore":
        ("quota_secondario_superiore", "residenti 25-64 anni"),
    "Quota di 25-64enni con un titolo terziario":
        ("quota_titolo_terziario", "residenti 25-64 anni"),
    "Quota di 25-34enni con un titolo terziario":
        ("quota_titolo_terziario", "residenti 25-34 anni"),
    "Giovani 18-24 anni usciti precocemente dal sistema di istruzione e formazione":
        ("abbandono_precoce_istruzione", "residenti 18-24 anni"),
}
ENVIRONMENT_COLUMNS = (
    ("waste_per_capita", "rifiuti urbani pro capite", "kg_per_person", "resident_population"),
    ("separate_waste_share", "raccolta differenziata rifiuti urbani", "%", "all_municipal_waste"),
    ("residents_in_target_municipalities", "popolazione in Comuni almeno 65% differenziata", "%", "all_residents"),
    ("families_satisfied_home_collection", "famiglie soddisfatte porta a porta", "%", "surveyed_families"),
)
# Exact source-issued page 2 formats, not a generic numeric text guess.
ENV_ROW = re.compile(
    r"^(Nord-ovest|Nord-est|Centro|Sud|Isole|Italia)\s+"
    + r"\s+".join([DEC]*4) + r"$", re.I
)
DEM_ROW = re.compile(
    r"^(Nord|Nord-ovest|Nord-est|Centro|Mezzogiorno|Sud|Isole|ITALIA)\s+"
    + r"\s+".join([INT]*8) + r"$", re.I
)
EU_IT_YEAR_ROW = re.compile(
    r"^(.+?)\s+" + r"\s+".join([DEC]*6) + r"$"
)


def _lines(text: str):
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]


def _source_ok(url: str, sha: str, domain: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and
            parsed.hostname in {"www.istat.it", "istat.it"} and
            url == SOURCES[domain] and bool(SHA.fullmatch(sha)))


def demography_page(text: str, url: str, sha: str, page: int) -> list[dict]:
    if not _source_ok(url, sha, "popolazione"):
        return []
    lines = _lines(text)
    joined = " ".join(lines).casefold()
    if not all(x in joined for x in (
        "bilancio della popolazione residente per ripartizione geografica",
        "anno 2025", "valori in migliaia",
        "popolazione al", "nascite", "decessi",
    )):
        return []
    selected = []
    for idx, line in enumerate(lines, 1):
        m = DEM_ROW.fullmatch(line)
        if not m or m.group(1).upper() != "ITALIA":
            continue
        vals = [int(x.replace(".", "")) for x in m.groups()[1:]]
        if not (
            len(vals) == 8 and 50_000 < vals[0] < 75_000
            and 100 < vals[1] < 1_000 and 100 < vals[2] < 1_000
            and abs(vals[0]-vals[-1]) < 1_000
        ):
            return []
        selected.append((idx, vals))
    if len(selected) != 1:
        return []
    line_num, values = selected[0]
    result = []
    for (key, title), val in zip(DEMOGRAPHY_COLUMNS, values):
        result.append({
            "indicator": title,
            "indicator_code": key,
            "period": "2025",
            "reference_period": "2025",
            "unit": "migliaia_di_persone",
            "value": val,
            "rounded_at_thousands": True,
            "provisional": True,
            "not_exact_individual_counts": True,
            "segment": {"territory": "Italia", "population": "residenti"},
            "source_url": url, "source_sha256": sha,
            "location": f"page:{page}:text:line:{line_num}:col:{key}",
            "extraction_method": "official_demography_population_balance_2025",
            "verified": True, "publication_status": "research_only",
        })
    return result


def education_page(text: str, url: str, sha: str, page: int) -> list[dict]:
    """3 consecutive, independently presented annual observations each."""
    if not _source_ok(url, sha, "istruzione"):
        return []
    lines = _lines(text)
    joined = " ".join(lines).casefold()
    if not all(x in joined for x in (
        "livelli di istruzione e ritorni occupazionali",
        "i numeri chiave",
        "anni 2022, 2023 e 2024",
        "valori percentuali",
        "2022 - italia", "2023 - italia", "2024 - italia",
        "2022 - ue27", "2023 - ue27", "2024 - ue27",
    )):
        return []
    found = {}
    for idx, line in enumerate(lines, 1):
        m = EU_IT_YEAR_ROW.fullmatch(line)
        if not m:
            continue
        label = m.group(1).strip()
        meta = EDUCATION_ROWS.get(label)
        if not meta:
            continue
        if label in found:
            return []  # duplicated / ambiguous
        vals = [float(x.replace(",", ".")) for x in m.groups()[1:]]
        if len(vals) != 6 or any(not 0 <= x <= 100 for x in vals):
            continue
        found[label] = (idx, vals, meta)
    # 2 labeled, non-overlapping, representative time series are enough
    # to validate history. Reject partial extracted tables.
    mandatory = (
        "Quota di 25-64enni con un titolo terziario",
        "Quota di 25-34enni con un titolo terziario",
    )
    if any(label not in found for label in mandatory):
        return []
    output = []
    for label in mandatory:
        line_num, vals, (code, population) = found[label]
        for territory, three in (("Italia", vals[:3]), ("Ue27", vals[3:])):
            output.append({
                "indicator": label,
                "indicator_code": code,
                "unit": "%",
                "territory": territory,
                "population_scope": population,
                "source_url": url,
                "source_sha256": sha,
                "location": f"page:{page}:text:line:{line_num}:block:{territory}",
                "verified": True,
                "extraction_method": "same_row_explicit_year_structured_table",
                "observations": [
                    {"period": str(year), "value": value}
                    for year, value in zip((2022, 2023, 2024), three)
                ],
                "publication_status": "research_only",
            })
    return output


def environment_page(text: str, url: str, sha: str, page: int) -> list[dict]:
    if not _source_ok(url, sha, "ambiente"):
        return []
    lines = _lines(text)
    joined = " ".join(lines).casefold()
    if not all(x in joined for x in (
        "rifiuti urbani, raccolta differenziata e soddisfazione delle famiglie",
        "per ripartizione", "anni 2024-2025",
        "kg/abitante", "raccolta differenziata", "famiglie soddisfatte",
    )):
        return []
    found = {}
    for idx, line in enumerate(lines, 1):
        m = ENV_ROW.fullmatch(line)
        if not m:
            continue
        place = next((k for k in (*AREA, "Italia")
                      if k.casefold() == m.group(1).casefold()), None)
        if not place or place in found:
            return []
        vals = [float(v.replace(",", ".")) for v in m.groups()[1:]]
        if (len(vals) != 4 or not 100 < vals[0] < 900 or
                any(not 0 <= v <= 100 for v in vals[1:])):
            continue
        found[place] = (idx, vals)
    if not all(area in found for area in AREA) or "Italia" not in found:
        return []
    out = []
    for place in AREA:
        line_num, vals = found[place]
        for colno, (code, label, unit, denominator) in enumerate(ENVIRONMENT_COLUMNS):
            # The environmental source's waste quantities and collection
            # shares refer to 2024; family satisfaction is 2025.
            period = "2025" if code == "families_satisfied_home_collection" else "2024"
            out.append({
                "indicator": label, "indicator_code": code,
                "unit": unit, "denominator_id": denominator,
                "population_scope": (
                    "famiglie" if period == "2025"
                    else "residenti" if code in
                        {"waste_per_capita", "residents_in_target_municipalities"}
                    else "rifiuti urbani prodotti"
                ),
                "reference_period": period,
                "value": vals[colno],
                "territory": {
                    "name": place, "code": AREA[place], "level": "ripartizione"
                },
                "source_url": url, "source_sha256": sha,
                "location": f"page:{page}:text:line:{line_num}:col:{colno+1}",
                "verified": True,
                "extraction_method": "explicit_territorial_rate_table",
                "publication_status": "research_only",
            })
    return out


ADAPTERS = {
    "popolazione": demography_page,
    "istruzione": education_page,
    "ambiente": environment_page,
}


def extract_source_pdf(raw: bytes, url: str, domain: str):
    if domain not in SOURCES or url != SOURCES[domain] or not raw.startswith(b"%PDF-"):
        raise ValueError("Unapproved source or bytes")
    import pdfplumber
    digest = hashlib.sha256(raw).hexdigest()
    with pdfplumber.open(io.BytesIO(raw)) as doc:
        for page_num, page in enumerate(doc.pages[:25], 1):
            results = ADAPTERS[domain](
                page.extract_text() or "", url, digest, page_num
            )
            if results:
                return results
    return []



def demography_research_signals(articles: list[dict]) -> list[dict]:
    """Source-confirmed provisional demographic balance, not exact counts."""
    out = []
    expected = {x[0] for x in DEMOGRAPHY_COLUMNS}
    for a in articles:
        if not isinstance(a, dict):
            continue
        url = (a.get("public_source") or {}).get("url")
        sha = a.get("source_sha256")
        if not url or not sha:
            continue
        rows = {}
        for f in a.get("document_findings") or []:
            if not isinstance(f, dict) or not (
                f.get("verified") is True
                and f.get("extraction_method") == "official_demography_population_balance_2025"
                and f.get("source_url") == url and f.get("source_sha256") == sha
                and f.get("unit") == "migliaia_di_persone"
                and f.get("rounded_at_thousands") is True
                and f.get("provisional") is True
                and f.get("reference_period") == "2025"
                and f.get("location")
                and f.get("indicator_code") in expected
                and f.get("segment") == {"territory":"Italia", "population":"residenti"}
            ):
                continue
            rows.setdefault(f["indicator_code"], []).append(f)
        if set(rows) != expected or any(len(v) != 1 for v in rows.values()):
            continue
        ordered = [rows[key][0] for key, _ in DEMOGRAPHY_COLUMNS]
        if len({r["location"] for r in ordered}) != len(expected):
            continue
        out.append({
            "id": "POPULATION-2025-PROVISIONAL-BALANCE",
            "story_type": "provisional_population_balance_rounded_thousands",
            "period": "2025",
            "evidence": ordered,
            "source_url": url, "source_sha256": sha,
            "source_locations": [r["location"] for r in ordered],
            "precision_caveat": "Source figures rounded to thousands; provisional",
            "not_exact_individual_counts": True,
            "publication_status": "research_only",
        })
    return out
