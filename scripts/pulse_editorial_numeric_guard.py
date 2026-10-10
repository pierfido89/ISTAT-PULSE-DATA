"""PULSE Editorial numeric audit v1.2.

Check exact source values, Italian notation, known quarterly-period
references and direction of published year-on-year changes. Does not
invent previous-year totals or publish any content.
"""
from __future__ import annotations

import math
import re

NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:%)?")
DIRECTIONS = re.compile(
    r"\b(calo|calat[oaie]|diminuzion[ei]|diminuisc\w*|riduzion[ei]|"
    r"flession[ei]|sces[oaie]|scend\w*|contrazion[ei]|"
    r"aument[oaie]|aument\w*|increment[oaie]|increment\w*|"
    r"crescit[ae]|cresc\w*|salit[ae]|rialz[oaie])\b", re.I
)
NEGATIVE_PREFIXES = ("cal", "dimin", "riduz", "fless", "sces", "scend", "contraz")


def normal(raw: str) -> str:
    text = raw.strip().rstrip("%").lstrip("+")
    if "," in text:
        before, sep, after = text.rpartition(",")
        if not after.isdigit():
            return text
        return before.replace(".", "") + "." + after
    if "." in text:
        parts = text.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            return "".join(parts)
    return text


def decimal(value) -> str:
    f = float(value)
    if not math.isfinite(f):
        raise ValueError("non-finite number")
    return f"{f:.7f}".rstrip("0").rstrip(".")


def allowed_numbers(fact: dict) -> set[str]:
    values = [fact["value"]]
    values.extend(fact.get("additional_values", []))
    if fact.get("comparison"):
        change = fact["comparison"]
        values += [change["from_value"], change["to_value"], change["change"]]
    result = {decimal(v) for v in values}

    # Magnitude without sign is allowed for officially sourced percentages
    # because "in calo del 4,3%" is idiomatic Italian for a -4.3% change.
    yoy = fact.get("change_pct")
    if yoy is not None:
        result.add(decimal(yoy))
        result.add(decimal(abs(float(yoy))))
    period = str(fact.get("period") or "")
    result.update(re.findall(r"\b20\d\d\b", period))
    year_q = re.fullmatch(r"(20\d\d)-Q([1-4])", period)
    if year_q:
        year, quarter = map(int, year_q.groups())
        result.add(str(quarter))
        # Published YoY for the quarter DOES support naming the compared
        # year, without claiming that the old absolute total is known.
        if yoy is not None:
            result.add(str(year - 1))
    return result


def _direction_word(prefix: str) -> int | None:
    # Look only at the current sentence (not a previous claim).
    sentence = re.split(r"[.!?;:\n]", prefix)[-1]
    # Focus on the local clause, limiting unrelated words to 85 chars.
    found = list(DIRECTIONS.finditer(sentence[-85:]))
    if not found:
        return None
    last = found[-1].group(0).lower()
    return -1 if last.startswith(NEGATIVE_PREFIXES) else +1


def inspect_numbers(text: str, fact: dict) -> tuple[list[str], list[str]]:
    allowed = allowed_numbers(fact)
    unsupported: list[str] = []
    direction_issues: list[str] = []
    yoy = fact.get("change_pct")
    for m in NUMBER.finditer(text):
        raw = m.group(0)
        normalized = normal(raw)
        if normalized not in allowed:
            unsupported.append(raw)
            continue
        if yoy is None or not raw.endswith("%"):
            continue
        # Check only percentages equal to the official change magnitude.
        try:
            numeric = float(normalized)
        except ValueError:
            continue
        source = float(yoy)
        if abs(abs(numeric) - abs(source)) > 0.0000001:
            continue
        has_explicit_sign = raw.startswith(("+", "-"))
        sign = 1 if numeric > 0 else -1 if numeric < 0 else 0
        if sign == 0:
            continue
        if has_explicit_sign and sign != (1 if source > 0 else -1):
            direction_issues.append("wrong_yoy_sign")
        local_direction = _direction_word(text[:m.start()])
        if local_direction is not None and local_direction != (1 if source > 0 else -1):
            direction_issues.append("wrong_yoy_direction")
        # With no explicit sign/directional word, magnitude alone
        # cannot verify whether the claim is an increase or decrease.
        if not has_explicit_sign and local_direction is None:
            direction_issues.append("unqualified_yoy_direction")
    return unsupported, list(dict.fromkeys(direction_issues))


def present(text: str, value) -> bool:
    expected = decimal(value)
    return any(normal(m.group()) == expected for m in NUMBER.finditer(text))


def yoy_present(text: str, change: float) -> bool:
    target = decimal(abs(change))
    return any(m.group().endswith("%") and
               normal(m.group()).lstrip("-") == target
               for m in NUMBER.finditer(text))
