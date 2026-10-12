"""Auditable ISTAT tourism derived measure: average nights per arrival.

ISTAT defines permanenza media as presenze / arrivi for the same
period and type of accommodation. This module performs that operation
ONLY on a provenance-matched pair of official totals. The YoY direction
is certified through the complete possible range induced by published
one-decimal YoY percentages; it NEVER reconstructs fictitious prior
absolute totals or publishes an exact growth rate from rounded changes.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

ISTAT_METHOD_URL = "https://noi-italia.istat.it/pagina.php?L=0&categoria=8&dove=ITALIA"
ROUNDING_POINTS = Decimal("0.05")  # official changes shown to 0.1 pp


def _decimal(value: object) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid statistical value") from exc
    if not d.is_finite():
        raise ValueError("Non-finite statistical value")
    return d


def derive_average_stay(arrivals: dict, nights: dict) -> dict | None:
    """Return a traceable derived fact, or None if any precondition fails."""
    if not isinstance(arrivals, dict) or not isinstance(nights, dict):
        return None
    if str(arrivals.get("indicator", "")).casefold() != "arrivi":
        return None
    if str(nights.get("indicator", "")).casefold() != "presenze":
        return None
    if arrivals.get("unit") != "arrivi" or nights.get("unit") != "notti":
        return None
    if not all(arrivals.get(k) == nights.get(k) and arrivals.get(k)
               for k in ("source_url", "source_sha256", "period", "segment")):
        return None
    if not re.fullmatch(r"20\d\d-Q[1-4]", str(arrivals.get("period", ""))):
        return None
    if not all(
        p.get("proof_type") == "official_observed_total_and_reported_yoy"
        and p.get("source_location")
        for p in (arrivals, nights)
    ):
        return None
    if arrivals["source_location"] == nights["source_location"]:
        return None
    try:
        a, p = _decimal(arrivals["value"]), _decimal(nights["value"])
        a_change, p_change = (_decimal(arrivals["change_pct"]),
                              _decimal(nights["change_pct"]))
    except (KeyError, ValueError):
        return None
    if a <= 0 or p < 0 or a != a.to_integral_value() or p != p.to_integral_value():
        return None
    if a_change < -100 or p_change < -100 or a_change > 100 or p_change > 100:
        return None

    mean = p / a
    # Official table provides one-decimal YoY values. We report only the
    # direction that holds for ALL underlying rates consistent with rounding.
    a_min, a_max = a_change - ROUNDING_POINTS, a_change + ROUNDING_POINTS
    p_min, p_max = p_change - ROUNDING_POINTS, p_change + ROUNDING_POINTS
    direction = "not_determined"
    if a_min > -100 and p_min > -100:
        min_ratio = (Decimal(100) + p_min) / (Decimal(100) + a_max)
        max_ratio = (Decimal(100) + p_max) / (Decimal(100) + a_min)
        if min_ratio > 1:
            direction = "increased"
        elif max_ratio < 1:
            direction = "decreased"

    display = str(mean.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)).replace(".", ",")
    return {
        "metric": "permanenza_media",
        "value_nights_per_arrival": display,
        "calculated_unrounded": str(mean),
        "reference_period": arrivals["period"],
        "residence_and_structure": arrivals["segment"],
        "comparison_direction_rounded_yoy": direction,
        "rounding_assumption": "each official YoY percentage rounded to 0.1 percentage point",
        "formula": "official_presenze_total / official_arrivi_total",
        "origin": "independent_PULSE_calculation_from_ISTAT",
        "methodology_source_url": ISTAT_METHOD_URL,
        "source_url": arrivals["source_url"],
        "source_sha256": arrivals["source_sha256"],
        "source_locations": [arrivals["source_location"], nights["source_location"]],
        "status": "computed_from_two_verified_observations_not_official_published_measure",
    }
