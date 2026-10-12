from datetime import datetime,timedelta,timezone
import unittest
from scripts.pulse_push_dispatch import (
    authoritative_geo,eligible_recipient,validate_subscription,document_key,
    article_is_eligible,push_data,geo_matches
)
NOW=datetime(2026,10,12,12,0,tzinfo=timezone.utc)
def article(**kw):
    a={"id":"PULSE-ARTICLE-001","publication_status":"published",
       "editorial_status":"verified","first_published_at_utc":
       (NOW-timedelta(minutes=5)).isoformat(),"headline":"Dato ufficiale Lazio",
       "topic":"AMBIENTE","pulse_score":90,
       "territories":["lazio"]}
    a.update(kw)
    return a
def subscription(**kw):
    s={"enabled":True,"token":"x"*60,"consent_version":"pulse-push-consent-v1",
       "consent_at":(NOW-timedelta(minutes=10)).isoformat(),
       "topics":["AMBIENTE"],"min_score":80,
       "territory":{"level":"REGIONE","code":"12"},
       "include_national":False}
    s.update(kw)
    return s
class PushTests(unittest.TestCase):
    def test_real_matching_strict_region(self):
        self.assertTrue(eligible_recipient(article(),subscription(),NOW))
        self.assertFalse(eligible_recipient(article(territories=["lombardia"]),subscription(),NOW))
    def test_scoped_province_cannot_match_region_by_ambiguous_text(self):
        a=article(headline="Roma Lazio",territories=["lazio"])
        self.assertFalse(eligible_recipient(a,subscription(territory={"level":"PROVINCIA","code":"058"}),NOW))
    def test_precise_codes_match_only_exact_province_and_city(self):
        a=article(push_geo={"level":"PROVINCIA","code":"058"})
        self.assertTrue(eligible_recipient(a,subscription(territory={"level":"PROVINCIA","code":"058"}),NOW))
        self.assertFalse(eligible_recipient(a,subscription(territory={"level":"COMUNE","code":"058091"}),NOW))
        a["push_geo"]={"level":"COMUNE","code":"058091"}
        self.assertTrue(eligible_recipient(a,subscription(territory={"level":"COMUNE","code":"058091"}),NOW))
    def test_national_news_are_opt_in_under_regional_filter(self):
        a=article(territories=["italia"])
        self.assertFalse(eligible_recipient(a,subscription(),NOW))
        self.assertTrue(eligible_recipient(a,subscription(include_national=True),NOW))
    def test_topic_and_min_score_constraints(self):
        self.assertFalse(eligible_recipient(article(topic="ECONOMIA"),subscription(),NOW))
        self.assertFalse(eligible_recipient(article(pulse_score=71),subscription(),NOW))
        self.assertTrue(eligible_recipient(article(topic="ECONOMIA"),subscription(topics=["TUTTE"]),NOW))
    def test_no_consent_no_token_no_subscription(self):
        self.assertFalse(eligible_recipient(article(),subscription(enabled=False),NOW))
        self.assertFalse(eligible_recipient(article(),subscription(token=""),NOW))
        self.assertFalse(eligible_recipient(article(),subscription(consent_at=""),NOW))
        self.assertFalse(eligible_recipient(article(),subscription(consent_version="obsolete"),NOW))
    def test_no_backfill_after_user_opt_in(self):
        self.assertFalse(eligible_recipient(article(),subscription(consent_at=NOW.isoformat()),NOW))
    def test_stale_unsupported_and_legacy_articles_do_not_notify(self):
        for candidate in (
            article(first_published_at_utc=""),
            article(first_published_at_utc=(NOW-timedelta(hours=25)).isoformat()),
            article(publication_status="withdrawn"),
            article(editorial_status="unverified"),
            article(id="INVALID"),
            article(territories=["Roma"]),
            article(first_published_at_utc=(NOW+timedelta(minutes=1)).isoformat())
        ):
            self.assertFalse(article_is_eligible(candidate,NOW))
    def test_no_fuzzy_headline_inference(self):
        a=article(territories=[],headline="Roma e Milano - 12 comuni")
        self.assertIsNone(authoritative_geo(a))
    def test_no_broad_region_converted_to_city_without_code(self):
        a=article(push_geo={"level":"COMUNE","code":"058091"})
        self.assertFalse(eligible_recipient(a,subscription(),NOW))
    def test_unsafe_territory_codes_rejected(self):
        for sub in (subscription(territory={"level":"REGIONE","code":"99"}),
                    subscription(territory={"level":"COMUNE","code":"Roma"}),
                    subscription(territory={"level":"ITALIA","code":"12"}),
                    subscription(territory={"level":"PROVINCIA","code":"058091"})):
            self.assertFalse(validate_subscription(sub))
    def test_duplicate_key_same_identity_across_retries(self):
        self.assertEqual(document_key("user1","PULSE-ARTICLE-001"),
                         document_key("user1","PULSE-ARTICLE-001"))
        self.assertNotEqual(document_key("user2","PULSE-ARTICLE-001"),
                            document_key("user1","PULSE-ARTICLE-001"))
    def test_data_payload_does_not_expose_user_or_secrets(self):
        d=push_data(article())
        self.assertEqual(d["territory_code"],"12")
        self.assertNotIn("uid",d)
        self.assertNotIn("token",d)
        self.assertNotIn("consent_at",d)
    def test_unregistered_unknown_topic_rejected(self):
        self.assertFalse(validate_subscription(subscription(topics=["BOMB"])))
        self.assertFalse(eligible_recipient(article(topic="ENERGIA"), subscription(topics=["ECONOMIA"]),NOW))
    def test_national_scope_receives_verified_geo_only(self):
        self.assertTrue(eligible_recipient(article(),subscription(territory={"level":"ITALIA","code":""}),NOW))
        self.assertFalse(eligible_recipient(article(territories=[]),subscription(territory={"level":"ITALIA","code":""}),NOW))
if __name__=="__main__":
    unittest.main()
