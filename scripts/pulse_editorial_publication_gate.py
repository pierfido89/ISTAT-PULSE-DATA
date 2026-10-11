#!/usr/bin/env python3
"""PULSE editorial publication gate, strictly OFFLINE and human-triggered.

This converts an already-human-approved private ChatGPT JSON export into a
PUBLIC-FEED CANDIDATE at a caller-chosen local path. It NEVER contacts GitHub,
loads OpenAI API keys, publishes, or changes the Android project.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

SCHEMA = "pulse-editorial-approved-v1"
DRAFT_SCHEMA = "pulse-chatgpt-direct-editorial-v1"
APPROVAL_SCHEMA = "pulse-editorial-human-approval-v1"
PERIOD = re.compile(r"20\d\d-(?:0[1-9]|1[0-2])\Z")
ID = re.compile(r"[A-Z0-9][A-Z0-9-]{4,70}\Z")


def check_https(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 600:
        return False
    u = urlsplit(value)
    return u.scheme == "https" and bool(u.hostname) and not u.username and not u.password


def validate_approved_feed(feed: dict) -> None:
    if feed.get("schema_version") != SCHEMA or feed.get("channel") != "approved_editorial_only":
        raise ValueError("Schema/canale diverso da approved-v1")
    articles = feed.get("articles")
    if not isinstance(articles, list) or len(articles) > 40:
        raise ValueError("Numero di articoli non valido")
    seen = set()
    for item in articles:
        if not isinstance(item, dict):
            raise ValueError("Voce non oggetto")
        article_id = item.get("id")
        if not isinstance(article_id, str) or not ID.fullmatch(article_id) or article_id in seen:
            raise ValueError("ID non valido o duplicato")
        seen.add(article_id)
        if (item.get("publication_status") != "approved_for_pulse"
                or item.get("human_approved") is not True
                or item.get("approved_by") in ("", None, "ChatGPT", "Qwen")
                or not isinstance(item.get("approved_by"), str)
                or not isinstance(item.get("approved_at"), str)):
            raise ValueError("Approvazione umana assente")
        if (not isinstance(item.get("headline"), str)
                or not 20 <= len(item["headline"]) <= 190
                or not isinstance(item.get("topic"), str)
                or not 2 <= len(item["topic"]) <= 45):
            raise ValueError("Titolo/tema non valido")
        paragraphs = item.get("paragraphs")
        if (not isinstance(paragraphs, list) or not 3 <= len(paragraphs) <= 5
                or not all(isinstance(p, str) and 70 <= len(p) <= 1300 for p in paragraphs)):
            raise ValueError("Testo incompleto")
        if not check_https(item.get("primary_source_url")):
            raise ValueError("Fonte primaria HTTPS mancante")
        if not PERIOD.fullmatch(str(item.get("reference_period") or "")):
            raise ValueError("Periodo nel formato YYYY-MM richiesto")
        evidence = item.get("evidence")
        if (not isinstance(evidence, list) or not 2 <= len(evidence) <= 30
                or not all(isinstance(e, dict) and isinstance(e.get("claim"), str)
                           and len(e["claim"]) >= 8
                           and isinstance(e.get("location"), str)
                           and len(e["location"]) >= 10 for e in evidence)):
            raise ValueError("Evidenze insufficienti")
        if item.get("producer") not in ("ChatGPT", "PULSE editorial"):
            raise ValueError("Origine non prevista")


def prepare(draft_bytes: bytes, approval: dict, previous: dict) -> dict:
    draft = json.loads(draft_bytes)
    if (draft.get("schema_version") != DRAFT_SCHEMA or draft.get("published") is not False
            or draft.get("auto_publish") is not False
            or draft.get("human_fact_check_required") is not True):
        raise ValueError("Bozza non conforme al contratto di quarantena")
    if approval.get("schema_version") != APPROVAL_SCHEMA:
        raise ValueError("Schema approvazione errato")
    if approval.get("draft_sha256") != hashlib.sha256(draft_bytes).hexdigest():
        raise ValueError("Hash approvazione non corrispondente alla bozza esatta")
    approver = approval.get("approved_by")
    if (not isinstance(approver, str) or len(approver.strip()) < 3
            or approver.strip().casefold() in ("chatgpt", "qwen", "ai", "automatico")):
        raise ValueError("Serve revisore umano identificato")
    approved_at = approval.get("approved_at")
    if not isinstance(approved_at, str):
        raise ValueError("Timestamp approvazione mancante")
    try:
        stamp = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Senza fuso orario")
    except ValueError as exc:
        raise ValueError("Data approvazione non valida") from exc
    selection = approval.get("approved_articles")
    if not isinstance(selection, list) or not selection:
        raise ValueError("Nessun articolo esplicitamente autorizzato")
    drafts = {item["id"]: item for item in draft["articles"]}
    result = dict(previous)
    validate_approved_feed(result)
    known = {a["id"] for a in result["articles"]}
    for spec in selection:
        if not isinstance(spec, dict):
            raise ValueError("Selezione non valida")
        article_id = spec.get("id")
        if article_id not in drafts or article_id in known:
            raise ValueError("Articolo non nella bozza o gia presente")
        item = drafts[article_id]
        if item.get("publication_status") != "not_publishable_without_human_review":
            raise ValueError("Testo originario non in quarantena")
        if spec.get("reviewed_claims_and_source") is not True:
            raise ValueError("Conferma umana del controllo dati mancante")
        reference = spec.get("reference_period")
        topic = spec.get("topic")
        final = {
            "id": article_id,
            "publication_status": "approved_for_pulse",
            "human_approved": True,
            "approved_by": approver.strip(),
            "approved_at": approved_at,
            "producer": "ChatGPT",
            "topic": topic,
            "reference_period": reference,
            "headline": item["headline"],
            "paragraphs": item["paragraphs"],
            "primary_source_url": item["primary_source_url"],
            "evidence": item["evidence"],
        }
        # An approval with editorial changes must first create a fresh draft,
        # because approving a different draft SHA would break the audit trail.
        result["articles"].append(final)
        known.add(article_id)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    validate_approved_feed(result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate candidate feed after *manual human* approval")
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--current-feed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-reviewed", action="store_true", required=True)
    opts = parser.parse_args(argv)
    if not opts.confirm_reviewed:
        parser.error("Approvazione umana esplicita obbligatoria")
    protected = {p.resolve() for p in (opts.draft, opts.approval, opts.current_feed)}
    if opts.output.resolve() in protected:
        parser.error("Non sovrascrivere bozze, approvazioni o feed esistente")
    result = prepare(
        opts.draft.read_bytes(),
        json.loads(opts.approval.read_text(encoding="utf-8")),
        json.loads(opts.current_feed.read_text(encoding="utf-8")),
    )
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    opts.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidate":str(opts.output),"articles":len(result["articles"]),
                      "uploaded":False,"published":False},ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
