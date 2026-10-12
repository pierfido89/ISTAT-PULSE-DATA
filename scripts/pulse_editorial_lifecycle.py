#!/usr/bin/env python3
"""PULSE editorial lifecycle v1: offline, auditable, fail-closed.

No network or publication. Maintain an append-only hash-chained event history
inside one atomically replaced ledger. Export immutable archive snapshots,
a withdrawal/rectification index and an atomically replaceable local pointer.

Deployment and Android cache invalidation are separate integrations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from scripts.pulse_editorial_archive_v2 import paginate
from scripts.pulse_editorial_publication_gate import validate_approved_feed

SCHEMA = "pulse-editorial-lifecycle-ledger-v1"
PUBLIC_SCHEMA = "pulse-editorial-lifecycle-pointer-v1"
ARTICLE_ID = re.compile(r"[A-Z0-9][A-Z0-9-]{4,70}\Z")
AUTOMATED_ACTORS = {"chatgpt", "qwen", "ai", "automatico", "bot"}


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def human_label(value, field):
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 120:
        raise ValueError(field + ": identificativo umano obbligatorio")
    if value.strip().casefold() in AUTOMATED_ACTORS:
        raise ValueError(field + ": etichetta automatica non ammessa")
    return value.strip()


def reason_text(value):
    if not isinstance(value, str) or len(value.strip()) < 12 or len(value) > 2000:
        raise ValueError("Motivazione obbligatoria (12-2000 caratteri)")
    return value.strip()


def _utc(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timezone missing")
        return dt.astimezone(timezone.utc)
    except (TypeError, AttributeError, ValueError) as exc:
        raise ValueError("Timestamp UTC invalido") from exc


@contextmanager
def file_lock(path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("Ledger occupato: lock esistente, intervento manuale necessario") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("pid=" + str(os.getpid()) + "\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pulse-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        if os.name == "posix":
            dirfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_json(path, obj):
    atomic_bytes(path, json.dumps(obj, ensure_ascii=False, indent=2,
                                  sort_keys=True).encode("utf-8") + b"\n")


def empty_store():
    return {"schema_version": SCHEMA, "generation": 0, "articles": {}, "events": []}


def _projection(state):
    return {"generation": state["generation"], "articles": state["articles"]}


def verify(state):
    if (not isinstance(state, dict) or state.get("schema_version") != SCHEMA
            or type(state.get("generation")) is not int
            or state["generation"] < 0
            or not isinstance(state.get("articles"), dict)
            or not isinstance(state.get("events"), list)):
        raise ValueError("Ledger schema invalido")
    if state["generation"] != len(state["events"]):
        raise ValueError("Generazione diversa dal numero eventi")
    prev = "0" * 64
    for seq, event in enumerate(state["events"], 1):
        if (event.get("seq") != seq or event.get("previous_hash") != prev
                or event.get("hash") != digest({k:v for k,v in event.items()
                                                if k != "hash"})):
            raise ValueError("Catena degli eventi danneggiata al passo " + str(seq))
        prev = event["hash"]
    if state["events"]:
        if state["events"][-1].get("projection_sha256") != digest(_projection(state)):
            raise ValueError("Proiezione modificata senza evento audit")
    elif state["articles"]:
        raise ValueError("Dati senza eventi")
    for key, rec in state["articles"].items():
        if (not ARTICLE_ID.fullmatch(key) or rec.get("id") != key
                or rec.get("status") not in ("active", "withdrawn")):
            raise ValueError("Identificativo o stato articolo invalido")
        versions = rec.get("revisions")
        if not isinstance(versions, list) or not versions:
            raise ValueError("Cronologia versioni assente")
        if [v.get("version") for v in versions] != list(range(1, len(versions)+1)):
            raise ValueError("Versioni non monotone")
        for revision in versions:
            content = revision.get("content")
            if not isinstance(content, dict) or content.get("id") != key:
                raise ValueError("Snapshot articolo non valido")
            if digest(content) != revision.get("content_sha256"):
                raise ValueError("Snapshot immutabile alterato")
            seq = revision.get("created_event_seq")
            if type(seq) is not int or not 1 <= seq <= len(state["events"]):
                raise ValueError("Snapshot privo di evento")
            origin_event = state["events"][seq-1]
            if origin_event.get("article_id") != key or origin_event.get("revision") != revision["version"]:
                raise ValueError("Snapshot non legato all'evento originale")
        current = rec.get("current_version")
        if type(current) is not int or not 1 <= current <= len(versions):
            raise ValueError("Puntatore alla versione corrente invalido")
        unsafe = rec.get("unsafe_versions")
        if not isinstance(unsafe, list) or any(
                type(v) is not int or v < 1 or v > len(versions) for v in unsafe
        ) or len(set(unsafe)) != len(unsafe):
            raise ValueError("Elenco versioni non sicure invalido")
        if rec["status"] == "active" and current in unsafe:
            raise ValueError("Versione segnalata non sicura ancora pubblicabile")
        if rec["status"] == "withdrawn" and not isinstance(rec.get("withdrawal"), dict):
            raise ValueError("Ritiro privo di tombstone")
    return {"valid": True, "generation": state["generation"],
            "article_count": len(state["articles"]),
            "event_count": len(state["events"]), "last_event_hash": prev}


def read_store(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    verify(obj)
    return obj


def init_store(path):
    path = Path(path)
    with file_lock(path):
        if path.exists():
            raise FileExistsError("Ledger gia' esistente: non azzerare lo storico")
        atomic_json(path, empty_store())
    return {"created": str(path), "generation": 0, "published": False}


def _approved_article(article):
    if not isinstance(article, dict) or not isinstance(article.get("id"), str):
        raise ValueError("Articolo non valido")
    validate_approved_feed({"schema_version": "pulse-editorial-approved-v1",
                            "channel": "approved_editorial_only", "articles": [article]})
    if not ARTICLE_ID.fullmatch(article["id"]):
        raise ValueError("ID articolo non valido")
    _utc(article["approved_at"])
    return deepcopy(article)


def _append(path, expected_generation, mutator):
    path = Path(path)
    with file_lock(path):
        state = read_store(path)
        if expected_generation is not None and state["generation"] != expected_generation:
            raise RuntimeError("Generazione obsoleta: operazione rifiutata")
        state = deepcopy(state)
        event = mutator(state)
        if not isinstance(event, dict):
            raise ValueError("Evento non valido")
        state["generation"] += 1
        event["seq"] = state["generation"]
        event["timestamp_utc"] = event.get("timestamp_utc") or stamp()
        event["previous_hash"] = (
            state["events"][-1]["hash"] if state["events"] else "0" * 64)
        event["projection_sha256"] = digest(_projection(state))
        event["hash"] = digest(event)
        state["events"].append(event)
        verify(state)
        atomic_json(path, state)
        return {"generation": state["generation"], "operation": event["operation"],
                "article_id": event["article_id"], "revision": event["revision"],
                "event_hash": event["hash"], "published": False}


def _new_revision(article, version, event_seq, kind, at, note, restored_from=None):
    return {"version": version, "content": deepcopy(article),
            "content_sha256": digest(article), "kind": kind,
            "created_at_utc": at, "created_event_seq": event_seq,
            "reason": note, "restored_from_version": restored_from}


def register(path, article, actor, reason, expected_generation=None):
    content = _approved_article(article)
    actor, reason = human_label(actor, "operatore"), reason_text(reason)
    def modify(state):
        key = content["id"]
        if key in state["articles"]:
            raise ValueError("ID esistente: usare rettifica con nuova versione")
        at = stamp()
        rev = _new_revision(content, 1, state["generation"] + 1, "publish", at, reason)
        state["articles"][key] = {
            "id": key, "status": "active", "first_published_at_utc": at,
            "current_version": 1, "revisions": [rev], "unsafe_versions": [],
            "withdrawal": None,
        }
        return {"operation": "register", "article_id": key, "revision": 1,
                "actor": actor, "reason": reason, "timestamp_utc": at,
                "content_sha256": rev["content_sha256"]}
    return _append(path, expected_generation, modify)


def rectify(path, article, actor, reason, expected_generation=None, *, invalidate_previous=False):
    content = _approved_article(article)
    actor, reason = human_label(actor, "operatore"), reason_text(reason)
    def modify(state):
        key = content["id"]
        rec = state["articles"].get(key)
        if not rec or rec["status"] != "active":
            raise ValueError("Rettifica consentita solo su un articolo attivo")
        before = rec["current_version"]
        if digest(content) == rec["revisions"][before-1]["content_sha256"]:
            raise ValueError("Nessuna modifica: rettifica identica")
        at = stamp()
        ver = len(rec["revisions"]) + 1
        rev = _new_revision(content, ver, state["generation"] + 1, "rectify", at, reason)
        rec["revisions"].append(rev)
        rec["current_version"] = ver
        # Flag a factual/statistical error explicitly. Mere wording revisions
        # do not automatically mean every preceding revision was unsafe.
        if invalidate_previous:
            rec["unsafe_versions"].append(before)
        return {"operation": "rectify", "article_id": key, "revision": ver,
                "previous_version": before, "actor": actor, "reason": reason,
                "timestamp_utc": at, "content_sha256": rev["content_sha256"]}
    return _append(path, expected_generation, modify)


def withdraw(path, article_id, actor, reason, *, confirmed=False,
             expected_generation=None):
    if not confirmed:
        raise ValueError("Ritiro d'emergenza richiede conferma esplicita")
    actor, reason = human_label(actor, "operatore"), reason_text(reason)
    def modify(state):
        rec = state["articles"].get(article_id)
        if not rec or rec["status"] != "active":
            raise ValueError("Articolo assente o già ritirato")
        at = stamp()
        version = rec["current_version"]
        rec["status"] = "withdrawn"
        rec["unsafe_versions"].append(version)
        rec["withdrawal"] = {"timestamp_utc": at, "reason": reason,
                             "by": actor, "event_seq": state["generation"] + 1}
        return {"operation": "withdraw", "article_id": article_id,
                "revision": version, "actor": actor, "reason": reason,
                "timestamp_utc": at, "emergency": True}
    return _append(path, expected_generation, modify)


def rollback(path, article_id, target_version, actor, reviewed_by, reason,
             *, confirmed=False, expected_generation=None):
    if not confirmed:
        raise ValueError("Ripristino richiede conferma umana esplicita")
    actor = human_label(actor, "operatore")
    reviewed_by = human_label(reviewed_by, "revisore")
    reason = reason_text(reason)
    def modify(state):
        rec = state["articles"].get(article_id)
        if not rec or type(target_version) is not int or not (
                1 <= target_version < len(rec["revisions"])):
            raise ValueError("Versione precedente inesistente")
        if target_version in rec["unsafe_versions"]:
            raise ValueError("Versione segnalata non sicura: ripristino vietato")
        source = rec["revisions"][target_version-1]
        content = _approved_article(source["content"])
        at = stamp()
        previous = rec["current_version"]
        new_version = len(rec["revisions"]) + 1
        rev = _new_revision(content, new_version, state["generation"] + 1,
                            "rollback", at, reason, restored_from=target_version)
        rec["revisions"].append(rev)
        if rec["status"] == "active":
            rec["unsafe_versions"].append(previous)
        rec["status"] = "active"
        rec["withdrawal"] = None
        rec["current_version"] = new_version
        return {"operation": "rollback", "article_id": article_id,
                "revision": new_version, "previous_version": previous,
                "restored_from_version": target_version, "actor": actor,
                "reviewed_by": reviewed_by, "reason": reason,
                "timestamp_utc": at, "content_sha256": rev["content_sha256"]}
    return _append(path, expected_generation, modify)


def lifecycle_view(state):
    entries = []
    for key, rec in sorted(state["articles"].items()):
        entries.append({
            "id": key, "status": rec["status"],
            "current_version": rec["current_version"],
            "first_published_at_utc": rec["first_published_at_utc"],
            "withdrawal": rec["withdrawal"],
            "unsafe_versions": sorted(rec["unsafe_versions"]),
            "versions": [{"version": x["version"], "sha256": x["content_sha256"],
                          "kind": x["kind"], "created_at_utc": x["created_at_utc"],
                          "restored_from_version": x["restored_from_version"]}
                         for x in rec["revisions"]],
        })
    return {"schema_version": "pulse-editorial-lifecycle-v1",
            "generation": state["generation"], "articles": entries}


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2,
                      sort_keys=True).encode("utf-8") + b"\n"


def export_snapshot(ledger_path, output_dir):
    """Offline only: immutable generation directory, atomic local pointer last."""
    ledger_path = Path(ledger_path).resolve()
    output_dir = Path(output_dir).resolve()
    if (output_dir == ledger_path.parent or output_dir == ledger_path
            or output_dir in ledger_path.parents
            or ledger_path in output_dir.parents):
        raise ValueError("Directory di esportazione non isolata dal ledger")
    state = read_store(ledger_path)
    versions = []
    for rec in state["articles"].values():
        if rec["status"] != "active":
            continue
        item = deepcopy(rec["revisions"][rec["current_version"]-1]["content"])
        item["first_published_at_utc"] = rec["first_published_at_utc"]
        item["version"] = rec["current_version"]
        versions.append(item)
    archive, pages = paginate(versions)
    lifecycle = lifecycle_view(state)
    generation = state["generation"]
    relative_dir = "snapshots/generation_" + str(generation).zfill(10)
    snapshots_root = output_dir / "snapshots"
    snapshot = output_dir / relative_dir
    index = {
        "schema_version": "pulse-editorial-lifecycle-export-v1",
        "generation": generation,
        "archive": archive,
        "lifecycle": {"url_path": "lifecycle.json",
                      "sha256": hashlib.sha256(_json_bytes(lifecycle)).hexdigest()},
        "consumer_contract": {
            "on_withdrawn": "remove cached full body, show withdrawn tombstone",
            "on_rectification": "replace cached version by higher revision",
            "never_display_cached_data_before_lifecycle_check": True,
            "must_revalidate_pointer_online": True,
        },
        "published_to_network": False,
    }
    snapshots_root.mkdir(parents=True, exist_ok=True)
    with file_lock(output_dir / "current.json"):
        pointer_path = output_dir / "current.json"
        if pointer_path.exists():
            previous = json.loads(pointer_path.read_text(encoding="utf-8"))
            if previous.get("schema_version") != PUBLIC_SCHEMA:
                raise ValueError("Unknown existing pointer: do not overwrite")
            if previous.get("generation", -1) > generation:
                raise ValueError("Cannot rewind current generation")
        if snapshot.exists():
            saved = (snapshot / "index.json").read_bytes()
            if saved != _json_bytes(index):
                raise ValueError("Immutable generation collision")
        else:
            with tempfile.TemporaryDirectory(dir=snapshots_root, prefix=".pulse-gen-") as td:
                work = Path(td)
                for name, page in pages.items():
                    target = work / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(_json_bytes(page))
                (work / "lifecycle.json").write_bytes(_json_bytes(lifecycle))
                (work / "index.json").write_bytes(_json_bytes(index))
                # Validate every written page against v2's canonical page digest.
                for entry in archive["pages"]:
                    loaded = json.loads((work / entry["url_path"]).read_text(encoding="utf-8"))
                    expected = hashlib.sha256(
                        (json.dumps(loaded, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n").encode("utf-8")).hexdigest()
                    if expected != entry["sha256"]:
                        raise ValueError("Page digest mismatch")
                # Recreate a path owned by this process to atomically install
                # this immutable local snapshot directory.
                os.replace(work, snapshot)
        pointer = {
            "schema_version": PUBLIC_SCHEMA,
            "generation": generation,
            "snapshot_index_url_path": relative_dir + "/index.json",
            "sha256": hashlib.sha256(_json_bytes(index)).hexdigest(),
            "last_event_hash": state["events"][-1]["hash"] if state["events"] else "0"*64,
            "http_required_cache_control": "no-store",
            "network_deployed": False,
        }
        atomic_json(pointer_path, pointer)
    return {"exported": True, "network_deployed": False,
            "generation": generation, "articles": len(versions),
            "withdrawn": sum(v["status"] == "withdrawn" for v in lifecycle["articles"]),
            "pointer": str(output_dir / "current.json")}


def main(argv=None):
    p = argparse.ArgumentParser(description="PULSE editorial lifecycle: OFFLINE, no network/publish")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("init", "verify", "register", "rectify", "withdraw", "rollback", "export"):
        s = sub.add_parser(cmd)
        s.add_argument("--ledger", type=Path, required=True)
        if cmd in ("register", "rectify"):
            s.add_argument("--article", type=Path, required=True,
                           help="Single previously human-approved JSON article")
        if cmd in ("register", "rectify", "withdraw", "rollback"):
            s.add_argument("--actor", required=True)
            s.add_argument("--reason", required=True)
            s.add_argument("--expected-generation", type=int)
        if cmd == "rectify":
            s.add_argument("--invalidate-previous", action="store_true",
                           help="Mark old revision unsafe for future rollback")
        if cmd in ("withdraw", "rollback"):
            s.add_argument("--id", required=True)
        if cmd == "withdraw":
            s.add_argument("--confirm-withdraw", action="store_true")
        if cmd == "rollback":
            s.add_argument("--target-version", type=int, required=True)
            s.add_argument("--reviewed-by", required=True)
            s.add_argument("--confirm-safe-target", action="store_true")
        if cmd == "export":
            s.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args(argv)
    if args.cmd == "init":
        result = init_store(args.ledger)
    elif args.cmd == "verify":
        result = verify(read_store(args.ledger))
    elif args.cmd in ("register", "rectify"):
        obj = json.loads(args.article.read_text(encoding="utf-8"))
        if args.cmd == "rectify":
            result = rectify(args.ledger, obj, args.actor, args.reason,
                             args.expected_generation,
                             invalidate_previous=args.invalidate_previous)
        else:
            result = register(args.ledger, obj, args.actor, args.reason,
                              args.expected_generation)
    elif args.cmd == "withdraw":
        result = withdraw(args.ledger, args.id, args.actor, args.reason,
                          confirmed=args.confirm_withdraw,
                          expected_generation=args.expected_generation)
    elif args.cmd == "rollback":
        result = rollback(args.ledger, args.id, args.target_version,
                          args.actor, args.reviewed_by, args.reason,
                          confirmed=args.confirm_safe_target,
                          expected_generation=args.expected_generation)
    else:
        result = export_snapshot(args.ledger, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
