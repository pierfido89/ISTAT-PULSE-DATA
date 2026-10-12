"""Offline v2 archive regression; verify no unapproved article is indexed."""
from datetime import datetime, timedelta, timezone
import unittest
from scripts.pulse_editorial_archive_v2 import paginate


def article(i):
    at=(datetime(2026,10,11,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat()
    return {"id":f"PULSE-ARTICLE-{i:05d}",
            "publication_status":"approved_for_pulse",
            "human_approved":True,"approved_by":"Reviewer",
            "first_published_at_utc":at,
            "primary_source_url":"https://www.istat.it/rapporti/document.pdf",
            "headline":f"Un dato ufficiale: articolo {i}",
            "paragraphs":["Testo ufficialmente revisionato e verificato." for _ in range(4)]}


class ArchiveTests(unittest.TestCase):
    def test_empty_approved_feed_remains_empty(self):
        idx,pages=paginate([])
        self.assertEqual(idx["page_count"],0)
        self.assertEqual(idx["article_count"],0)
        self.assertEqual(pages,{})
        self.assertFalse(idx["auto_publish_enabled"])

    def test_thousands_of_articles_without_first_40_limit(self):
        idx,pages=paginate([article(i) for i in range(1001)])
        self.assertEqual(idx["article_count"],1001)
        self.assertEqual(idx["page_count"],41)
        self.assertEqual(len(pages["pages/page_00001.json"]["articles"]),25)
        self.assertEqual(len(pages["pages/page_00041.json"]["articles"]),1)
        self.assertEqual(pages["pages/page_00001.json"]["articles"][0]["id"],"PULSE-ARTICLE-01000")
        self.assertFalse(idx["publication_allowed_by_this_script"])

    def test_duplicate_article_rejected(self):
        with self.assertRaises(ValueError): paginate([article(1),article(1)])

    def test_model_drafts_never_enter_archive(self):
        a=article(1)
        a["publication_status"]="not_publishable_without_human_review"
        with self.assertRaises(ValueError): paginate([a])
        a=article(1)
        a["human_approved"]=False
        with self.assertRaises(ValueError): paginate([a])

    def test_timezones_and_missing_timestamp(self):
        a=article(1);a["first_published_at_utc"]="2026-10-11T09:00:00"
        with self.assertRaises(ValueError):paginate([a])
        a=article(1);a["first_published_at_utc"]="2026-10-11T09:00:00Z"
        self.assertEqual(paginate([a])[0]["page_count"],1)

    def test_rejects_http_and_empty_text(self):
        a=article(1);a["primary_source_url"]="http://example.com"
        with self.assertRaises(ValueError):paginate([a])
        a=article(1);a["paragraphs"]=[]
        with self.assertRaises(ValueError):paginate([a])


if __name__=="__main__":
    unittest.main()
