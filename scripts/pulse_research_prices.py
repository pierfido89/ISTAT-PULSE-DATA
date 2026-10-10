"""Strict ISTAT August 2026 CPI Prospetto 1 numeric extraction.

The three indices NIC, IPCA, FOI use index 2025=100 and each own
population basket. Compare published YoY rates, NEVER equate level
indices with prices paid by all households. No LLM or guesses.
"""
from __future__ import annotations
import hashlib
import io
import re
from urllib.parse import urlsplit

SOURCE_URL = "https://www.istat.it/wp-content/uploads/2026/09/CS_Prezzi-al-consumo_Def_Agosto2026.pdf"
ROW = re.compile(
    r"^(Indice nazionale per l[’']intera collettivit[aà] NIC|"
    r"Indice armonizzato IPCA|"
    r"Indice per le famiglie di operai e impiegati FOI \(senza tabacchi\))"
    r"\s+(\d{2,3},\d)\s+([+-]?\d{1,2},\d)\s+([+-]?\d{1,2},\d)$",
    re.I,
)
LABELS = {
    "Indice armonizzato IPCA": "IPCA",
    "Indice per le famiglie di operai e impiegati FOI (senza tabacchi)": "FOI",
    "Indice nazionale per l’intera collettività NIC": "NIC",
}


def extract_istat_cpi_table(text: str, *, url: str, source_sha256: str,
                             page_number: int) -> list[dict]:
    if not isinstance(text, str) or not text:
        return []
    parsed = urlsplit(url)
    if not (parsed.scheme == "https" and parsed.hostname in ("www.istat.it", "istat.it")
            and re.fullmatch("[0-9a-f]{64}", source_sha256 or "")):
        return []
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    joined = " ".join(lines).casefold()
    required = [
        "prospetto 1. indici dei prezzi al consumo nic, ipca e foi",
        "agosto 2026",
        "base 2025=100",
        "variazioni congiunturali",
        "variazioni tendenziali",
    ]
    if not all(x in joined for x in required):
        return []
    found = []
    for line_no, line in enumerate(lines, 1):
        match = ROW.fullmatch(line)
        if not match:
            continue
        label = match.group(1).replace("'", "’")
        code = LABELS.get(label)
        if not code:
            continue
        level, mom, yoy = [
            float(x.replace(",", "."))
            for x in (match.group(2), match.group(3), match.group(4))
        ]
        if not 50 < level < 200 or not -100 < mom < 100 or not -100 < yoy < 100:
            continue
        found.append({
            "indicator": f"Indice prezzi {code}",
            "price_index_code": code,
            "unit": "indice_base_2025_100",
            "observed_index": level,
            "reported_monthly_change_pct": mom,
            "reported_yoy_change_pct": yoy,
            "segment": {"territory": "Italia", "basket": code},
            "reference_period": "2026-08",
            "reference_comparison": "same_month_previous_year",
            "source_url": url,
            "source_sha256": source_sha256,
            "location": f"page:{page_number}:text:line:{line_no}",
            "extraction_method": "explicit_cpi_prospetto1_three_index_monthly_and_yoy",
            "verified": True,
            "publication_status": "research_workbench_only",
            "methodology_note": "Three different consumer price index baskets; never merge index levels",
        })
    found_codes = [row["price_index_code"] for row in found]
    return found if len(found_codes) == 3 and set(found_codes) == {"NIC", "IPCA", "FOI"} else []


def extract_istat_cpi_pdf(raw: bytes, url: str = SOURCE_URL) -> list[dict]:
    if not raw.startswith(b"%PDF-"):
        raise ValueError("Not a PDF")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("www.istat.it", "istat.it"):
        raise ValueError("Only HTTPS ISTAT source allowed")
    import pdfplumber
    digest = hashlib.sha256(raw).hexdigest()
    with pdfplumber.open(io.BytesIO(raw)) as doc:
        for pno, page in enumerate(doc.pages[:25], 1):
            rows = extract_istat_cpi_table(page.extract_text() or "", url=url,
                                           source_sha256=digest, page_number=pno)
            if rows:
                return rows
    return []


def price_research_signals(articles: list[dict]) -> list[dict]:
    signals = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = (article.get("public_source") or {}).get("url")
        sha = article.get("source_sha256")
        if not url or not sha:
            continue
        pool = {}
        for fact in article.get("document_findings") or []:
            if not isinstance(fact, dict):
                continue
            if not (fact.get("verified") is True
                    and fact.get("extraction_method")
                    == "explicit_cpi_prospetto1_three_index_monthly_and_yoy"
                    and fact.get("unit") == "indice_base_2025_100"
                    and fact.get("source_url") == url
                    and fact.get("source_sha256") == sha
                    and fact.get("location")
                    and fact.get("reference_period") == "2026-08"
                    and fact.get("price_index_code") in {"NIC", "IPCA", "FOI"}):
                continue
            pool.setdefault(fact["price_index_code"], []).append(fact)
        if set(pool) != {"NIC", "IPCA", "FOI"} or any(len(x) != 1 for x in pool.values()):
            continue
        ordered = [pool[k][0] for k in ("NIC", "IPCA", "FOI")]
        if len({f["location"] for f in ordered}) != 3:
            continue
        signals.append({
            "id": "PRICES-NIC-IPCA-FOI-2026-08",
            "story_type": "different_price_baskets_yoy_rates",
            "evidence": ordered,
            "comparison": "three_independent_price_baskets_rates_not_common_index_level",
            "source_url": url, "source_sha256": sha,
            "source_locations": [f["location"] for f in ordered],
            "publication_status": "research_only",
            "not_official_pulse_pattern": True,
        })
    return signals
