"""Offline safety tests: ChatGPT-only editorial preview must never self-publish."""
import hashlib
import json
import unittest

from scripts.pulse_editorial_publication_gate import prepare, validate_approved_feed


def sample():
    p = "La fonte osserva i valori ufficiali per il periodo specificato senza attribuire cause non documentate. " * 2
    return {
        "schema_version": "pulse-chatgpt-direct-editorial-v1",
        "published": False, "auto_publish": False,
        "human_fact_check_required": True,
        "articles": [{
            "id": "LABOR-2026-08", "headline": "Lavoro in agosto 2026: andamento osservato del mercato italiano",
            "paragraphs": [p] * 4,
            "primary_source_url": "https://www.istat.it/wp-content/uploads/2026/10/sample.pdf",
            "publication_status": "not_publishable_without_human_review",
            "evidence": [
                {"claim": "Occupati 24.352.000", "location": "Tabella 1, riga Totale"},
                {"claim": "Disoccupati 1.591.000", "location": "Tabella 1, riga Totale"},
            ]
        }]
    }


def approved(doc):
    return {"schema_version": "pulse-editorial-human-approval-v1",
            "draft_sha256": hashlib.sha256(json.dumps(doc).encode()).hexdigest(),
            "approved_by": "Revisore editoriale umano", "approved_at": "2026-10-11T14:00:00+02:00",
            "approved_articles": [{"id": "LABOR-2026-08", "reviewed_claims_and_source": True,
                                   "topic": "LAVORO", "reference_period": "2026-08"}]}


class HumanApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.doc = sample()
        self.raw = json.dumps(self.doc).encode()
        self.signoff = approved(self.doc)
        self.public = {"schema_version": "pulse-editorial-approved-v1",
                       "channel": "approved_editorial_only",
                       "generated_at": None, "articles": []}

    def test_initially_empty_channel(self):
        validate_approved_feed(self.public)
        self.assertEqual(self.public["articles"], [])

    def test_only_explicit_signoff_promotes(self):
        result = prepare(self.raw, self.signoff, self.public)
        self.assertEqual(len(result["articles"]), 1)
        self.assertTrue(result["articles"][0]["human_approved"])
        self.assertEqual(result["articles"][0]["reference_period"], "2026-08")
        self.assertEqual(len(self.public["articles"]), 0)

    def test_wrong_hash_rejected(self):
        self.signoff["draft_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            prepare(self.raw, self.signoff, self.public)

    def test_ai_as_human_rejected(self):
        self.signoff["approved_by"] = "ChatGPT"
        with self.assertRaises(ValueError):
            prepare(self.raw, self.signoff, self.public)

    def test_missing_specific_claim_review_rejected(self):
        self.signoff["approved_articles"][0]["reviewed_claims_and_source"] = False
        with self.assertRaises(ValueError):
            prepare(self.raw, self.signoff, self.public)

    def test_no_private_drafts_pass_as_public(self):
        public = dict(self.public)
        public["articles"] = [{**self.doc["articles"][0],
            "publication_status": "draft_only", "human_approved": False}]
        with self.assertRaises(ValueError):
            validate_approved_feed(public)

    def test_unapproved_unknown_id_rejected(self):
        self.signoff["approved_articles"][0]["id"] = "OTHER-2026-08"
        with self.assertRaises(ValueError):
            prepare(self.raw, self.signoff, self.public)

    def test_disallows_non_https_and_tiny_paragraphs(self):
        result = prepare(self.raw, self.signoff, self.public)
        result["articles"][0]["primary_source_url"] = "http://example.com"
        with self.assertRaises(ValueError):
            validate_approved_feed(result)
        result["articles"][0]["primary_source_url"] = self.doc["articles"][0]["primary_source_url"]
        result["articles"][0]["paragraphs"] = ["short"] * 4
        with self.assertRaises(ValueError):
            validate_approved_feed(result)


if __name__ == "__main__":
    unittest.main()
