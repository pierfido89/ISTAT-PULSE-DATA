"""NEW badge: 180 minutes strictly from original PULSE publication, not a source date."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from scripts.pulse_new_badge import (
    stamp_first_pulse_publication, is_new, parse_utc, original_date_utc
)


class NewBadgeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
        self.source = self.now - timedelta(minutes=15)
        self.article = {"id": "PULSE-FRESH-1", "publication_status": "published",
                        "editorial_status": "verified_primary_match"}
    def stamp(self, previous=None, source=None):
        article = deepcopy(self.article)
        return stamp_first_pulse_publication(
            article, previous, self.now, source if source is not None else self.source)

    def test_first_publication_stamped_only_for_new_current_pulse_article(self):
        a = self.stamp()
        self.assertEqual(parse_utc(a["first_published_at_utc"]), self.now)
        self.assertTrue(is_new(a, self.now + timedelta(minutes=179, seconds=59)))
        self.assertFalse(is_new(a, self.now + timedelta(minutes=180)))

    def test_first_seen_not_restarted_by_recrawl_or_content_edit(self):
        old = self.stamp()
        after = deepcopy(self.article)
        stamp_first_pulse_publication(after, old,
            self.now + timedelta(hours=8), self.now + timedelta(hours=8))
        self.assertEqual(after["first_published_at_utc"], old["first_published_at_utc"])
        self.assertFalse(is_new(after, self.now + timedelta(hours=8)))

    def test_pre_existing_legacy_record_without_first_pub_never_reborn(self):
        old = deepcopy(self.article)
        old["published_at"] = "2026-10-12T09:45:00+00:00"
        current = self.stamp(previous=old)
        self.assertNotIn("first_published_at_utc", current)

    def test_historical_report_import_is_not_new(self):
        self.assertNotIn("first_published_at_utc",
                         self.stamp(source=self.now-timedelta(days=20)))
        self.assertNotIn("first_published_at_utc",
                         self.stamp(source=self.now-timedelta(days=1, seconds=1)))

    def test_current_source_exact_24_hours_allowed(self):
        self.assertIn("first_published_at_utc",
                      self.stamp(source=self.now-timedelta(hours=24)))

    def test_missing_unzoned_future_source_not_new(self):
        for source in (None, self.now+timedelta(seconds=1),
                       "2026-10-12T09:30:00", "not-a-date"):
            a=deepcopy(self.article)
            stamp_first_pulse_publication(a, {}, self.now, source)
            self.assertNotIn("first_published_at_utc", a)

    def test_bad_publication_status_never_eligible(self):
        for status in ("draft","archived","withdrawn"):
            a=deepcopy(self.article)
            a["publication_status"]=status
            stamp_first_pulse_publication(a, None, self.now, self.source)
            self.assertNotIn("first_published_at_utc", a)

    def test_unverified_observer_document_never_new(self):
        for status in ("source_publication_verified", "", "unknown"):
            a=deepcopy(self.article)
            a["editorial_status"]=status
            stamp_first_pulse_publication(a, None, self.now, self.source)
            self.assertNotIn("first_published_at_utc", a)

    def test_utc_offset_and_cross_midnight(self):
        a=self.stamp()
        first_rome="2026-10-12T12:00:00+02:00"
        self.assertEqual(parse_utc(first_rome),self.now)
        a["first_published_at_utc"]=first_rome
        self.assertTrue(is_new(a, self.now+timedelta(minutes=179)))
        self.assertFalse(is_new(a, self.now+timedelta(minutes=181)))

    def test_no_future_badges_and_no_malformed_badges(self):
        a=self.stamp()
        self.assertFalse(is_new(a,self.now-timedelta(milliseconds=1)))
        for t in ("", "2026-10-12", "2026-10-12T10:00:00", "invalid"):
            a["first_published_at_utc"]=t
            self.assertFalse(is_new(a,self.now))

    def test_rss_freshness_is_source_publication_not_ingestion(self):
        raw="Mon, 12 Oct 2026 09:45:00 +0000"
        source=original_date_utc(raw)
        self.assertEqual(source,self.now-timedelta(minutes=15))
        self.assertIn("first_published_at_utc",self.stamp(source=source))

    def test_absent_original_rss_date_does_not_trigger_freshness(self):
        self.assertIsNone(original_date_utc(""))
        self.assertIsNone(original_date_utc("Mon, 12 Oct 2026 09:45:00"))
        self.assertIsNone(original_date_utc("invalid"))

if __name__ == "__main__":
    unittest.main()
