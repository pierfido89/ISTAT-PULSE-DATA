#!/usr/bin/env python3
"""PULSE editorial operations: bounded costs, durable priority queue, 3h NEW badge.

Deterministic offline primitives. NO model calls, credentials, spending, commits,
Android builds, auto-approval, or publication. Production must supply its own
audited state store and explicit enablement after tests.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MODEL_PRICE_USD_PER_M = {
    # Official short-context Standard, verified 2026-10-11.
    "gpt-6-luna": {"input": Decimal("0.10"), "output": Decimal("0.50")},
    "gpt-6.1-sol": {"input": Decimal("2.00"), "output": Decimal("10.00")},
}
BLOCKED = frozenset(("QUARANTINED", "PUBLISHED", "AUTO_APPROVED", "AWAITING_HUMAN_REVIEW"))
PENDING = frozenset(("DISCOVERED", "ACQUIRED", "VERIFIED_FACTS", "RETRY"))
API_PRODUCTION_ENABLED = False
PUBLISHING_ENABLED = False


def utc_time(text: str) -> datetime:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Missing time")
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Naive time forbidden; must be UTC/offset aware")
    return t.astimezone(timezone.utc)


def source_identity(url: str, source_sha256: str) -> str:
    """Keep each revised PDF distinct; strip URL fragments and tracker query."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Primary source must be HTTPS and independently accessible")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        raise ValueError("PDF/data SHA-256 missing")
    if any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("Malformed SHA-256")
    normalized = urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", ""))
    return hashlib.sha256((normalized + "\n" + source_sha256).encode("utf-8")).hexdigest()


def build_queue(records: list[dict], now_utc: str, max_items: int = 2) -> list[dict]:
    """Return a small deduplicated batch; current releases precede archive."""
    now = utc_time(now_utc)
    if not isinstance(records, list) or not isinstance(max_items, int) or not 1 <= max_items <= 100:
        raise ValueError("Invalid queue input")
    ready = []
    seen = set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Bad queue entry")
        status = row.get("status")
        if status in BLOCKED:
            continue
        if status not in PENDING:
            raise ValueError("Unexpected state: " + str(status))
        if row.get("evidence_verified") is not True:
            # A news article with numbers not checked on the official PDF never enters redaction.
            continue
        uid = source_identity(row["primary_source_url"], row["source_sha256"])
        if uid in seen:
            continue
        seen.add(uid)
        if row.get("next_attempt_at"):
            if utc_time(row["next_attempt_at"]) > now:
                continue
        released = utc_time(row["official_released_at"])
        historical = row.get("archive_backfill") is True or released < now - timedelta(days=14)
        ready.append({
            "source_id": uid,
            "primary_source_url": row["primary_source_url"],
            "source_sha256": row["source_sha256"],
            "official_released_at": released.isoformat(),
            "queue_lane": "ARCHIVE" if historical else "CURRENT",
            "priority": 1 if historical else 0,
            "status": status,
            "publication_allowed": False,
        })
    ready.sort(key=lambda x:(x["priority"],x["official_released_at"],x["source_id"]),
               reverse=False)
    # For equal priority, newest official releases first.
    ready.sort(key=lambda x:x["official_released_at"],reverse=True)
    ready.sort(key=lambda x:x["priority"])
    return ready[:max_items]


def show_new_badge(first_published_at: str, now_utc: str, *, archive_backfill: bool = False) -> bool:
    """Badge is about genuinely new releases, not recycled historical uploads."""
    if archive_backfill:
        return False
    try:
        start, now = utc_time(first_published_at), utc_time(now_utc)
    except (ValueError, TypeError):
        return False
    return start <= now < start + timedelta(minutes=180)


def price_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    if model not in MODEL_PRICE_USD_PER_M:
        raise ValueError("Unpriced model")
    if (not isinstance(input_tokens,int) or not isinstance(output_tokens,int)
            or min(input_tokens,output_tokens) < 0):
        raise ValueError("Invalid token counts")
    p=MODEL_PRICE_USD_PER_M[model]
    return ((Decimal(input_tokens)*p["input"] + Decimal(output_tokens)*p["output"])
            / Decimal(1_000_000))


def estimate_articles(articles: int, *, escalation_fraction: str = "0.20",
                      retry_factor: str = "1.25", budget_usd: str = "5") -> dict:
    """Two Luna stages + optional Sol escalation, with a retry safety factor.

    Luna author: 10k input / 2k output
    Luna structured review: 12k input / 1.5k output
    Sol deep semantic: 12k input / 1.5k output, on escalation_fraction.
    All are assumptions, not quota or invoices; tool calls/PDF ingestion extra.
    """
    if not isinstance(articles,int) or articles < 0:
        raise ValueError("Invalid volume")
    fraction=Decimal(escalation_fraction)
    retry=Decimal(retry_factor)
    budget=Decimal(budget_usd)
    if not Decimal(0) <= fraction <= Decimal(1) or retry < 1 or budget < 0:
        raise ValueError("Invalid fraction/retry/budget")
    base=price_usd("gpt-6-luna",10000,2000)+price_usd("gpt-6-luna",12000,1500)
    upgrade=price_usd("gpt-6.1-sol",12000,1500)
    each=(base+upgrade*fraction)*retry
    total=each*Decimal(articles)
    affordable=int(budget//each) if each else 0
    return {
        "schema_version":"pulse-ai-estimate-v1",
        "mode":"offline_estimate_no_api_calls",
        "model_prices_as_of":"2026-10-11",
        "articles":articles,
        "assumptions":{"luna_stages":2,"sol_escalation_fraction":str(fraction),
                       "retry_factor":str(retry),
                       "pdf_and_tool_costs_excluded":True},
        "estimated_per_article_usd":str(each.quantize(Decimal("0.000001"))),
        "estimated_total_usd":str(total.quantize(Decimal("0.0001"))),
        "trial_budget_usd":str(budget),
        "approx_articles_at_trial_budget":affordable,
        "within_budget":total <= budget,
        "paid_api_enabled":API_PRODUCTION_ENABLED,
        "automatic_publication_enabled":PUBLISHING_ENABLED,
    }


def main() -> None:
    ap=argparse.ArgumentParser(description="Offline cost forecast or priority queue")
    ap.add_argument("--articles",type=int,default=300)
    ap.add_argument("--budget-usd",default="5")
    ap.add_argument("--sol-share",default="0.20")
    ap.add_argument("--retry-factor",default="1.25")
    ap.add_argument("--queue-file",type=Path)
    ap.add_argument("--now",help="Offset-aware ISO-8601, required with --queue-file")
    ap.add_argument("--limit",type=int,default=2)
    args=ap.parse_args()
    if args.queue_file:
        if not args.now:ap.error("--now mandatory with --queue-file")
        data=json.loads(args.queue_file.read_text(encoding="utf-8"))
        print(json.dumps({"publication_allowed":False,"queue":build_queue(data,args.now,args.limit)},
                         ensure_ascii=False,indent=2))
    else:
        print(json.dumps(estimate_articles(args.articles,escalation_fraction=args.sol_share,
                                          retry_factor=args.retry_factor,budget_usd=args.budget_usd),
                         ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
