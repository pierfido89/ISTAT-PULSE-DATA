"""Reviewed remote release: SHA, tombstones, immutable remote pointer and roles."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.pulse_editorial_lifecycle import init_store, register, withdraw, export_snapshot
from scripts.pulse_editorial_remote_release import (
    inspect_package, verified_github_review, stage_release, REMOTE_SUBDIR
)
from tests.test_pulse_editorial_lifecycle import approved, ACTOR, REASON

SHA = "1" * 40
PR = {"number": 12, "state": "open", "draft": False, "head": {"sha": SHA}}
REV = [{"user": {"login": "statistical-reviewer"}, "commit_id": SHA,
        "submitted_at": "2026-10-12T10:00:00Z", "state": "APPROVED"}]


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.ledger = self.root / "private" / "ledger.json"
        self.exports = self.root / "private_exports"
        self.checkout = self.root / "remote_checkout"
        self.checkout.mkdir()
        (self.checkout / ".git").mkdir()
        init_store(self.ledger)

    def auth(self):
        return verified_github_review(PR, REV, "editor-owner",
            ["editor-owner"], ["statistical-reviewer"])

    def test_auth_requires_real_other_user_current_sha_and_non_draft_pr(self):
        self.assertEqual(self.auth()["reviewer"], "statistical-reviewer")
        with self.assertRaises(PermissionError):
            verified_github_review(PR, REV, "unknown", ["editor-owner"], ["statistical-reviewer"])
        with self.assertRaises(PermissionError):
            verified_github_review(PR, REV, "editor-owner", ["editor-owner"], ["editor-owner"])
        bad = copy.deepcopy(REV)
        bad[0]["commit_id"] = "2" * 40
        with self.assertRaises(PermissionError):
            verified_github_review(PR, bad, "editor-owner", ["editor-owner"],
                                   ["statistical-reviewer"])
        bad = copy.deepcopy(PR)
        bad["draft"] = True
        with self.assertRaises(PermissionError):
            verified_github_review(bad, REV, "editor-owner", ["editor-owner"],
                                   ["statistical-reviewer"])

    def test_stage_live_and_withdrawal_to_new_remote_generation(self):
        register(self.ledger, approved(), ACTOR, REASON)
        export_snapshot(self.ledger, self.exports)
        self.assertEqual(inspect_package(self.exports)["articles"], 1)
        staged = stage_release(self.exports, self.checkout, self.auth())
        self.assertEqual(staged["generation"], 1)
        remote = self.checkout / REMOTE_SUBDIR
        published = json.loads((remote / "current.json").read_text())
        self.assertTrue(published["network_deployed"])
        self.assertEqual(published["authenticated_operator"], "editor-owner")
        self.assertEqual(published["independent_github_reviewer"], "statistical-reviewer")
        self.assertEqual(stage_release(self.exports, self.checkout, self.auth())["status"],
                         "already_released")
        withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON, confirmed=True)
        export_snapshot(self.ledger, self.exports)
        staged2 = stage_release(self.exports, self.checkout, self.auth())
        self.assertEqual(staged2["generation"], 2)
        self.assertEqual(staged2["articles"], 0)
        self.assertEqual(staged2["withdrawn"], 1)
        remote_now = inspect_package(remote)
        self.assertEqual(remote_now["articles"], 0)
        self.assertEqual(remote_now["withdrawn"], 1)
        self.assertEqual(remote_now["generation"], 2)
        self.assertTrue((remote / "snapshots/generation_0000000001/index.json").exists())

    def test_remote_version_rewind_never_allowed(self):
        register(self.ledger, approved(), ACTOR, REASON)
        export_snapshot(self.ledger, self.exports)
        stage_release(self.exports, self.checkout, self.auth())
        withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON, confirmed=True)
        export_snapshot(self.ledger, self.exports)
        stage_release(self.exports, self.checkout, self.auth())
        older = self.root / "old-export"
        older.mkdir()
        import shutil
        shutil.copytree(self.checkout / REMOTE_SUBDIR / "snapshots/generation_0000000001",
                        older / "snapshots/generation_0000000001")
        first = json.loads((self.checkout / REMOTE_SUBDIR / "snapshots/generation_0000000001/index.json").read_text())
        from scripts.pulse_editorial_remote_release import h
        index_raw = (older / "snapshots/generation_0000000001/index.json").read_bytes()
        pointer = {"schema_version": "pulse-editorial-lifecycle-pointer-v1",
                   "generation": 1, "snapshot_index_url_path":
                   "snapshots/generation_0000000001/index.json", "sha256": h(index_raw)}
        (older / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "rollback"):
            stage_release(older, self.checkout, self.auth())

    def test_corrupted_source_manifest_prevents_remote_write(self):
        register(self.ledger, approved(), ACTOR, REASON)
        export_snapshot(self.ledger, self.exports)
        page = self.exports / "snapshots/generation_0000000001/pages/page_00001.json"
        page.write_text('{"forged":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            stage_release(self.exports, self.checkout, self.auth())
        self.assertFalse((self.checkout / REMOTE_SUBDIR / "current.json").exists())

    def test_incomplete_copied_immutable_page_cannot_publish(self):
        register(self.ledger, approved(), ACTOR, REASON)
        export_snapshot(self.ledger, self.exports)
        pointer = json.loads((self.exports / "current.json").read_text())
        pointer["sha256"] = "0" * 64
        (self.exports / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            stage_release(self.exports, self.checkout, self.auth())

    def test_same_generation_different_content_is_rejected(self):
        register(self.ledger, approved(), ACTOR, REASON)
        export_snapshot(self.ledger, self.exports)
        stage_release(self.exports, self.checkout, self.auth())
        snap = self.exports / "snapshots/generation_0000000001/index.json"
        snap.write_text('{"broken":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            stage_release(self.exports, self.checkout, self.auth())


if __name__ == "__main__":
    unittest.main()
