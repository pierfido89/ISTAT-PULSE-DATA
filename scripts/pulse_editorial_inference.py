"""PULSE Editorial AI 1.0: conservative checks of ungrounded interpretations.

An evidence-backed claim must match the indicator and population scope of
the supplied fact. This lexical gate catches known failures; it CANNOT
establish truth or replace independent editorial review.
"""
from __future__ import annotations
import re


def inference_issues(text: str, fact: dict) -> list[str]:
    normalized = " ".join(str(text or "").casefold().split()).replace("’", "'")
    segment = " ".join(str(fact.get("segment") or "").casefold().split())
    indicator = str(fact.get("indicator") or "").casefold()
    issues = []

    if re.search(r"\b(?:dati|rilevazioni|statistiche)\s+(?:disponibili\s+per|"
                 r"prodott[ie]\s+da|raccolt[ie]\s+da|rilevat[ie]\s+da)\s+"
                 r"(?:l[' ]|da(?:ll[ao])?\s+)?istat\s*pulse\b", normalized) or \
       re.search(r"\b(?:secondo|dati di|rilevazioni di)\s+"
                 r"(?:l[' ]|da(?:ll[ao])?\s+)?istat\s*pulse\b", normalized):
        issues.append("misattributed_primary_source")

    # An arrival counts a check-in, not a person counted once per period.
    if re.search(r"\b(?:numero|quantità|totale)\s+(?:di|dei|delle)\s+"
                 r"(?:visitator[ie]|turist[ie])\b", normalized) or \
       re.search(r"\b(?:visitator[ie]|turist[ie])\s+(?:unici|distinti)\b", normalized):
        issues.append("arrivals_confused_with_unique_visitors")

    # A one-indicator candidate may not add other indicators from the PDF.
    if (re.search(r"\barrivi\b", normalized) and
            not re.search(r"\barrivi\b", indicator)) or \
       (re.search(r"\bpresenze\b", normalized) and
            not re.search(r"\bpresenze\b", indicator)):
        issues.append("secondary_indicator_without_evidence")

    nonresident = bool(re.search(r"\bnon[\s-]?residenti\b", segment))
    resident = bool(re.search(r"\bresidenti\b", segment)) and not nonresident
    if re.search(r"\bnon[\s-]?residenti\b", normalized) and not nonresident:
        issues.append("unsourced_population_nonresidents")
    without_nonresident = re.sub(r"\bnon[\s-]?residenti\b", "", normalized)
    if re.search(r"\bresidenti\b|\bsoggetti residenti\b", without_nonresident) and not resident:
        issues.append("unsourced_population_residents")

    ungrounded_groups = (
        r"\b(?:gruppi?\s+(?:più\s+)?stabil[ie]|"
        r"gruppi?\s+(?:organizzat[ie]|numeros[ie])|"
        r"famigl[iea]|nuclei familiari|stranier[ie]|turismo domestico|"
        r"composizione dei visitatori)\b"
    )
    for match in re.finditer(ungrounded_groups, normalized):
        if match.group(0) not in segment:
            issues.append("unsourced_visitor_group")
            break

    # A reliable change in average length of stay requires both observed
    # arrivals and nights, with a compatible population and denominator.
    if re.search(r"\b(?:permanenza media|durata media (?:del )?soggiorno|"
                 r"soggiorni?\s+(?:più|maggiormente)\s+lungh[ie]|"
                 r"notti?\s+per\s+arrivo)\b", normalized) and \
       not fact.get("paired_arrivals_nights_verified", False):
        issues.append("unsupported_average_stay")

    if re.search(r"\b(?:maggiore|aumentato|crescente)\s+utilizzo\s+del\s+servizio\b|"
                 r"\bgruppi?\s+(?:più\s+)?stabil[ie]\b", normalized):
        issues.append("unsupported_behavioral_explanation")

    return list(dict.fromkeys(issues))
