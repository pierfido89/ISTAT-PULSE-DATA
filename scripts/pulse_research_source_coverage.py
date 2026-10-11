#!/usr/bin/env python3
"""PULSE Research expansion inventory.

Maps the existing catalogue (feed/connected/archive/error) to *separate*
research capabilities. Catalog "feed" NEVER means a PDF was fact checked.
No network access, no LLM, no publishing, no Android changes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "pulse-research-coverage-v1"


def is_official_https(url: object) -> bool:
    if not isinstance(url, str) or len(url) > 800:
        return False
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    return bool(p.scheme == "https" and p.hostname and
                not p.username and not p.password and
                p.hostname not in ("localhost", "127.0.0.1"))


def make_coverage(catalog: dict, packet: dict) -> dict:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("sources"), list):
        raise ValueError("Official source catalog missing")
    if (not isinstance(packet, dict)
            or packet.get("schema_version") != "pulse-research-to-chatgpt-v1"
            or packet.get("publication_allowed") is not False):
        raise ValueError("Unverified research evidence packet")
    stories = packet.get("stories")
    if not isinstance(stories, list) or not stories:
        raise ValueError("No verified research stories")
    documents = {}
    for story in stories:
        if not isinstance(story, dict):
            raise ValueError("Malformed research story")
        url = story.get("source_url")
        sha = story.get("source_sha256")
        if (not is_official_https(url) or not isinstance(sha, str) or
                len(sha) != 64 or any(x not in "0123456789abcdef" for x in sha)):
            raise ValueError("Verified document must have URL and SHA256")
        facts = story.get("facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError("Source must include verified facts")
        if (url, sha) not in documents:
            documents[(url, sha)] = {
                "source_url": url, "source_sha256": sha,
                "domain": story.get("domain"),
                "story_count": 0, "fact_count": 0,
                "numeric_validation": "source_specific_acceptance_passed",
            }
        documents[(url, sha)]["story_count"] += 1
        documents[(url, sha)]["fact_count"] += len(facts)
    names = set()
    rows = []
    for raw in catalog["sources"]:
        if not isinstance(raw, dict) or not raw.get("official"):
            continue
        name = raw.get("name")
        url = raw.get("url")
        if not isinstance(name, str) or not name.strip() or not is_official_https(url):
            raise ValueError("A listed official source has no valid name or HTTPS URL")
        if name in names:
            raise ValueError("Duplicated source name: " + name)
        names.add(name)
        integration = raw.get("integration_status") or "unknown"
        rows.append({
            "source_name": name, "source_url": url,
            "host": urlsplit(url).hostname.lower(),
            "catalogue_status": integration,
            "research_intake": "candidate_only_unverified",
            "numeric_research_verified": False,
            "editorial_publication_allowed": False,
            "reason": "Catalogue may supply discovery, but not a PDF-specific audited numeric extractor",
        })
    rows.sort(key=lambda x: x["source_name"].casefold())
    if not rows:
        raise ValueError("No official source entries")
    status_count = dict(sorted(Counter(row["catalogue_status"] for row in rows).items()))
    return {
        "schema_version": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "official_source_catalogue_plus_separately_verified_primary_pdfs",
        "catalogue_official_sources": len(rows),
        "catalogue_status_distribution": status_count,
        "verified_primary_pdf_count": len(documents),
        "verified_story_count": sum(d["story_count"] for d in documents.values()),
        "verified_fact_count": sum(d["fact_count"] for d in documents.values()),
        "sources": rows,
        "verified_primary_documents": sorted(documents.values(), key=lambda x: x["source_url"]),
        "research_intake_rules": {
            "catalogue_feed_is_not_numeric_research_verification": True,
            "new_official_pdfs_enter_as_read_only": True,
            "structured_values_require_source_specific_audited_adapter": True,
            "unverified_text_never_enters_fact_checker_as_numerical_evidence": True,
            "human_publication_approval_required": True,
        },
        "auto_publish": False,
        "public_approved_article_count": 0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.output.resolve() in {args.catalog.resolve(), args.packet.resolve()}:
        ap.error("Do not overwrite source inputs")
    result = make_coverage(
        json.loads(args.catalog.read_text(encoding="utf-8")),
        json.loads(args.packet.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "official_catalogue": result["catalogue_official_sources"],
        "verified_pdfs": result["verified_primary_pdf_count"],
        "fact_ids": result["verified_fact_count"],
        "additional_sources_numeric_verified": 0,
        "automatic_publications": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
