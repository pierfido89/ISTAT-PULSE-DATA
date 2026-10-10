import unittest
from scripts.pulse_taxonomy import load_topics, classify, enrich_article, UNCLASSIFIED

class TaxonomyContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topics = load_topics()

    def test_dictionary_has_unique_57_codes(self):
        self.assertEqual(len(self.topics), 57)
        self.assertEqual(len({c["code"] for c in self.topics}), 57)
        self.assertEqual(len({c["code"].split("-")[0] for c in self.topics}), 7)

    def test_clear_multi_hint_topic_is_provisional(self):
        result = classify("Occupazione giovanile: aumentano gli occupati", self.topics)
        self.assertEqual(result["primary_category"], "LAV-05")
        self.assertEqual(result["classification_status"], "provisional")

    def test_ambiguous_topic_remains_unclassified(self):
        result = classify("Nuovo rapporto annuale con dati generali", self.topics)
        self.assertEqual(result["primary_category"], UNCLASSIFIED)
        self.assertEqual(result["classification_status"], "review_needed")

    def test_preserves_statistical_score_and_source(self):
        article = {"headline": "Occupazione e occupati in Italia", "topic": "LAVORO",
                   "pulse_score": 82, "public_source": {"url": "https://istat.it/a"}}
        out = enrich_article(article, self.topics)
        self.assertEqual(out["pulse_score"], 82)
        self.assertEqual(out["public_source"], article["public_source"])
        self.assertEqual(out["taxonomy_version"], "1.0")
        self.assertEqual(out["classification_method"], "rules")

    def test_preserves_previous_validated_decision(self):
        article = {"headline": "Titolo generico", "primary_category": "POP-02",
                   "classification_status": "validated",
                   "classification_reason": "Manual check"}
        out = enrich_article(article, self.topics)
        self.assertEqual(out["primary_category"], "POP-02")
        self.assertEqual(out["classification_status"], "validated")

if __name__ == "__main__":
    unittest.main()
