import unittest
from scripts.pulse_taxonomy import classify, load_taxonomy, enrich_articles, UNCLASSIFIED

class TaxonomyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tax = load_taxonomy()

    def test_dimensions(self):
        self.assertEqual(len(self.tax["macroareas"]), 7)
        self.assertEqual(sum(len(x["subcategories"]) for x in self.tax["macroareas"]), 57)

    def test_natality(self):
        self.assertEqual(classify("In Italia calano le nascite", taxonomy=self.tax)["primary_category"], "POP-02")

    def test_jobs(self):
        self.assertEqual(classify("Cresce l'occupazione femminile", taxonomy=self.tax)["primary_category"], "LAV-05")

    def test_ambiguity_stays_pending(self):
        result=classify("Lavoro e inflazione: rapporto", taxonomy=self.tax)
        self.assertEqual(result["primary_category"], UNCLASSIFIED)
        self.assertEqual(result["classification_status"], "review_needed")

    def test_no_publisher_shortcut(self):
        self.assertEqual(classify("Bollettino trimestrale", taxonomy=self.tax)["primary_category"], UNCLASSIFIED)

    def test_preserve_validated(self):
        article={"headline":"Occupazione", "taxonomy":{"taxonomy_version":"1.0","classification_status":"validated","primary_category":"SOC-06"}}
        enrich_articles([article], self.tax)
        self.assertEqual(article["taxonomy"]["primary_category"], "SOC-06")

    def test_existing_metadata_not_changed(self):
        article={"headline":"Calano le nascite", "pulse_score":72, "publication_status":"published"}
        enrich_articles([article], self.tax)
        self.assertEqual(article["pulse_score"],72)
        self.assertEqual(article["publication_status"],"published")

if __name__ == "__main__":
    unittest.main()
