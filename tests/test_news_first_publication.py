"""Contract tests for the genuine 180-minute NEW marker, no retroactive badges."""
import unittest
from datetime import datetime, timezone, timedelta
from scripts.update_news_radar import mark_first_pulse_publications


def article(aid, *, stage="verified", first=None):
    row = {"id": aid, "publication_status": "published", "editorial_status": stage,
           "published_at": "2026-10-11T08:00:00Z"}
    if first:
        row["first_published_at_utc"] = first
    return row


class FirstPulsePublicationContractTest(unittest.TestCase):
    now = datetime(2026, 10, 12, 16, 0, tzinfo=timezone.utc)

    def test_new_verified_story_only_gets_current_publication_clock(self):
        previous = [article("LEGACY")]
        updated = [article("LEGACY"), article("NEW")]
        result = mark_first_pulse_publications(updated, previous, self.now)
        self.assertNotIn("first_published_at_utc", result[0])
        self.assertEqual("2026-10-12T16:00:00Z", result[1]["first_published_at_utc"])

    def test_refresh_never_restarts_three_hour_countdown(self):
        original = article("A", first="2026-10-12T12:00:00Z")
        changed = article("A", first="2026-10-12T16:00:00Z")
        result = mark_first_pulse_publications([changed], [original], self.now)
        self.assertEqual("2026-10-12T12:00:00Z", result[0]["first_published_at_utc"])

    def test_legacy_article_does_not_receive_badge_on_reimport(self):
        previous = [article("OLD")]
        changed = article("OLD", first="2026-10-12T16:00:00Z")
        result = mark_first_pulse_publications([changed], previous, self.now)
        self.assertNotIn("first_published_at_utc", result[0])

    def test_initial_bulk_import_not_labelled_as_just_published(self):
        result = mark_first_pulse_publications([article("HISTORICAL")], [], self.now)
        self.assertNotIn("first_published_at_utc", result[0])

    def test_drafts_and_unverified_stories_get_no_new_badge(self):
        previous = [article("PREVIOUS")]
        draft = article("DRAFT", stage="unverified")
        result = mark_first_pulse_publications([draft], previous, self.now)
        self.assertNotIn("first_published_at_utc", result[0])

    def test_timezone_normalizes_to_utc(self):
        local = datetime(2026, 10, 12, 18, 0,
                         tzinfo=timezone(timedelta(hours=2)))
        result = mark_first_pulse_publications(
            [article("NEW")], [article("EXISTING")], local)
        self.assertEqual("2026-10-12T16:00:00Z", result[0]["first_published_at_utc"])


if __name__ == "__main__":
    unittest.main()
