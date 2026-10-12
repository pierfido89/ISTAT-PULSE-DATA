#!/usr/bin/env python3
"""Single-owner emergency withdrawal: no reviewer, no artificial sign-off.

Operates on an already checked-out PRIVATE ledger and a local public preview
checkout. Never performs network requests or git pushes. The trusted GitHub
Actions workflow validates github.actor and confirmation, commits private ledger
first, and finally publishes the immutable preview Git generation.

Crash recovery: if an article was already withdrawn, rebuilding the current
snapshot is idempotent. No stale edition is reintroduced.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.pulse_editorial_lifecycle import read_store, withdraw, export_snapshot
from scripts.pulse_editorial_remote_release import (
    stage_release, verified_emergency_owner, inspect_package,
)


def prepare_emergency(ledger, output_dir, remote_checkout, article_id, reason,
                      actor, *, confirmed=False):
    approval = verified_emergency_owner(actor, article_id, reason,
                                        confirmed=confirmed)
    store = read_store(ledger)
    row = store["articles"].get(article_id)
    if row is None:
        raise ValueError("Articolo non presente nel registro privato; nessuna pubblicazione")
    if row["status"] == "active":
        result = withdraw(ledger, article_id, actor, reason, confirmed=True,
                          expected_generation=store["generation"])
        new_withdrawal = True
    elif row["status"] == "withdrawn":
        result = {"operation": "withdraw_already_recorded",
                  "generation": store["generation"]}
        new_withdrawal = False
    else:
        raise ValueError("Stato articolo sconosciuto")
    export_snapshot(ledger, output_dir)
    verified = inspect_package(output_dir)
    if verified["generation"] != read_store(ledger)["generation"]:
        raise ValueError("Local ledger/export generations do not match")
    remote = stage_release(output_dir, remote_checkout, approval)
    return {"article_id": article_id, "owner": actor, "new_withdrawal": new_withdrawal,
            "generation": verified["generation"], "public_active_count": verified["articles"],
            "public_withdrawn_count": verified["withdrawn"],
            "remote_stage": remote["status"], "published_to_network": False,
            "private_audit_event": result.get("event_hash")}


def main(argv=None):
    p = argparse.ArgumentParser(description="Owner-only emergency editorial preview staging")
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--remote-checkout", type=Path, required=True)
    p.add_argument("--article-id", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--confirm-emergency", action="store_true")
    args = p.parse_args(argv)
    print(json.dumps(prepare_emergency(
        args.ledger, args.output_dir, args.remote_checkout, args.article_id,
        args.reason, args.actor, confirmed=args.confirm_emergency),
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
