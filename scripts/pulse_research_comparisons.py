"""Historically and territorially comparable RESEARCH signals, no AI.

Historical comparisons require an explicitly verified contiguous ANNUAL
series with source hash/locator and consistent dimension contract.
Territorial comparisons require independently verified RATES (not raw
population-size-sensitive totals), same source, period, group, unit,
denominator and territory level. Nothing is published automatically.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import math
import re

try:
    from scripts.pulse_editorial_evidence import METHODS, _observations
except ModuleNotFoundError:
    from pulse_editorial_evidence import METHODS, _observations

_SHA = re.compile(r"[0-9a-f]{64}", re.I)
_HTTPS = re.compile(r"https://[^ ]+")
_PERIOD = re.compile(r"20[0-9]{2}(?:-Q[1-4])?")
_RATE_UNITS = {"%", "per_1000", "per_100000", "index_100"}


def _sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _decimal(val: object) -> Decimal | None:
    try:
        x = Decimal(str(val))
        return x if x.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _source_authorized(article: dict, url: str, source_sha: str) -> bool:
    base = (article.get("public_source") or {})
    if (base.get("role") != "primary_statistical_source"
            or base.get("url") != url or not _HTTPS.fullmatch(url)
            or not _sha(source_sha)):
        return False
    reading = article.get("document_reading")
    if reading:
        return (isinstance(reading, dict)
                and reading.get("source_sha256") == source_sha
                and reading.get("source_url") == url)
    return True


def historical_signals(articles: list[dict]) -> list[dict]:
    found = []
    unique = set()
    for article in articles:
        if not isinstance(article, dict):
            continue
        for series in article.get("verified_series") or []:
            if not isinstance(series, dict):
                continue
            url = series.get("source_url") or ""
            sha = series.get("source_sha256") or ""
            if (series.get("verified") is not True
                    or series.get("extraction_method") not in METHODS
                    or not _source_authorized(article, url, sha)
                    or not str(series.get("location") or "").strip()
                    or not series.get("territory")
                    or not series.get("indicator")
                    or not series.get("unit")
                    or not series.get("population_scope")):
                continue
            rows = _observations(series)
            if len(rows) < 2:
                continue
            begin, end = _decimal(rows[0][1]), _decimal(rows[-1][1])
            if begin is None or end is None:
                continue
            key = (url, sha, series["location"],
                   str(series["indicator"]), str(series["territory"]),
                   str(series["population_scope"]), str(series["unit"]))
            if key in unique:
                continue
            unique.add(key)
            delta = end - begin
            direction = "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged"
            changes = [(rows[i][1]-rows[i-1][1]) for i in range(1, len(rows))]
            monotone = (
                len(rows) >= 4
                and (all(x > 0 for x in changes) or all(x < 0 for x in changes))
            )
            found.append({
                "id": f"HISTORY-{len(found)+1}",
                "story_type": "verified_annual_series",
                "indicator": series["indicator"],
                "unit": series["unit"],
                "territory": series["territory"],
                "population_scope": series["population_scope"],
                "periods": [int(y) for y, _ in rows],
                "first_value": str(begin),
                "last_value": str(end),
                "absolute_change": str(delta),
                "percent_change_from_first": (
                    str((delta / begin * 100).quantize(Decimal("0.01")))
                    if begin != 0 else None
                ),
                "comparison_direction": direction,
                "monotone_at_least_four_years": monotone,
                "source_url": url,
                "source_sha256": sha,
                "source_location": series["location"],
                "extraction_method": series["extraction_method"],
                "status": "research_only_human_review_required",
                "not_official_pulse_pattern": True,
            })
    return found


def _territorial_row(article: dict, row: dict) -> dict | None:
    if not isinstance(row, dict) or row.get("verified") is not True:
        return None
    if row.get("extraction_method") != "explicit_territorial_rate_table":
        return None
    url, sha = row.get("source_url") or "", row.get("source_sha256") or ""
    if not _source_authorized(article, url, sha):
        return None
    territory = row.get("territory")
    if (not isinstance(territory, dict) or
            not all(str(territory.get(k) or "").strip()
                    for k in ("name", "code", "level"))):
        return None
    period = row.get("reference_period")
    if not isinstance(period, str) or not _PERIOD.fullmatch(period):
        return None
    if not all(isinstance(row.get(k), str) and row[k].strip()
               for k in ("indicator", "unit", "denominator_id",
                         "population_scope", "location")):
        return None
    if row["unit"] not in _RATE_UNITS:
        return None
    val = _decimal(row.get("value"))
    if val is None or (row["unit"] == "%" and not (0 <= val <= 100)):
        return None
    return {
        "territory": territory,
        "period": period,
        "value": val,
        "indicator": row["indicator"],
        "unit": row["unit"],
        "denominator_id": row["denominator_id"],
        "population_scope": row["population_scope"],
        "age_scope": str(row.get("age_scope") or ""),
        "sex_scope": str(row.get("sex_scope") or ""),
        "source_url": url,
        "source_sha256": sha,
        "source_location": row["location"],
    }


def territorial_signals(articles: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for article in articles:
        if not isinstance(article, dict):
            continue
        for item in article.get("document_findings") or []:
            row = _territorial_row(article, item)
            if row is None:
                continue
            t = row["territory"]
            key = (
                row["source_url"], row["source_sha256"], row["period"],
                row["indicator"].casefold(), row["unit"],
                row["denominator_id"], row["population_scope"],
                row["age_scope"], row["sex_scope"], t["level"],
            )
            groups[key].append(row)
    output = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        codes = [str(r["territory"]["code"]) for r in group]
        # Ambiguous duplicated code invalidates group. No cherry-picking.
        if len(codes) != len(set(codes)):
            continue
        ordered = sorted(group, key=lambda r: (r["value"], r["territory"]["code"]))
        low, high = ordered[0], ordered[-1]
        if low["value"] == high["value"]:
            continue
        diff = high["value"] - low["value"]
        output.append({
            "id": f"TERRITORY-{len(output)+1}",
            "story_type": "rate_territorial_contrast",
            "indicator": high["indicator"],
            "unit": high["unit"],
            "population_scope": high["population_scope"],
            "denominator_id": high["denominator_id"],
            "period": high["period"],
            "territorial_level": high["territory"]["level"],
            "low": {
                "name": low["territory"]["name"], "code": low["territory"]["code"],
                "value": str(low["value"]), "source_location": low["source_location"],
            },
            "high": {
                "name": high["territory"]["name"], "code": high["territory"]["code"],
                "value": str(high["value"]), "source_location": high["source_location"],
            },
            "gap": str(diff),
            "gap_unit": "percentage_points" if high["unit"] == "%" else high["unit"],
            "number_of_verified_territories": len(group),
            "source_url": high["source_url"],
            "source_sha256": high["source_sha256"],
            "status": "research_only_human_review_required",
            "not_statistical_significance": True,
            "no_unjustified_raw_total_comparison": True,
        })
    return output
