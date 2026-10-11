#!/usr/bin/env python3
"""ISTAT PULSE: local, allowlisted Ollama job runner. Never executes remote commands.

Python standard library only. Does NOT self-update, pull code, publish content,
modify the Android app, open listening ports or store authentication tokens.
The remote JSON file can choose only an existing, fixed editorial operation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPO = "pierfido89/ISTAT-PULSE-DATA"
REMOTE_JOB_URL = (
    "https://raw.githubusercontent.com/"
    "pierfido89/ISTAT-PULSE-DATA/"
    "feat/pulse-editorial-ai-1.0/automation/editorial_job.json"
)
SOURCE = ROOT / "workbench" / "edizione_editoriale_3_5.json"
WRITER = ROOT / "scripts" / "pulse_editorial_local_writer.py"
OUTBOX = ROOT / "workbench" / "local-automation-outbox"
ALLOWED_KEYS = {"version", "job_id", "task", "start", "limit", "enabled"}
JOB_ID_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?\Z")


def parse_job(data: bytes) -> dict:
    if len(data) > 4096:
        raise ValueError("Il job remoto supera 4096 byte")
    def no_duplicates(pairs):
        d = {}
        for key, value in pairs:
            if key in d:
                raise ValueError("Chiave JSON duplicata: " + key)
            d[key] = value
        return d
    job = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    if not isinstance(job, dict) or set(job) != ALLOWED_KEYS:
        raise ValueError("Schema job non autorizzato")
    if type(job["version"]) is not int or job["version"] != 1:
        raise ValueError("Versione job non consentita")
    if not isinstance(job["job_id"], str) or not JOB_ID_PATTERN.fullmatch(job["job_id"]):
        raise ValueError("Identificativo job non valido")
    if job["task"] != "rewrite_verified_editorial_drafts":
        raise ValueError("Operazione non consentita")
    if type(job["enabled"]) is not bool:
        raise ValueError("enabled deve essere true o false")
    if type(job["start"]) is not int or type(job["limit"]) is not int:
        raise ValueError("start e limit devono essere interi")
    if not (0 <= job["start"] <= 5 and 1 <= job["limit"] <= 2
            and job["start"] + job["limit"] <= 6):
        raise ValueError("Intervallo articoli non autorizzato")
    return job


def get_job(manifest_file: Path | None) -> dict:
    if manifest_file:
        return parse_job(manifest_file.read_bytes())
    req = Request(
        REMOTE_JOB_URL,
        headers={"User-Agent": "IstatPulseLocalAgent/0.1", "Cache-Control": "no-cache"},
    )
    with urlopen(req, timeout=15) as response:
        return parse_job(response.read(4097))


def check_repo() -> None:
    if not WRITER.is_file() or not SOURCE.is_file():
        raise ValueError(
            "Mancano script o workbench locale: controllare il checkout, senza "
            "eseguire git pull automaticamente"
        )
    origin = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=15,
    ).stdout.strip().lower().rstrip("/")
    allowed = {
        "https://github.com/pierfido89/istat-pulse-data.git",
        "https://github.com/pierfido89/istat-pulse-data",
        "git@github.com:pierfido89/istat-pulse-data.git",
        "ssh://git@github.com/pierfido89/istat-pulse-data.git",
    }
    if origin not in allowed:
        raise ValueError("Repository remoto diverso da quello autorizzato")


def validate_input(job: dict) -> list[str]:
    doc = json.loads(SOURCE.read_text(encoding="utf-8"))
    drafts = doc.get("drafts")
    if not isinstance(drafts, list) or len(drafts) < job["start"] + job["limit"]:
        raise ValueError("Workbench editoriale non valido/incompleto")
    chosen = drafts[job["start"]:job["start"] + job["limit"]]
    for draft in chosen:
        if (not isinstance(draft, dict)
                or draft.get("publication_status") != "draft_only"
                or (draft.get("quality") or {}).get("status") != "review_required"):
            raise ValueError("Articolo non verificato: esecuzione bloccata")
    return [str(x.get("domain", "sconosciuto")) for x in chosen]


def run_one(job: dict) -> dict:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    result_path = OUTBOX / (job["job_id"] + ".json")
    report_path = OUTBOX / (job["job_id"] + ".report.json")
    if result_path.exists() or report_path.exists():
        raise ValueError("Job gia elaborato o presente: usare un nuovo job_id")
    command = [
        sys.executable, str(WRITER),
        "--input", str(SOURCE),
        "--output", str(result_path),
        "--start", str(job["start"]),
        "--limit", str(job["limit"]),
    ]
    started = datetime.now(timezone.utc).isoformat()
    status, error = "failed", None
    try:
        proc = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=900,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError("Writer fallito (codice " + str(proc.returncode)
                               + "): " + proc.stderr[-1000:])
        data = json.loads(result_path.read_text(encoding="utf-8"))
        rows = data.get("rewrite_results")
        if (data.get("published") is not False
                or data.get("cannot_promote_without_human_check") is not True
                or not isinstance(rows, list) or len(rows) != job["limit"]):
            raise ValueError("Il risultato non rispetta la quarantena editoriale")
        for row in rows:
            if (row.get("publication_status") != "not_publishable_model_text"
                    or (row.get("model_copy_assessment") or {}).get("human_review_required") is not True):
                raise ValueError("Bozza non correttamente in quarantena")
        status = "needs_human_review"
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        error = str(exc)[-1200:]
        # Leave draft file local for investigation, never upload automatically.
    report = {
        "job_id": job["job_id"],
        "task": job["task"],
        "status": status,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "model_expected": "qwen3.5:9b",
        "start": job["start"],
        "limit": job["limit"],
        "result_sha256": (
            hashlib.sha256(result_path.read_bytes()).hexdigest()
            if result_path.is_file() else None
        ),
        "error": error,
        "published": False,
        "human_review_required": True,
        "remote_upload_enabled": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="ISTAT PULSE local safe agent")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Check job + source locally, do not invoke Ollama")
    mode.add_argument("--once", action="store_true",
                      help="Execute at most one enabled verified job")
    parser.add_argument("--manifest-file", type=Path,
                        help="Offline test override; default reads GitHub")
    args = parser.parse_args()
    try:
        job = get_job(args.manifest_file)
        check_repo()
        domains = validate_input(job)
        if args.dry_run:
            print(json.dumps({
                "ready": True, "enabled": job["enabled"], "job_id": job["job_id"],
                "domains": domains, "dry_run": True, "ollama_invoked": False,
                "automatic_code_updates": False, "remote_upload_enabled": False,
            }, ensure_ascii=False, indent=2))
            return 0
        if not job["enabled"]:
            print("Job disabilitato: nessuna esecuzione.")
            return 0
        report = run_one(job)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "needs_human_review" else 2
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            json.JSONDecodeError) as exc:
        print("AGENTE BLOCCATO: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
