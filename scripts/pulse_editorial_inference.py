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

    # A one-indicator story cannot make a second factual claim.
    # Explicit distinctions ("arrivi, non presenze") are explanatory,
    # not claims about the second indicator.
    def asserts_extra_indic(name):
        if not re.search(r"\b" + name + r"\b", normalized):
            return False
        for match in re.finditer(r"\b" + name + r"\b", normalized):
            prefix = normalized[max(0, match.start()-40):match.start()]
            if re.search(r"\bnon\s+(?:(?:alle|le|dei|delle|di|sulle|sui|agli|i)\s+)?$", prefix):
                continue
            return True
        return False

    if (asserts_extra_indic("arrivi") and "arrivi" not in indicator) or \
       (asserts_extra_indic("presenze") and "presenze" not in indicator):
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

    # Quarter ≠ four-month or six-month period: reject an incorrect label
    # even when no unsourced numeric token is present.
    period = str(fact.get("period") or "")
    if re.fullmatch(r"20\d\d-Q[1-4]", period):
        if re.search(r"\bquadrimestr\w*|\bsemestr\w*", normalized):
            issues.append("wrong_period_duration")
        # A 2026-Q2 observation is never "first quarter" or Q3.
        q = int(period[-1])
        ordinals = {"primo": 1, "secondo": 2, "terzo": 3, "quarto": 4,
                    "i": 1, "ii": 2, "iii": 3, "iv": 4}
        for match in re.finditer(r"\b(primo|secondo|terzo|quarto|i|ii|iii|iv)\s+trimestre\b",
                                  normalized):
            if ordinals[match.group(1)] != q:
                issues.append("wrong_quarter_number")
                break

    # Terms identifying a DIFFERENT kind of tourist accommodation
    # cannot be inferred from a row labelled 'esercizi alberghieri'.
    if "alberghier" in segment and re.search(
            r"\b(?:bed\s*(?:&|and|e)\s*breakfast|b\s*&\s*b|"
            r"campegg[iio]|agriturism[iio]|ostell[iio]|case\s+vacanz[ae])\b",
            normalized):
        issues.append("unsourced_accommodation_type")

    # 'Residenti' modifies the tourists/customers, not the properties.
    if re.search(r"\b(?:esercizi|strutture|alberghi)\s+"
                 r"(?:alberghier[ie]\s+)?(?:non\s+)?residenti\b", normalized):
        issues.append("misassigned_residence_to_facilities")
    if re.search(r"\b(?:esercizi|strutture)\s+(?:alberghier[ie]\s+)?"
                 r"dedicat[ie]\s+ai\s+non\s+residenti\b", normalized):
        issues.append("unsupported_accommodation_exclusivity")

    return list(dict.fromkeys(issues))
