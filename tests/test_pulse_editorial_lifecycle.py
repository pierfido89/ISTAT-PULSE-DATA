"""PULSE editorial lifecycle acceptance: offline, tamper evidence, tombstones, safe rollback."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.pulse_editorial_lifecycle import (
    empty_store, init_store, read_store, register, rectify, withdraw,
    rollback, verify, export_snapshot, file_lock
)

ACTOR = "Responsabile PULSE"
REVIEWER = "Revisore editoriale"
REASON = "Revisione documentata sulla fonte ufficiale disponibile."


def approved(i="PULSE-TEST-001", headline="Titolo verificato del primo articolo",
             source="https://www.istat.it/rapporto.pdf"):
    return {
        "id": i, "publication_status": "approved_for_pulse",
        "human_approved": True, "approved_by": "Revisore umano",
        "approved_at": "2026-10-12T09:00:00+02:00",
        "producer": "ChatGPT",
        "topic": "PREZZI", "reference_period": "2026-08",
        "headline": headline,
        "paragraphs": ["Le informazioni sono state ricontrollate nel rapporto ufficiale "
                       "con periodo, definizione, metodo e territorio indicati con precisione."]
                      * 3,
        "primary_source_url": source,
        "evidence": [
            {"claim": "Controllo della prima osservazione",
             "location": "PDF ufficiale, pagina 1, prospetto 1"},
            {"claim": "Controllo della seconda osservazione",
             "location": "PDF ufficiale, pagina 2, prospetto 2"},
        ],
    }


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "secure" / "ledger.json"
        self.export = self.root / "offline_exports"
        init_store(self.ledger)

    def read(self):
        return read_store(self.ledger)

    def test_init_empty_never_reinitialize(self):
        self.assertEqual(verify(self.read())["generation"], 0)
        with self.assertRaises(FileExistsError):
            init_store(self.ledger)

    def test_publication_requires_existing_human_approval_and_retains_hash(self):
        with self.assertRaises(ValueError):
            register(self.ledger, {**approved(), "human_approved": False},
                     ACTOR, REASON)
        register(self.ledger, approved(), ACTOR, REASON)
        state = self.read()
        rec = state["articles"]["PULSE-TEST-001"]
        self.assertEqual(rec["current_version"], 1)
        self.assertEqual(len(rec["revisions"]), 1)
        self.assertTrue(verify(state)["valid"])
        with self.assertRaises(ValueError):
            register(self.ledger, approved(), ACTOR, REASON)

    def test_safe_revision_and_explicit_human_rollback_create_new_version(self):
        register(self.ledger, approved(), ACTOR, REASON)
        rectify(self.ledger, approved(headline="Titolo verificato dopo editing"),
                ACTOR, REASON)
        state = self.read()
        self.assertEqual(state["articles"]["PULSE-TEST-001"]["current_version"], 2)
        self.assertEqual(state["articles"]["PULSE-TEST-001"]["unsafe_versions"], [])
        rollback(self.ledger, "PULSE-TEST-001", 1, ACTOR, REVIEWER, REASON,
                 confirmed=True)
        rec = self.read()["articles"]["PULSE-TEST-001"]
        self.assertEqual(rec["current_version"], 3)
        self.assertEqual(rec["revisions"][-1]["restored_from_version"], 1)
        self.assertEqual(rec["revisions"][0]["content_sha256"],
                         rec["revisions"][2]["content_sha256"])
        self.assertIn(2, rec["unsafe_versions"])
        self.assertEqual(self.read()["generation"], 3)

    def test_incorrect_older_revision_cannot_rollback(self):
        register(self.ledger, approved(), ACTOR, REASON)
        rectify(self.ledger, approved(headline="Testo statistico rettificato definitivo"),
                ACTOR, REASON, invalidate_previous=True)
        rec = self.read()["articles"]["PULSE-TEST-001"]
        self.assertEqual(rec["unsafe_versions"], [1])
        with self.assertRaisesRegex(ValueError, "non sicura"):
            rollback(self.ledger, "PULSE-TEST-001", 1,
                     ACTOR, REVIEWER, REASON, confirmed=True)
        self.assertEqual(self.read()["generation"], 2)

    def test_emergency_withdraw_needs_confirmation_and_removes_live_content(self):
        register(self.ledger, approved(), ACTOR, REASON)
        with self.assertRaises(ValueError):
            withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON)
        withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON, confirmed=True)
        rec = self.read()["articles"]["PULSE-TEST-001"]
        self.assertEqual(rec["status"], "withdrawn")
        self.assertEqual(rec["unsafe_versions"], [1])
        self.assertIsNotNone(rec["withdrawal"])
        with self.assertRaises(ValueError):
            withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON, confirmed=True)
        output = export_snapshot(self.ledger, self.export)
        self.assertEqual(output["withdrawn"], 1)
        ptr = json.loads((self.export / "current.json").read_text())
        idx = json.loads((self.export / ptr["snapshot_index_url_path"]).read_text())
        self.assertEqual(idx["archive"]["article_count"], 0)
        lifecycle = json.loads((self.export / "snapshots" /
                                "generation_0000000002" / "lifecycle.json").read_text())
        self.assertEqual(lifecycle["articles"][0]["status"], "withdrawn")
        self.assertNotIn("Le informazioni sono state", json.dumps(lifecycle))
        self.assertTrue(self.read()["articles"]["PULSE-TEST-001"]["revisions"])

    def test_no_recovery_of_withdrawn_bad_revision(self):
        register(self.ledger, approved(), ACTOR, REASON)
        rectify(self.ledger, approved(headline="Nuovo articolo di dettaglio verificato"),
                ACTOR, REASON)
        withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON, confirmed=True)
        with self.assertRaises(ValueError):
            rollback(self.ledger, "PULSE-TEST-001", 2,
                     ACTOR, REVIEWER, REASON, confirmed=True)
        rollback(self.ledger, "PULSE-TEST-001", 1,
                 ACTOR, REVIEWER, REASON, confirmed=True)
        self.assertEqual(self.read()["articles"]["PULSE-TEST-001"]["status"], "active")
        self.assertEqual(self.read()["articles"]["PULSE-TEST-001"]["current_version"], 3)
        self.assertIsNone(self.read()["articles"]["PULSE-TEST-001"]["withdrawal"])

    def test_attempts_to_tamper_with_history_and_content_are_detected(self):
        register(self.ledger, approved(), ACTOR, REASON)
        state = self.read()
        bad = copy.deepcopy(state)
        bad["events"][0]["reason"] = "falso"
        with self.assertRaisesRegex(ValueError, "Catena"):
            verify(bad)
        bad = copy.deepcopy(state)
        bad["articles"]["PULSE-TEST-001"]["revisions"][0]["content"]["headline"] = "Menzogna"
        with self.assertRaises(ValueError):
            verify(bad)
        bad = copy.deepcopy(state)
        bad["articles"]["PULSE-TEST-001"]["status"] = "withdrawn"
        with self.assertRaisesRegex(ValueError, "Proiezione"):
            verify(bad)

    def test_lock_prevents_concurrent_updates_and_ledger_kept(self):
        with file_lock(self.ledger):
            with self.assertRaises(RuntimeError):
                register(self.ledger, approved(), ACTOR, REASON)
        self.assertEqual(self.read()["generation"], 0)

    def test_optimistic_concurrency_blocks_stale_actor(self):
        register(self.ledger, approved(), ACTOR, REASON, expected_generation=0)
        with self.assertRaisesRegex(RuntimeError, "obsoleta"):
            rectify(self.ledger, approved(headline="Correzione tardiva oltre la generazione"),
                    ACTOR, REASON, expected_generation=0)
        self.assertEqual(self.read()["generation"], 1)

    def test_invalid_reviewer_and_unknown_target_block(self):
        register(self.ledger, approved(), ACTOR, REASON)
        rectify(self.ledger, approved(headline="Revisione successiva verificata"),
                ACTOR, REASON)
        with self.assertRaises(ValueError):
            rollback(self.ledger, "PULSE-TEST-001", 1,
                     ACTOR, "ChatGPT", REASON, confirmed=True)
        with self.assertRaises(ValueError):
            rollback(self.ledger, "PULSE-TEST-001", 1,
                     ACTOR, REVIEWER, REASON, confirmed=False)
        with self.assertRaises(ValueError):
            rollback(self.ledger, "PULSE-TEST-001", 99,
                     ACTOR, REVIEWER, REASON, confirmed=True)

    def test_export_is_immutable_and_pointer_switches_only_forward(self):
        register(self.ledger, approved(), ACTOR, REASON)
        first = export_snapshot(self.ledger, self.export)
        p1 = json.loads((self.export / "current.json").read_text())
        self.assertEqual(first["articles"], 1)
        self.assertEqual(p1["generation"], 1)
        rectify(self.ledger, approved(headline="Titolo corretto su dati verificati"),
                ACTOR, REASON)
        export_snapshot(self.ledger, self.export)
        p2 = json.loads((self.export / "current.json").read_text())
        self.assertEqual(p2["generation"], 2)
        self.assertTrue((self.export / p1["snapshot_index_url_path"]).exists())
        self.assertTrue((self.export / p2["snapshot_index_url_path"]).exists())
        with self.assertRaises(ValueError):
            # Restoring previous file is not supported: only a NEW event is valid.
            other = self.root / "old.json"
            older = self.read()
            older["generation"] = 1
            json.dump(older, other.open("w"))
            export_snapshot(other, self.export)

    def test_export_rejects_overwrite_of_private_ledger_area(self):
        register(self.ledger, approved(), ACTOR, REASON)
        with self.assertRaises(ValueError):
            export_snapshot(self.ledger, self.ledger.parent)

    def test_many_articles_paginate_and_withdrawn_never_enter_archive(self):
        for n in range(58):
            register(self.ledger, approved(i=f"PULSE-TEST-{n:03d}"), ACTOR, REASON)
        for n in range(4):
            withdraw(self.ledger, f"PULSE-TEST-{n:03d}", ACTOR, REASON,
                     confirmed=True)
        result = export_snapshot(self.ledger, self.export)
        self.assertEqual(result["articles"], 54)
        self.assertEqual(result["withdrawn"], 4)
        ptr = json.loads((self.export / "current.json").read_text())
        manifest = json.loads((self.export / ptr["snapshot_index_url_path"]).read_text())
        self.assertEqual(manifest["archive"]["page_count"], 3)
        self.assertEqual(manifest["archive"]["article_count"], 54)

    def test_withdrawn_snapshot_does_not_embed_private_full_body(self):
        register(self.ledger, approved(headline="Prima pubblicazione verificata"), ACTOR, REASON)
        withdraw(self.ledger, "PULSE-TEST-001", ACTOR, REASON, confirmed=True)
        export_snapshot(self.ledger, self.export)
        archive = (self.export / "snapshots" / "generation_0000000002")
        self.assertFalse(list((archive / "pages").glob("*.json"))
                         if (archive / "pages").exists() else True)

    def test_store_requires_version_and_approval_no_synthetic_ai_shortcut(self):
        x = approved()
        x["approved_by"] = "ChatGPT"
        with self.assertRaises(ValueError):
            register(self.ledger, x, ACTOR, REASON)
        x = approved()
        x["publication_status"] = "not_publishable_without_human_review"
        with self.assertRaises(ValueError):
            register(self.ledger, x, ACTOR, REASON)


if __name__ == "__main__":
    unittest.main()
