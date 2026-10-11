"""PULSE automated publishing prerequisites: offline, no keys or spending."""
import unittest
from scripts.pulse_editorial_operations import (
    API_PRODUCTION_ENABLED, PUBLISHING_ENABLED, build_queue, estimate_articles,
    price_usd, show_new_badge, source_identity
)
from decimal import Decimal

HASH_A="a"*64
HASH_B="b"*64
T="2026-10-11T12:00:00Z"


def item(url="https://www.istat.it/wp-content/uploads/report.pdf",
         sha=HASH_A, released="2026-10-11T10:00:00Z",
         status="VERIFIED_FACTS", **updates):
    return {"primary_source_url":url,"source_sha256":sha,
            "official_released_at":released,"status":status,
            "evidence_verified":True,**updates}


class EditorialOperationsTest(unittest.TestCase):
    def test_no_money_or_publication_enabled(self):
        self.assertFalse(API_PRODUCTION_ENABLED)
        self.assertFalse(PUBLISHING_ENABLED)
        self.assertFalse(estimate_articles(60)["paid_api_enabled"])
        self.assertFalse(estimate_articles(60)["automatic_publication_enabled"])

    def test_verified_current_precedes_historic(self):
        archive=item(url="https://www.istat.it/old.pdf",
                     released="2024-08-01T12:00:00Z",archive_backfill=True)
        live=item()
        batch=build_queue([archive,live],T)
        self.assertEqual([a["queue_lane"] for a in batch],["CURRENT","ARCHIVE"])
        self.assertTrue(all(a["publication_allowed"] is False for a in batch))

    def test_duplicate_url_and_document_is_removed(self):
        d1=item()
        d2=item(url="https://www.istat.it/wp-content/uploads/report.pdf?utm_source=feed#page=2")
        self.assertEqual(len(build_queue([d1,d2],T)),1)
        self.assertEqual(source_identity(d1["primary_source_url"],HASH_A),
                         source_identity(d2["primary_source_url"],HASH_A))

    def test_changed_primary_document_version_is_not_lost(self):
        self.assertEqual(len(build_queue([item(),item(sha=HASH_B)],T)),2)

    def test_unverified_quarantined_and_retry_delay_never_published(self):
        raw=[item(evidence_verified=False),item(status="QUARANTINED"),
             item(status="RETRY",next_attempt_at="2026-10-12T07:00:00Z")]
        self.assertEqual(build_queue(raw,T),[])

    def test_rejects_http_or_fake_hash(self):
        with self.assertRaises(ValueError): source_identity("http://example.com/file.pdf",HASH_A)
        with self.assertRaises(ValueError): source_identity("https://example.com/file.pdf","x"*64)
        with self.assertRaises(ValueError): build_queue([item(status="PUBLISHED"),item(status="CORRUPT")],T)

    def test_new_badge_expires_at_three_hours_exactly(self):
        created="2026-10-11T09:00:00Z"
        self.assertTrue(show_new_badge(created,"2026-10-11T11:59:59Z"))
        self.assertFalse(show_new_badge(created,"2026-10-11T12:00:00Z"))
        self.assertFalse(show_new_badge(created,"2026-10-11T08:59:59Z"))
        self.assertFalse(show_new_badge(created,"2026-10-11T10:00:00Z",archive_backfill=True))
        self.assertFalse(show_new_badge("bad","2026-10-11T11:00:00Z"))

    def test_correct_cost_math_luna_and_sol(self):
        self.assertEqual(price_usd("gpt-6-luna",10_000,2_000), Decimal("0.0020"))
        self.assertEqual(price_usd("gpt-6-luna",12_000,1_500), Decimal("0.00195"))
        self.assertEqual(price_usd("gpt-6.1-sol",12_000,1_500), Decimal("0.0390"))
        quote=estimate_articles(300,escalation_fraction="0.20",retry_factor="1.25",budget_usd="5")
        self.assertEqual(quote["estimated_total_usd"],"4.4063")
        self.assertTrue(quote["within_budget"])
        self.assertEqual(quote["articles"],300)

    def test_strict_sol_review_exceeds_five_dollars_at_scale(self):
        quote=estimate_articles(300,escalation_fraction="1",retry_factor="1.25",budget_usd="5")
        self.assertFalse(quote["within_budget"])

    def test_cost_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError): estimate_articles(1,escalation_fraction="2")
        with self.assertRaises(ValueError): estimate_articles(-1)
        with self.assertRaises(ValueError): estimate_articles(1,retry_factor="0.5")
        with self.assertRaises(ValueError): price_usd("fake",300,400)


if __name__=="__main__":
    unittest.main()
