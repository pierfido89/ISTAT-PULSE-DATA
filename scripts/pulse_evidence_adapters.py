"""Source attachment discovery and SDMX evidence adapters for ISTAT PULSE.

Fail-closed: no mixing dimensions or units; metadata revisions block comparisons.
"""
from __future__ import annotations
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

ALLOWED_EXT = (".pdf", ".xlsx", ".xls", ".csv", ".tsv", ".json")
YEAR = re.compile(r"(?:19|20)\d{2}$")
REVISIONS = ("break in series", "series break", "methodological break", "rottura di serie",
             "cambio metodologia", "non comparabile", "not comparable")


def discover_attachments(html, page_url, max_links=20):
    """Discover same-origin downloadable attachments from an official publication page."""
    from scripts.pulse_evidence import validate_source_url
    validate_source_url(page_url)
    origin = urlparse(page_url).hostname
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for tag in soup.select("a[href]"):
        url = urljoin(page_url, tag.get("href", ""))
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != origin:
            continue
        if not parsed.path.lower().endswith(ALLOWED_EXT):
            continue
        if url not in found:
            found.append(url)
        if len(found) >= max_links:
            break
    return found


def compare_observations(observations, *, source_url, dataset, indicator,
                         unit, territory, method_id, revision_notes=""):
    """Compare adjacent observations only inside an identical dimensional series."""
    if not source_url.startswith("https://"):
        return {"status": "rejected", "reason": "source_url"}
    if not all((dataset, indicator, unit, territory, method_id)):
        return {"status": "rejected", "reason": "missing_dimensions"}
    if any(flag in revision_notes.lower() for flag in REVISIONS):
        return {"status": "rejected", "reason": "methodological_break"}
    rows = []
    for obs in observations:
        year = str(obs.get("period", ""))
        try:
            value = float(obs.get("value"))
        except (ValueError, TypeError):
            continue
        if YEAR.fullmatch(year) and value == value and abs(value) != float("inf"):
            rows.append((int(year), value))
    rows = sorted(set(rows))
    if len(rows) < 2:
        return {"status": "rejected", "reason": "insufficient_observations"}
    before, after = rows[-2:]
    if after[0] - before[0] != 1:
        return {"status": "rejected", "reason": "non_adjacent_years"}
    if unit == "%" and (not 0 <= before[1] <= 100 or not 0 <= after[1] <= 100):
        return {"status": "rejected", "reason": "invalid_percentage"}
    delta = after[1] - before[1]
    delta_unit = "punti percentuali" if unit == "%" else unit
    return {"status": "verified", "indicator": indicator, "unit": unit,
            "territory": territory, "dataset": dataset, "method_id": method_id,
            "source_url": source_url, "observations": [
                {"period": str(before[0]), "value": before[1]},
                {"period": str(after[0]), "value": after[1]}],
            "delta": round(delta, 6), "comparison_unit": delta_unit,
            "review_status": "automated_structural_check", "verified": True}


def parse_sdmx_csv(content, source_url):
    """SDMX CSV 2-style records: retain every dimension, no cross-key comparisons."""
    import csv, io
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    time_key = next((k for k in ("TIME_PERIOD", "TIME") if k in fields), None)
    value_key = next((k for k in ("OBS_VALUE", "OBS_VALUE_NUMERIC") if k in fields), None)
    if not time_key or not value_key:
        return {"status": "unsupported_schema", "evidence": []}
    dimension_fields = [f for f in fields if f not in {
        time_key, value_key, "OBS_STATUS", "DECIMALS", "OBS_CONF", "UNIT_MULT"}]
    groups = {}
    for row in reader:
        key = tuple((k, row.get(k, "")) for k in dimension_fields)
        groups.setdefault(key, []).append({"period": row.get(time_key), "value": row.get(value_key)})
    evidence = []
    for key, rows in groups.items():
        dims = dict(key)
        unit = dims.get("UNIT_MEASURE") or dims.get("UNIT") or ""
        territory = dims.get("REF_AREA") or dims.get("GEO") or ""
        indicator = dims.get("INDICATOR") or dims.get("MEASURE") or dims.get("KEY") or ""
        dataset = dims.get("DATAFLOW") or dims.get("DATAFLOW_ID") or ""
        method = dims.get("METHODOLOGY") or dims.get("METHODOLOGY_ID") or ""
        result = compare_observations(
            rows, source_url=source_url, dataset=dataset, indicator=indicator,
            unit=unit, territory=territory, method_id=method,
            revision_notes=dims.get("COMMENT_OBS", "") + " " + dims.get("BREAK_IN_SERIES", ""))
        if result["status"] == "verified":
            result["dimensions"] = dims
            result["extraction_method"] = "sdmx_csv_explicit_dimensions"
            evidence.append(result)
    return {"status": "verified" if evidence else "no_comparable_series",
            "evidence": evidence[:30], "total_dimension_groups": len(groups)}


def acquire_publication_attachments(page_url, max_links=10):
    """Fetch a bounded landing page and same-host attachments, returning auditable summaries."""
    from scripts.pulse_evidence import fetch_bounded, extract_bytes
    data, mime, final = fetch_bounded(page_url)
    if "html" not in mime.lower():
        return {"page_url": final, "attachments": [], "status": "not_html"}
    links = discover_attachments(data, final, max_links=max_links)
    reports = []
    for link in links:
        try:
            raw, ct, resolved = fetch_bounded(link)
            report = extract_bytes(raw, resolved, ct, filename=urlparse(resolved).path)
            reports.append({"url": resolved, "status": report["status"],
                            "sha256": report["source_sha256"],
                            "evidence": report["evidence"][:5]})
        except Exception as exc:
            reports.append({"url": link, "status": "extraction_failed",
                            "error": type(exc).__name__})
    return {"page_url": final, "attachments": reports, "status": "processed"}


def _revision_text(metadata):
    """Collect only explicit revision metadata, never guess methodological continuity."""
    if not isinstance(metadata, dict):
        return ""
    keys = ("revision", "revisions", "methodology", "methodological_notes",
            "break_in_series", "notes", "comment", "OBS_STATUS")
    return " ".join(str(metadata.get(k, "")) for k in keys)


def _parse_indexed_sdmx_json(doc, source_url, revision_metadata):
    """Decode common SDMX-JSON dataSets[].series using explicit structure metadata."""
    structure = doc.get("structure") or {}
    dimensions = structure.get("dimensions") or {}
    series_dims = dimensions.get("series") or []
    observation_dims = dimensions.get("observation") or []
    if len(observation_dims) != 1 or observation_dims[0].get("id") not in ("TIME_PERIOD", "TIME"):
        return {"status": "requires_dimension_resolution", "evidence": []}
    years = observation_dims[0].get("values") or []
    datasets = doc.get("dataSets") or []
    groups = []
    for dataset in datasets[:5]:
        for key, series in list((dataset.get("series") or {}).items())[:1000]:
            positions = key.split(":")
            if len(positions) != len(series_dims):
                continue
            fields = {}
            for dim, pos in zip(series_dims, positions):
                values = dim.get("values") or []
                try:
                    fields[dim["id"]] = str(values[int(pos)]["id"])
                except (KeyError, IndexError, ValueError, TypeError):
                    fields = {}
                    break
            if not fields:
                continue
            obs = []
            for obs_key, raw in list((series.get("observations") or {}).items())[:10000]:
                try:
                    year = str(years[int(obs_key)]["id"])
                    value = raw[0]
                except (ValueError, IndexError, KeyError, TypeError):
                    continue
                obs.append({"period": year, "value": value})
            groups.append((fields, obs))
    evidence = []
    for fields, observations in groups:
        # No default units or geography: missing mandatory dimensions => reject.
        result = compare_observations(
            observations, source_url=source_url,
            dataset=fields.get("DATAFLOW") or doc.get("dataflow") or "",
            indicator=fields.get("INDICATOR") or fields.get("MEASURE") or "",
            unit=fields.get("UNIT_MEASURE") or fields.get("UNIT") or "",
            territory=fields.get("REF_AREA") or fields.get("GEO") or "",
            method_id=fields.get("METHODOLOGY") or fields.get("METHODOLOGY_ID") or "",
            revision_notes=_revision_text(revision_metadata))
        if result["status"] == "verified":
            result["extraction_method"] = "sdmx_json_indexed_resolved_dimensions"
            evidence.append(result)
    return {"status": "verified" if evidence else "no_comparable_series",
            "evidence": evidence[:30]}


def parse_sdmx_json(content, source_url, revision_metadata=None):
    """SDMX-JSON 2.0 flat observations only; reject unknown/multidimensional encodings.

    Full SDMX-JSON time-series decoding requires dimension index resolution and
    should not be guessed from observation indices.
    """
    doc = json.loads(content)
    if not isinstance(doc, dict):
        return {"status": "unsupported_schema", "evidence": []}
    # SDMX-JSON 2.0 messages commonly use dataSets/structure; never infer
    # dimensions from indexed observation identifiers.
    if "dataSets" in doc or "structure" in doc:
        return _parse_indexed_sdmx_json(doc, source_url, revision_metadata)
    if doc.get("format") != "pulse_sdmx_flat_v1":
        return {"status": "unsupported_schema", "evidence": []}
    rows = doc.get("observations", [])
    if not isinstance(rows, list):
        return {"status": "unsupported_schema", "evidence": []}
    groups = {}
    for item in rows[:10000]:
        if not isinstance(item, dict):
            continue
        dims = tuple(sorted((key, str(item.get(key, ""))) for key in
            ("dataset", "indicator", "unit", "territory", "method_id")))
        groups.setdefault(dims, []).append(item)
    evidence = []
    for dims, observations in groups.items():
        d = dict(dims)
        result = compare_observations(
            observations, source_url=source_url, dataset=d["dataset"],
            indicator=d["indicator"], unit=d["unit"],
            territory=d["territory"], method_id=d["method_id"],
            revision_notes=_revision_text(revision_metadata) +
                " " + " ".join(_revision_text(o) for o in observations))
        if result["status"] == "verified":
            result["extraction_method"] = "sdmx_flat_json_explicit_dimensions"
            evidence.append(result)
    return {"status": "verified" if evidence else "no_comparable_series",
            "evidence": evidence[:30]}


def parse_sdmx_xml(content, source_url, revision_metadata=None):
    """SDMX-ML generic observation: conservative explicit attribute adapter."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(content)
    groups = {}
    for series in root.iter():
        if series.tag.rsplit("}", 1)[-1] != "Series":
            continue
        dimensions = {}
        for node in series.iter():
            if node.tag.rsplit("}", 1)[-1] != "Value":
                continue
            key, value = node.get("id"), node.get("value")
            if key and value and key not in dimensions:
                dimensions[key] = value
        observations = []
        for obs in series.iter():
            if obs.tag.rsplit("}", 1)[-1] != "Obs":
                continue
            period, value = None, None
            for child in obs.iter():
                local = child.tag.rsplit("}", 1)[-1]
                if local == "ObsDimension":
                    period = child.get("value")
                elif local == "ObsValue":
                    value = child.get("value")
            if period is not None and value is not None:
                observations.append({"period": period, "value": value})
        if not observations:
            continue
        key = tuple(sorted(dimensions.items()))
        groups.setdefault(key, []).extend(observations)
    evidence = []
    for key, observations in groups.items():
        dims = dict(key)
        result = compare_observations(
            observations, source_url=source_url,
            dataset=dims.get("DATAFLOW", ""),
            indicator=dims.get("INDICATOR", ""),
            unit=dims.get("UNIT_MEASURE", ""),
            territory=dims.get("REF_AREA", ""),
            method_id=dims.get("METHODOLOGY", ""),
            revision_notes=_revision_text(revision_metadata))
        if result["status"] == "verified":
            result["extraction_method"] = "sdmx_xml_explicit_series_dimensions"
            evidence.append(result)
    return {"status": "verified" if evidence else "no_comparable_series",
            "evidence": evidence[:30]}


def load_revision_metadata(content, filename=""):
    """Read a separate companion JSON methodological bulletin; unknown => no assertion."""
    try:
        data = json.loads(content)
    except (ValueError, UnicodeDecodeError, TypeError):
        return {"status": "unreadable_revision_metadata", "notes": ""}
    if not isinstance(data, dict):
        return {"status": "unsupported_revision_metadata", "notes": ""}
    notes = _revision_text(data)
    if any(flag in notes.lower() for flag in REVISIONS):
        return {"status": "methodological_break", "notes": notes}
    return {"status": "metadata_read", "notes": notes}
