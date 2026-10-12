#!/usr/bin/env python3
"""Controlled GitHub-backed PULSE editorial *remote* snapshot preparation.

The GitHub Actions workflow is the authenticated publishing entry point.
This module never logs in or pushes itself. It validates private approved-ledger
exports, pinned PR reviews, history monotonicity, page hashes and tombstones,
then stages ONE complete atomic Git commit in a checkout of the remote branch.
Raw GitHub CDN cache latency and offline phones remain outside server control.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


REMOTE_SUBDIR = Path("data/editorial/lifecycle")
VERSION_RE = re.compile(r"snapshots/generation_(\d{10})/index[.]json\Z")
NAME_RE = re.compile(r"[A-Z0-9][A-Z0-9-]{4,70}\Z")


def h(data):
    return hashlib.sha256(data).hexdigest()


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def page_checksum(body):
    return h((json.dumps(body, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")) + "\n").encode("utf-8"))


def inspect_package(root):
    root = Path(root).resolve()
    pointer_path = root / "current.json"
    pointer = json_file(pointer_path)
    if pointer.get("schema_version") != "pulse-editorial-lifecycle-pointer-v1":
        raise ValueError("Wrong release pointer schema")
    try:
        generation = pointer["generation"]
        path = pointer["snapshot_index_url_path"]
        match = VERSION_RE.fullmatch(path)
        if match is None or type(generation) is not int or generation != int(match.group(1)):
            raise ValueError("Snapshot generation/path mismatch")
        idx_path = root / path
        idx_raw = idx_path.read_bytes()
        if h(idx_raw) != pointer["sha256"]:
            raise ValueError("Snapshot manifest digest mismatch")
        index = json.loads(idx_raw)
        if index.get("schema_version") != "pulse-editorial-lifecycle-export-v1" or (
            index.get("generation") != generation):
            raise ValueError("Unexpected export index")
        lc_ref = index["lifecycle"]
        if lc_ref.get("url_path") != "lifecycle.json":
            raise ValueError("External lifecycle path forbidden")
        lc_path = idx_path.parent / "lifecycle.json"
        lc_bytes = lc_path.read_bytes()
        if h(lc_bytes) != lc_ref["sha256"]:
            raise ValueError("Lifecycle manifest digest mismatch")
        lifecycle = json.loads(lc_bytes)
        if lifecycle.get("schema_version") != "pulse-editorial-lifecycle-v1" or (
            lifecycle.get("generation") != generation):
            raise ValueError("Mismatched lifecycle generation")
        rows = lifecycle["articles"]
        ids = set()
        active = {}
        withdrawn = set()
        if not isinstance(rows, list):
            raise ValueError("Invalid lifecycle")
        for row in rows:
            key = row["id"]
            if not isinstance(key, str) or not NAME_RE.fullmatch(key) or key in ids:
                raise ValueError("Malformed/duplicate lifecycle article")
            ids.add(key)
            if row["status"] == "active":
                if type(row.get("current_version")) is not int:
                    raise ValueError("Missing revision")
                active[key] = row["current_version"]
            elif row["status"] == "withdrawn":
                if not isinstance(row.get("withdrawal"), dict):
                    raise ValueError("Missing withdrawn tombstone")
                withdrawn.add(key)
            else:
                raise ValueError("Unknown article state")
        archive = index["archive"]
        if archive.get("article_count") != len(active):
            raise ValueError("Archive count not equal active lifecycle count")
        seen = set()
        for page in archive["pages"]:
            name = page["url_path"]
            if not re.fullmatch(r"pages/page_[0-9]{5}[.]json", name):
                raise ValueError("Unsafe page path")
            raw = (idx_path.parent / name).read_bytes()
            content = json.loads(raw)
            if page_checksum(content) != page["sha256"]:
                raise ValueError("Page checksum mismatch")
            articles = content.get("articles")
            if not isinstance(articles, list) or page["count"] != len(articles):
                raise ValueError("Incorrect page count")
            for article in articles:
                key = article.get("id")
                if key in seen or key not in active:
                    raise ValueError("Withdrawn, duplicated or unapproved article in page")
                if article.get("version") != active[key] or (
                    article.get("publication_status") != "approved_for_pulse" or
                    article.get("human_approved") is not True):
                    raise ValueError("Incorrect approved lifecycle revision")
                seen.add(key)
        if seen != set(active):
            raise ValueError("Live articles missing from released pages")
        return {"generation": generation, "pointer": pointer, "index": index,
                "articles": len(active), "withdrawn": len(withdrawn),
                "snapshot_path": path[: -len("/index.json")],
                "snapshot_dir": idx_path.parent,
                "snapshot_sha256": h(idx_raw)}
    except (KeyError, IndexError, TypeError, OSError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid/incomplete release snapshot") from exc


def verified_github_review(pull, reviews, actor, allowed_operators, allowed_reviewers):
    """Workflow MUST supply responses fetched from authenticated GitHub REST API."""
    if not isinstance(actor, str) or actor not in allowed_operators:
        raise PermissionError("Authenticated GitHub operator not allowed")
    head_sha = pull.get("head", {}).get("sha")
    if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise PermissionError("PR must have a verifiable commit SHA")
    if pull.get("state") != "open" or pull.get("draft") is True:
        raise PermissionError("Release PR must be open, non-draft and current")
    if not isinstance(reviews, list):
        raise PermissionError("GitHub reviews missing")
    by_user = {}
    for review in reviews:
        reviewer = review.get("user", {}).get("login")
        if reviewer not in allowed_reviewers or reviewer == actor:
            continue
        if review.get("commit_id") != head_sha:
            continue
        at = review.get("submitted_at", "")
        if reviewer not in by_user or at > by_user[reviewer].get("submitted_at", ""):
            by_user[reviewer] = review
    approved = [login for login, rev in by_user.items() if rev.get("state") == "APPROVED"]
    if not approved:
        raise PermissionError("Missing current-SHA independent GitHub approval")
    return {"operator": actor, "reviewer": sorted(approved)[0],
            "reviewed_head_sha": head_sha, "github_pr": pull.get("number")}


def stage_release(source_dir, git_checkout, authorization, *, base=REMOTE_SUBDIR):
    """Stage file changes in a local git worktree, never push/merge on its own."""
    if set(authorization) != {"operator", "reviewer", "reviewed_head_sha", "github_pr"}:
        raise PermissionError("Verified GitHub approval contract required")
    source = inspect_package(source_dir)
    checkout = Path(git_checkout).resolve()
    if not (checkout / ".git").exists():
        raise ValueError("Target must be a checked-out Git repository")
    remote = checkout / base
    remote.mkdir(parents=True, exist_ok=True)
    remote_pointer = remote / "current.json"
    current_generation = -1
    if remote_pointer.exists():
        old = inspect_package(remote)
        current_generation = old["generation"]
        if source["generation"] < current_generation:
            raise ValueError("Release generation rollback is forbidden")
        if source["generation"] == current_generation:
            if source["snapshot_sha256"] != old["snapshot_sha256"]:
                raise ValueError("Same generation with different content")
            return {"status": "already_released", "generation": current_generation,
                    "published": False}
    relative = Path(source["snapshot_path"])
    destination = remote / relative
    if destination.exists():
        raise ValueError("Immutable snapshot already exists with unexpected generation")
    # The source was validated before copying. Stage into a temporary private
    # directory, revalidate after copying, then atomically install snapshot.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pulse-release-", dir=destination.parent) as td:
        temporary = Path(td) / "snapshot"
        shutil.copytree(source["snapshot_dir"], temporary)
        check_root = Path(td) / "validation"
        (check_root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temporary, check_root / relative)
        (check_root / "current.json").write_bytes(
            (Path(source_dir) / "current.json").read_bytes())
        checked = inspect_package(check_root)
        if checked["snapshot_sha256"] != source["snapshot_sha256"]:
            raise ValueError("Copied snapshot integrity mismatch")
        os.replace(temporary, destination)
    pointer = deepcopy(source["pointer"])
    pointer["network_deployed"] = True
    pointer["authenticated_operator"] = authorization["operator"]
    pointer["independent_github_reviewer"] = authorization["reviewer"]
    pointer["reviewed_head_sha"] = authorization["reviewed_head_sha"]
    pointer["reviewed_pr_number"] = authorization["github_pr"]
    pointer["staged_at_utc"] = datetime.now(timezone.utc).isoformat()
    # Atomic Git commit is the publication transaction; current.json is added
    # last and becomes visible remotely together with all snapshot files.
    fd, filename = tempfile.mkstemp(prefix=".pulse-current-", dir=remote)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write((json.dumps(pointer, ensure_ascii=False, indent=2,
                                     sort_keys=True) + "\n").encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(filename, remote_pointer)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)
    return {"status": "staged_for_reviewed_git_push", "generation": source["generation"],
            "articles": source["articles"], "withdrawn": source["withdrawn"],
            "published": False, "snapshot": str(destination)}


def main(argv=None):
    p = argparse.ArgumentParser(description="Stage reviewed remote PULSE lifecycle release (no push)")
    p.add_argument("--source-export", type=Path, required=True)
    p.add_argument("--target-checkout", type=Path, required=True)
    p.add_argument("--github-pr-json", type=Path, required=True)
    p.add_argument("--github-reviews-json", type=Path, required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--allowed-operators", required=True)
    p.add_argument("--allowed-reviewers", required=True)
    args = p.parse_args(argv)
    authorization = verified_github_review(
        json_file(args.github_pr_json), json_file(args.github_reviews_json),
        args.actor, args.allowed_operators.split(","), args.allowed_reviewers.split(","))
    result = stage_release(args.source_export, args.target_checkout, authorization)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
