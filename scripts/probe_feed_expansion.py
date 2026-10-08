#!/usr/bin/env python3
"""Batch-probe the 39 candidate permanent structured-data feeds.

This script never promotes a source to active merely because a webpage exists.
A source becomes structured_endpoint_verified only when an official-domain URL
returns a machine-readable resource (JSON/CSV/TSV/XML/RDF/SDMX/GeoJSON/XLS/XLSX/ZIP)
or an official API/catalog page exposes such a resource and that resource is reachable.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "feed_expansion_registry.json"
STATUS = ROOT / "data" / "feed_expansion_status.json"

UA = "ISTAT-PULSE-feed-probe/1.0 (+https://github.com/pierfido89/ISTAT-PULSE)"
TIMEOUT = 10
MAX_DISCOVERED = 8
MAX_VERIFY = 3

MACHINE_EXTENSIONS = (
    ".csv", ".tsv", ".json", ".geojson", ".xml", ".rdf",
    ".xls", ".xlsx", ".zip", ".parquet", ".ods",
)
MACHINE_CT = (
    "application/json",
    "application/geo+json",
    "text/csv",
    "text/tab-separated-values",
    "application/xml",
    "text/xml",
    "application/rdf+xml",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "application/octet-stream",
)
REJECT_CT = (
    "application/rss+xml",
    "application/atom+xml",
    "application/pdf",
)
DISCOVERY_WORDS = (
    "open data", "opendata", "dataset", "api", "sdmx", "csv", "xlsx",
    "xls", "json", "xml", "rdf", "download", "scarica", "dati",
)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "*/*",
})


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def allowed(url: str, domains: list[str]) -> bool:
    host = hostname(url)
    return any(
        host == domain.lower().removeprefix("www.")
        or host.endswith("." + domain.lower().removeprefix("www."))
        for domain in domains
    )


def looks_machine_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in MACHINE_EXTENSIONS) or any(
        token in path for token in ("/api/", "/api?", "/sdmx", "/rest/", "/sparql")
    )


def get(url: str, *, stream: bool = False) -> requests.Response:
    response = session.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True,
        stream=stream,
    )
    response.raise_for_status()
    return response


def verify_resource(url: str, domains: list[str]) -> dict:
    if not allowed(url, domains):
        return {"url": url, "ok": False, "reason": "outside_official_domain"}
    try:
        response = get(url, stream=True)
        final_url = response.url
        if not allowed(final_url, domains):
            return {
                "url": url,
                "final_url": final_url,
                "ok": False,
                "reason": "redirect_outside_official_domain",
            }
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        disposition = response.headers.get("content-disposition", "")
        rejected = any(content_type.startswith(ct) for ct in REJECT_CT)
        machine = (not rejected) and (
            any(content_type.startswith(ct) for ct in MACHINE_CT)
            or looks_machine_url(final_url)
            or any(ext in disposition.lower() for ext in MACHINE_EXTENSIONS)
        )
        return {
            "url": url,
            "final_url": final_url,
            "ok": bool(machine),
            "http_status": response.status_code,
            "content_type": content_type,
            "content_length": response.headers.get("content-length", ""),
            "reason": "machine_readable_data" if machine else (
                "editorial_or_document_resource" if rejected else "html_or_unknown"
            ),
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def discover_from_page(url: str, domains: list[str]) -> dict:
    if not allowed(url, domains):
        return {"url": url, "ok": False, "reason": "outside_official_domain", "links": []}
    try:
        response = get(url)
        final_url = response.url
        if not allowed(final_url, domains):
            return {
                "url": url,
                "final_url": final_url,
                "ok": False,
                "reason": "redirect_outside_official_domain",
                "links": [],
            }
        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type or "xml" in content_type or looks_machine_url(final_url):
            verified = verify_resource(final_url, domains)
            return {
                "url": url,
                "final_url": final_url,
                "ok": True,
                "reason": "entrypoint_is_machine_resource",
                "links": [verified],
            }

        soup = BeautifulSoup(response.text, "html.parser")
        ranked: list[tuple[int, str]] = []
        seen: set[str] = set()
        for tag in soup.find_all("a", href=True):
            absolute = urljoin(final_url, tag.get("href", "").strip())
            if not absolute.startswith(("http://", "https://")):
                continue
            if not allowed(absolute, domains):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            text = " ".join(tag.stripped_strings).lower()
            low = absolute.lower()
            score = 0
            if looks_machine_url(absolute):
                score += 8
            score += sum(1 for word in DISCOVERY_WORDS if word in text or word in low)
            if score:
                ranked.append((score, absolute))

        ranked.sort(key=lambda x: (-x[0], x[1]))
        candidates = [url for _, url in ranked[:MAX_DISCOVERED]]
        verified = [
            verify_resource(candidate, domains)
            for candidate in candidates[:MAX_VERIFY]
        ]
        return {
            "url": url,
            "final_url": final_url,
            "ok": True,
            "http_status": response.status_code,
            "content_type": content_type.split(";")[0],
            "reason": "official_page_scanned",
            "candidate_links": candidates,
            "verified_links": verified,
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "candidate_links": [],
            "verified_links": [],
        }


def root_candidates(domains: list[str]) -> list[str]:
    urls: list[str] = []
    common = (
        "", "/opendata", "/open-data", "/dati", "/dataset", "/datasets",
        "/api", "/statistiche", "/statistica",
    )
    for domain in domains:
        for suffix in common:
            urls.append("https://" + domain.removeprefix("www.") + suffix)
    return urls


def source_probe(source: dict) -> dict:
    institution = source["institution"]
    domains = source.get("domains", [])
    endpoints = source.get("endpoints", [])
    entrypoints = source.get("entrypoints", [])

    checks: list[dict] = []
    verified_resources: list[dict] = []

    for endpoint in endpoints:
        result = verify_resource(endpoint, domains)
        checks.append({"kind": "endpoint", **result})
        if result.get("ok"):
            verified_resources.append(result)

    pages = list(entrypoints)
    if not pages:
        pages = root_candidates(domains)

    # Keep probes bounded: permanent connector logic should be deterministic and
    # respectful of source infrastructure.
    for page in pages[:5]:
        result = discover_from_page(page, domains)
        checks.append({"kind": "discovery", **result})
        for item in result.get("links", []) + result.get("verified_links", []):
            if item.get("ok"):
                verified_resources.append(item)
        if len(verified_resources) >= 1:
            break
        time.sleep(0.12)

    dedup: dict[str, dict] = {}
    for resource in verified_resources:
        key = resource.get("final_url") or resource.get("url")
        if key:
            dedup[key] = resource
    verified_resources = list(dedup.values())

    if verified_resources:
        status = "structured_endpoint_verified"
    elif any(check.get("ok") for check in checks):
        status = "official_portal_reachable"
    else:
        status = "blocked"

    return {
        "institution": institution,
        "strategy": source.get("strategy", ""),
        "status": status,
        "domains": domains,
        "verified_resources": verified_resources,
        "checks": checks,
    }


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    sources = registry.get("sources", [])
    if len(sources) != 39:
        raise RuntimeError(f"Expected 39 feed candidates, found {len(sources)}")

    results_by_name: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(source_probe, source): source["institution"]
            for source in sources
        }
        completed = 0
        for future in as_completed(futures):
            institution = futures[future]
            completed += 1
            try:
                results_by_name[institution] = future.result()
                print(
                    f"[{completed:02d}/39] {institution}: "
                    f"{results_by_name[institution]['status']}"
                )
            except Exception as exc:
                results_by_name[institution] = {
                    "institution": institution,
                    "strategy": "",
                    "status": "blocked",
                    "domains": [],
                    "verified_resources": [],
                    "checks": [{
                        "kind": "probe_exception",
                        "ok": False,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }],
                }
                print(f"[{completed:02d}/39] {institution}: blocked ({exc})")

    # Preserve registry order so diffs remain stable and human-reviewable.
    results = [
        results_by_name[source["institution"]]
        for source in sources
    ]

    counts: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": registry.get("policy", {}),
        "candidate_count": len(results),
        "status_counts": counts,
        "sources": results,
    }
    STATUS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
