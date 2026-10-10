import unittest
from scripts.pulse_editorial_evidence import enrich

class ObserverEditorialQualityTests(unittest.TestCase):
    def test_unproved_archive_pattern_is_not_shown(self):
        article={
            "headline":"Franchising: nuova accelerazione","summary":"Le vendite crescono.",
            "public_source":{"url":"https://www.istat.it/comunicato-stampa/esempio"},
            "patterns":["ACCELERAZIONE"],"verified_series":[],
            "publication_status":"published"
        }
        enrich(article)
        self.assertEqual(article["patterns"],[])
        self.assertEqual(article["pattern_validation_status"],"insufficient_evidence")
        self.assertEqual(article["publication_status"],"published")
        self.assertEqual(article["source_methodology"]["data_status"],"not_declared")

    def test_glossary_from_source_linked_text(self):
        article={"headline":"Flussi turistici: arrivi e presenze",
                 "summary":"La variazione tendenziale di presenze è positiva",
                 "public_source":{"url":"https://www.istat.it/"},
                 "patterns":[],"verified_series":[]}
        enrich(article)
        terms={entry["term"] for entry in article["glossary_entries"]}
        self.assertTrue({"arrivi","presenze","variazione tendenziale"} <= terms)

if __name__=="__main__":
    unittest.main()
