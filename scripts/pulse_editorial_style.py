"""Style signals for Qwen's drafts; not statistical truth certification.

Warnings only: the human editor still decides whether the article is useful.
"""
from __future__ import annotations
import re


def style_warnings(headline: str, lead: str, body: str, fact: dict) -> list[str]:
    t = " ".join((headline, lead, body)).casefold().replace("’", "'")
    warnings = []
    if re.search(r"\b(?:il valore è stato osservato|osservato e confrontato"
                 r" ufficialmente|senza (?:modifiche|arrotondamenti)|"
                 r"la variabilità è (?:riferita|confermata))\b", t):
        warnings.append("boilerplate_instead_of_reporting")
    if re.search(r"\bdel\s+(?:1|8)[,.]\d+%|\bdel\s+0[,.]\d+%", t):
        warnings.append("nonidiomatic_percentage_article")
    try:
        value = f"{int(fact['value']):,}".replace(",", ".")
        occurrences = sum(value in p for p in (lead, body))
        if occurrences == 2:
            warnings.append("repeat_total_in_lead_and_body")
    except (TypeError, ValueError, KeyError):
        pass
    if (headline.casefold().startswith("i dati") or
        re.search(r"\b(?:l'analisi deve essere interpretata con cautela|"
                  r"non riflette tendenze di lungo termine|"
                  r"non permett[eoa] di (?:affermare|stabilire) "
                  r"(?:l'esistenza di )?una tendenza di lungo termine)\b", t)):
        warnings.append("generic_caution_instead_of_context")
    # The user-facing headline should signal the change, not merely label
    # a statistical table. This is a warning, not a statistical rejection.
    if fact.get("change_pct") not in (None, 0):
        if not re.search(
            r"\b(?:calo|cal\w*|flession[ei]|riduzion[ei]|diminuzion[ei]|"
            r"decrement[ioa]|crescit[ae]|increment[ioa]|aument\w*|"
            r"salit[ae]|sces[oa]|scend\w*)\b|[+-]\s*\d+(?:[,.]\d+)?\s*%",
            headline.casefold()
        ):
            warnings.append("headline_only_labels_indicator")

    body_norm = " ".join(body.casefold().split())
    if re.search(
        r"\b(?:i dati mostrano un|hanno registrato un|si registra un|"
        r"variazione tendenziale (?:negativa|positiva)|"
        r"confermando una tendenza)\b", body_norm):
        warnings.append("body_restates_change_instead_of_explaining")
    if re.search(r"\b(?:locali alberghieri|"
                 r"valore osservato (?:e|nel)|"
                 r"periodo (?:di riferimento|considerato))\b", body_norm):
        warnings.append("generic_or_imprecise_wording")
    return warnings
