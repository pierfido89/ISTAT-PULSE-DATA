"""PULSE Deep Reading v1: evidence-first, non-generative editorial enrichments.

No single quoted figure (nor a press headline) can certify a statistical
pattern. Verified findings remain candidates until editorial review.
"""
from __future__ import annotations
import datetime as dt
import math
import re
import statistics
from urllib.parse import urlsplit

PATTERNS = {
    "INVERSIONE", "ACCELERAZIONE", "RALLENTAMENTO", "RECORD",
    "ANOMALIA", "DIVERGENZA_TERRITORIALE",
}
ALIASES = {"DIVERGENZA": "DIVERGENZA_TERRITORIALE"}
METHODS = {
    "same_row_explicit_year_html_table",
    "same_row_explicit_year_structured_table",
    "sdmx_csv_explicit_dimensions",
    "sdmx_xml_explicit_series_dimensions",
    "sdmx_flat_json_explicit_dimensions",
    "sdmx_json_indexed_resolved_dimensions",
}
GLOSSARY = {
    "arrivi": "Numero di clienti che iniziano un soggiorno negli esercizi ricettivi; non è il numero delle notti.",
    "presenze": "Numero di notti trascorse dai clienti negli esercizi ricettivi.",
    "variazione tendenziale": "Variazione rispetto allo stesso periodo dell'anno precedente.",
    "punti percentuali": "Differenza aritmetica fra due percentuali, distinta dalla variazione percentuale relativa.",
    "pressione fiscale": "Rapporto percentuale tra entrate fiscali e contributive e PIL, secondo la definizione della fonte.",
    "potere d'acquisto": "Capacità di acquisto associata al reddito disponibile reale delle famiglie.",
}
MONTHS = dict(zip(
    ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
     "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"),
    range(1, 13)
))

def _host(url):
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""

def _observations(series):
    if not isinstance(series, dict) or series.get("verified") is not True:
        return []
    if series.get("extraction_method") not in METHODS:
        return []
    if not series.get("unit") or not series.get("indicator"):
        return []
    rows = series.get("observations") or []
    output = []
    for p in rows:
        if not isinstance(p, dict) or not re.fullmatch(r"(?:19|20)\d{2}", str(p.get("period", ""))):
            return []
        try:
            value = float(p["value"])
        except (TypeError, ValueError, KeyError):
            return []
        if not math.isfinite(value) or (series["unit"] == "%" and not (0 <= value <= 100)):
            return []
        output.append((int(p["period"]), value))
    if len(output) != len({period for period, _ in output}):
        return []
    output.sort()
    if any(y2 - y1 != 1 for (y1, _), (y2, _) in zip(output, output[1:])):
        return []
    return output

def _authorized_series(article):
    source = (article.get("public_source") or {}).get("url") or ""
    origin = _host(source)
    if not source.startswith("https://") or not origin:
        return []
    valid = []
    for series in article.get("verified_series") or []:
        if not isinstance(series, dict) or _host(series.get("source_url", "")) != origin:
            continue
        observations = _observations(series)
        if len(observations) >= 2:
            valid.append((series, observations))
    return valid

def _prove(pattern, series, rows):
    vals = [x[1] for x in rows]
    n = len(vals)
    if pattern == "RECORD" and n >= 5:
        previous = vals[:-1]
        return vals[-1] > max(previous) or vals[-1] < min(previous)
    if pattern == "ANOMALIA" and n >= 9:
        baseline = vals[:-1]
        center = statistics.median(baseline)
        mad = statistics.median(abs(x-center) for x in baseline)
        return mad > 0 and abs(vals[-1]-center) / (1.4826*mad) >= 3.5
    if n < 4:
        return False
    a, b, c = (vals[-3]-vals[-4], vals[-2]-vals[-3], vals[-1]-vals[-2])
    if pattern == "INVERSIONE":
        return a*b > 0 and b*c < 0 and abs(c) > 1e-10
    if pattern == "ACCELERAZIONE":
        return a*b > 0 and b*c > 0 and abs(c) > abs(b)*1.2 and abs(b) >= abs(a)*0.8
    if pattern == "RALLENTAMENTO":
        return a*b > 0 and b*c > 0 and abs(c) < abs(b)*0.8 and abs(b) <= abs(a)*1.25
    # Divergence requires an explicit, independently verified same-period
    # territorial benchmark and is withheld until that contract is available.
    return False

def validate_patterns(article):
    proposed = [ALIASES.get(str(p).upper(), str(p).upper())
                for p in (article.get("patterns") or [])]
    proposed = list(dict.fromkeys(proposed))
    authorized = _authorized_series(article)
    approved, evidence, withheld = [], [], []
    for pattern in proposed:
        if pattern not in PATTERNS:
            withheld.append({"pattern": pattern, "reason": "unknown_pattern"})
            continue
        witness = next(((series, rows) for series, rows in authorized
                        if _prove(pattern, series, rows)), None)
        if witness is None:
            withheld.append({"pattern": pattern, "reason": "insufficient_comparable_series"})
            continue
        series, rows = witness
        approved.append(pattern)
        evidence.append({
            "pattern": pattern,
            "indicator": series["indicator"],
            "source_url": series["source_url"],
            "source_location": series.get("location"),
            "periods": [str(p) for p, _ in rows],
            "method": series["extraction_method"],
            "unit": series["unit"],
            "rule_version": "1.0",
        })
    article["patterns_proposed"] = proposed
    article["patterns"] = approved
    article["pattern_evidence"] = evidence
    article["patterns_withheld"] = withheld
    article["pattern_validation_status"] = (
        "verified_from_series" if approved else
        "not_applicable" if not proposed else "insufficient_evidence"
    )
    # These titles assert a superlative even without a formal PULSE tag.
    # Withhold them rather than pretending the text is supported.
    if "RECORD" not in approved and re.search(
        r"\b(?:record storico|livelli record|nuovo record|massimo storico|mai cos[iì])\b",
        article.get("headline", ""), re.I
    ):
        if article.get("publication_status") == "published":
            article["publication_status"] = "requires_quality_review"
            article["quality_hold_reason"] = "unverified_historical_superlative"
    return article

def extract_phenomena(article, limit=12):
    """Distinct independently comparable series, not auto-published stories."""
    unique = set()
    findings = []
    for series, rows in _authorized_series(article):
        key = (
            _host(series.get("source_url", "")),
            str(series.get("indicator", "")).strip().casefold(),
            str(series.get("unit", "")).strip(),
            str(series.get("territory", "")).strip().casefold(),
            tuple(period for period, _ in rows),
        )
        if key in unique:
            continue
        unique.add(key)
        left, right = rows[-2], rows[-1]
        change = round(right[1]-left[1], 6)
        unit = "punti percentuali" if series["unit"] == "%" else series["unit"]
        findings.append({
            "indicator": series["indicator"],
            "unit": series["unit"],
            "territory": series.get("territory") or None,
            "comparison": {"from": str(left[0]), "to": str(right[0]),
                           "from_value": left[1], "to_value": right[1],
                           "change": change, "change_unit": unit},
            "source_url": series["source_url"],
            "location": series.get("location"),
            "source_sha256": series.get("source_sha256"),
            "extraction_method": series["extraction_method"],
            "editorial_status": "candidate_not_published",
        })
        if len(findings) >= limit:
            break
    article["editorial_findings"] = findings
    article["findings_status"] = "multiple_evidenced" if len(findings) > 1 else (
        "one_evidenced" if findings else "insufficient_structured_evidence")
    return article

def source_metadata_from_text(text):
    """Only explicit source statements, never dates inferred from news-cycle."""
    preview = re.sub(r"\s+", " ", text or "")[:6000]
    low = preview.casefold()
    prov = bool(re.search(r"\b(?:dati|stime) provvisor[ie]\b", low))
    defi = bool(re.search(r"\b(?:dati|stime) definitiv[ie]\b", low))
    status = "provisional" if prov and not defi else (
        "final" if defi and not prov else "not_declared")
    next_release = None
    match = re.search(
        r"prossima\s+diffusione\s*[:\-]?\s*(\d{1,2})\s+"
        r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
        r"settembre|ottobre|novembre|dicembre)\s+(20\d{2})",
        low
    )
    if match:
        try:
            next_release = dt.date(int(match[3]), MONTHS[match[2]], int(match[1])).isoformat()
        except ValueError:
            next_release = None
    return {
        "data_status": status,
        "next_release_date": next_release,
        "next_release_source": "explicit_primary_document" if next_release else None,
        "methodology_note": "Fonte primaria; solo confronti omogenei documentati; nessuna stima di valori mancanti.",
    }

def enrich(article, *, official_text=None):
    validate_patterns(article)
    extract_phenomena(article)
    if official_text is not None:
        article["source_methodology"] = source_metadata_from_text(official_text)
    else:
        article.setdefault("source_methodology", source_metadata_from_text(""))
    searchable = " ".join([str(article.get("headline") or ""),
                           str(article.get("summary") or "")] +
                          [str(s.get("indicator") or "") for s in article.get("verified_series") or []] +
                          [str(s.get("indicator") or "") for s in article.get("document_findings") or []]).casefold()
    article["glossary_entries"] = [
        {"term": term, "definition": description}
        for term, description in GLOSSARY.items()
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", searchable)
    ][:5]
    return article

def enrich_all(articles):
    for article in articles:
        enrich(article)
    return articles
