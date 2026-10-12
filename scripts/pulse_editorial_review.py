#!/usr/bin/env python3
"""Re-evaluate an existing PULSE paired pilot, no Ollama and no cloud API.

The original official workbench is the sole authority for all numbers.
A previously generated draft provides only the optional AI context to
audit. Malformed or altered evidence is never silently trusted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

try:
    from scripts.pulse_editorial_ai import _read_input, MAX_INPUT_BYTES
    from scripts.pulse_editorial_pairs import (
        paired_candidates, paired_audit, FORBIDDEN_OUTPUTS,
    )
except ModuleNotFoundError:
    from pulse_editorial_ai import _read_input, MAX_INPUT_BYTES
    from pulse_editorial_pairs import (
        paired_candidates, paired_audit, FORBIDDEN_OUTPUTS,
    )

FACT_KEYS = (
    "indicator", "unit", "segment", "period", "value", "change_pct",
    "source_url", "source_sha256", "source_location", "proof_type",
)


def recheck(original_workbench: Path, previous_draft: Path) -> dict:
    all_pairs = {
        pair["id"]: pair
        for pair in paired_candidates(_read_input(original_workbench))
    }
    if not previous_draft.is_file() or previous_draft.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Old draft file missing or too large")
    report = json.loads(previous_draft.read_text(encoding="utf-8"))
    if (not isinstance(report, dict)
            or report.get("schema_version") != "pulse-editorial-paired-2.0"
            or report.get("mode") != "local_drafts_only"
            or not isinstance(report.get("drafts"), list)):
        raise ValueError("Expected local PULSE Editorial 2.0 paired draft JSON")
    output = []
    seen: set[str] = set()
    for old in report["drafts"]:
        if not isinstance(old, dict):
            raise ValueError("Invalid draft record")
        ident = old.get("id")
        if ident not in all_pairs or ident in seen:
            raise ValueError("Unknown or repeated paired candidate ID")
        seen.add(ident)
        pair = all_pairs[ident]
        supplied = old.get("evidence")
        if not isinstance(supplied, list) or len(supplied) != 2:
            raise ValueError("Previous draft does not contain two source facts")
        for actual, purported in zip(pair["evidence"], supplied):
            if not isinstance(purported, dict) or any(
                actual.get(key) != purported.get(key) for key in FACT_KEYS
            ):
                raise ValueError("Original draft evidence does not match official workbench")
        context = old.get("model_proposed_context")
        proposal = {"context": context} if isinstance(context, str) else {}
        fresh = paired_audit(pair, proposal)
        fresh["generator"]["model"] = str(report.get("model") or "unknown")
        fresh["review_of_previous_draft"] = ident
        fresh["review_method"] = "offline_official_workbench_reverification"
        output.append(fresh)
    return {
        "schema_version": "pulse-editorial-paired-review-2.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_review_no_ollama_or_cloud",
        "reviewed_count": len(output),
        "drafts": output,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Recheck previous Qwen paired draft against original ISTAT workbench")
    p.add_argument("--input", type=Path, required=True,
                   help="Existing official tourism workbench JSON")
    p.add_argument("--previous", type=Path, required=True,
                   help="Previous PULSE Editorial 2.0 output")
    p.add_argument("--output", type=Path, required=True,
                   help="New isolated reviewed JSON; never production")
    args = p.parse_args(argv)
    if (args.output.name.lower() in FORBIDDEN_OUTPUTS
            or args.output.resolve() in (args.input.resolve(),
                                         args.previous.resolve())):
        p.error("Refusing to overwrite source files or production artifacts")
    try:
        reviewed = recheck(args.input, args.previous)
    except (OSError, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        print("Revisione impossibile: " + str(exc), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "file": str(args.output), "reviewed": len(reviewed["drafts"]),
        "safe_cores": sum(
            d["quality"]["safe_core_status"] == "review_required"
            for d in reviewed["drafts"]
        ),
        "accepted_ai_contexts": sum(
            d["quality"]["model_context_status"] == "accepted"
            for d in reviewed["drafts"]
        ),
        "rejected_ai_contexts": sum(
            d["quality"]["model_context_status"] == "rejected"
            for d in reviewed["drafts"]
        ),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
