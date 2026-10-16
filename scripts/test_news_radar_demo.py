"""Offline regression checks for PULSE news radar, no network or paid APIs."""
import unittest
from unittest.mock import patch
from scripts import update_news_radar as radar


class FakeReply:
    def __init__(self, req):
        self.req = req
        self.headers = {"Content-Type": "application/rss+xml"}
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, size):
        return b"<rss/>"
    def geturl(self):
        return self.req.full_url


class RadarDemoTests(unittest.TestCase):
    def test_accented_query_is_percent_encoded(self):
        urls = []
        def fake_open(req, timeout=0):
            urls.append(req.full_url)
            return FakeReply(req)
        with patch.object(radar.urllib.request, "urlopen", fake_open):
            data, final, ct = radar.fetch(
                "https://news.google.com/rss/search?q=sanità+popolazione&hl=it",
                timeout=3)
        self.assertEqual(data, b"<rss/>")
        self.assertIn("sanit%C3%A0", urls[0])
        self.assertNotIn("à", urls[0])
        self.assertIn("popolazione", final)

    def test_existing_percent_escapes_are_preserved(self):
        with patch.object(radar.urllib.request, "urlopen", lambda req, timeout=0: FakeReply(req)):
            _, url, _ = radar.fetch("https://example.org/?q=universit%C3%A0")
        self.assertIn("universit%C3%A0", url)
        self.assertNotIn("%25C3", url)

    def test_geo_is_not_extracted_from_partial_word(self):
        self.assertEqual(radar.detect_geo("economia nazionale in Italia"), [])
        self.assertIn("lazio", radar.detect_geo("Prezzi per il Lazio"))

    def test_cpi_is_economics_not_work(self):
        self.assertEqual(radar.classify_topic("Prezzi al consumo, settembre 2026"), "ECONOMIA")
        self.assertEqual(radar.classify_topic("Occupazione e disoccupazione"), "LAVORO")

    def test_primary_match_rejects_coincidental_values(self):
        false_match={"verification_score":55,"matched_numbers":["1%","2026"],
                     "matched_keywords":[]}
        valid_match={"verification_score":92,"matched_numbers":["1,5%"],
                     "matched_keywords":["prezzi","consumo","settembre"]}
        self.assertFalse(radar.strong_primary_match(false_match))
        self.assertTrue(radar.strong_primary_match(valid_match))

    def test_unverified_media_stays_in_quarantine(self):
        from datetime import datetime, timezone
        now=datetime(2026,10,16,12,0,tzinfo=timezone.utc)
        item={"title":"Inflazione al 4,5% nel 2026 - Agenzia stampa",
              "url":"https://news.google.com/rss/articles/example",
              "summary":"Pubblicato un rapporto sul tasso d'inflazione.",
              "published_raw":"Fri, 16 Oct 2026 10:00:00 GMT"}
        row=radar.journalistic_statistical_article(item, {}, now, "ECONOMIA", [],
                                                   ["4,5%", "2026"], 72)
        self.assertIsNotNone(row)
        self.assertEqual(row["publication_status"],"quarantined")
        self.assertEqual(row["editorial_status"],"needs_primary_source")
        self.assertEqual(row["statistical_claims"][0]["verified"],False)

if __name__=="__main__":
    unittest.main()
