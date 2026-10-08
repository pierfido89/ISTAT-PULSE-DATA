#!/usr/bin/env python3
"""Materialize all automatically verified structured feed endpoints.

Consumes data/feed_expansion_status.json produced by probe_feed_expansion.py.
Only official, non-editorial structured resources are persisted. This is the
generic second stage shared by all 39 candidate institutions.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "data" / "feed_expansion_status.json"
OUT_DIR = ROOT / "data" / "expanded_verified"
MANIFEST = ROOT / "data" / "expanded_verified_manifest.json"

UA = "ISTAT-PULSE-feed-materializer/1.0 (+https://github.com/pierfido89/ISTAT-PULSE)"
TIMEOUT = 60
MAX_BYTES = 80 * 1024 * 1024

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "*/*"})

REJECT_TYPES = ("application/pdf", "application/rss+xml", "application/atom+xml")
SUPPORTED_TYPES = (
    "application/json", "application/geo+json", "text/csv",
    "text/tab-separated-values", "application/xml", "text/xml",
    "application/rdf+xml", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip", "application/octet-stream", "text/plain",
)


def slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "source"


def extension(url: str, content_type: str, raw: bytes) -> str:
    path = urlparse(url).path.lower()
    for ext in (".xlsx", ".xls", ".csv", ".tsv", ".json", ".geojson", ".xml", ".rdf", ".zip"):
        if path.endswith(ext):
            return ext
    if raw.startswith(b"PK"):
        return ".zip"
    if "json" in content_type:
        return ".json"
    if "csv" in content_type:
        return ".csv"
    if "rdf" in content_type:
        return ".rdf"
    if "xml" in content_type:
        return ".xml"
    return ".dat"


def validate(url: str, content_type: str, raw: bytes) -> dict:
    low = content_type.lower()
    if any(low.startswith(x) for x in REJECT_TYPES):
        raise RuntimeError(f"editorial/document content type: {content_type}")
    if len(raw) < 16:
        raise RuntimeError("payload too small")
    if len(raw) > MAX_BYTES:
        raise RuntimeError(f"payload exceeds {MAX_BYTES} bytes")

    info: dict = {}
    text = raw[:12000].decode("utf-8", errors="replace").lstrip()

    if raw.startswith(b"PK"):
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = [x for x in archive.namelist() if x and not x.endswith("/")]
            if not names:
                raise RuntimeError("empty ZIP/XLSX archive")
            info["archive_files"] = names[:100]
            info["archive_file_count"] = len(names)
            if "xl/workbook.xml" in names:
                info["detected_format"] = "xlsx"
                info["worksheet_count"] = len([
                    x for x in names
                    if x.startswith("xl/worksheets/") and x.endswith(".xml")
                ])
            else:
                info["detected_format"] = "zip"
        return info

    if "json" in low or text.startswith(("{", "[")):
        payload = json.loads(raw.decode("utf-8"))
        info["detected_format"] = "json"
        if isinstance(payload, dict):
            info["json_keys"] = list(payload.keys())[:30]
            result = payload.get("result")
            if isinstance(result, list):
                info["result_count"] = len(result)
        elif isinstance(payload, list):
            info["result_count"] = len(payload)
        return info

    if "xml" in low or "rdf" in low or text.startswith("<"):
        lower_text = text.lower()
        if "exceptionreport" in lower_text or "serviceexception" in lower_text:
            raise RuntimeError("XML service exception returned instead of dataset")
        if not text.startswith("<"):
            raise RuntimeError("invalid XML/RDF payload")
        info["detected_format"] = "rdf" if "rdf" in low else "xml"
        info["sample"] = text[:500]
        return info

    lines = [line for line in text.splitlines() if line.strip()]
    if "csv" in low or path_like_csv(url):
        if len(lines) < 2:
            raise RuntimeError("CSV payload has fewer than 2 non-empty lines")
        if lines[0].lstrip().startswith("<"):
            raise RuntimeError("HTML/XML returned instead of CSV")
        info["detected_format"] = "csv"
        info["sample_lines"] = [line[:1500] for line in lines[:4]]
        return info

    if any(low.startswith(x) for x in SUPPORTED_TYPES):
        info["detected_format"] = "structured_unknown"
        info["sample"] = text[:500]
        return info

    raise RuntimeError(f"unsupported content type: {content_type}")


def path_like_csv(url: str) -> bool:
    return urlparse(url).path.lower().endswith((".csv", ".tsv"))


def fetch_resource(resource: dict) -> tuple[bytes, requests.Response]:
    url = resource.get("final_url") or resource.get("url")
    response = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
    response.raise_for_status()
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=1024 * 256):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES:
            raise RuntimeError(f"resource larger than {MAX_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks), response


def main() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    failures = []
    for source in status.get("sources", []):
        if source.get("status") != "structured_endpoint_verified":
            continue
        institution = source["institution"]
        resources = source.get("verified_resources", [])
        success = None
        source_errors = []

        for resource in resources:
            url = resource.get("final_url") or resource.get("url")
            if not url:
                continue
            try:
                raw, response = fetch_resource(resource)
                content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                meta = validate(response.url, content_type, raw)
                ext = extension(response.url, content_type, raw)
                target = OUT_DIR / f"{slug(institution)}{ext}"
                target.write_bytes(raw)
                success = {
                    "institution": institution,
                    "url": response.url,
                    "content_type": content_type,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "snapshot": str(target.relative_to(ROOT)),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    **meta,
                }
                print(f"OK {institution}: {response.url} ({len(raw):,} bytes)")
                break
            except Exception as exc:
                source_errors.append({
                    "url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        if success:
            results.append(success)
        else:
            failures.append({
                "institution": institution,
                "resources_tested": len(resources),
                "errors": source_errors,
            })
            print(f"FAIL {institution}: no verified resource materialized")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verified_sources_seen": len(results) + len(failures),
        "materialized_sources": len(results),
        "failed_sources": len(failures),
        "results": results,
        "failures": failures,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not results:
        raise RuntimeError("No verified feed could be materialized")


if __name__ == "__main__":
    main()
