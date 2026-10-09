"""Live smoke tests: five real official statistical publication landing pages.

No fabricated expected values: verifies retrieval, immutable SHA, and a safe outcome.
A landing page without a usable annual table MUST remain no_comparable_series.
"""
import json
import unittest
from scripts.pulse_evidence import extract_url

SOURCES = {
    "ISTAT": "https://www.istat.it/comunicato-stampa/occupati-e-disoccupati-dati-provvisori-maggio-2026/",
    "ISPRA": "https://www.isprambiente.gov.it/it/pubblicazioni/rapporti/rapporto-rifiuti-urbani-edizione-2025",
    "INPS": "https://www.inps.it/it/it/dati-e-bilanci/osservatori-statistici-e-altre-statistiche/dati-cartacei---auu.html",
    "BANCA_D_ITALIA": "https://www.bancaditalia.it/pubblicazioni/economia-italiana-in-breve/2026/index.html",
    "EUROSTAT": "https://ec.europa.eu/eurostat/web/products-eurostat-news/w/edn-20261005-1"
}

class LivePublications(unittest.TestCase):
    def test_real_publications(self):
        for institution, url in SOURCES.items():
            with self.subTest(institution=institution):
                result = extract_url(url)
                self.assertTrue(result["source_sha256"])
                self.assertEqual(len(result["source_sha256"]), 64)
                self.assertIn(result["status"], {
                    "verified", "no_comparable_series", "unsupported_format"
                })
                self.assertEqual(result["source_url"], url)
                for row in result["evidence"]:
                    self.assertEqual(row["source_sha256"], result["source_sha256"])
                    self.assertEqual(row["unit"], "%")
                print(json.dumps({
                    "source": institution, "status": result["status"],
                    "verified_series": len(result["evidence"])
                }))

if __name__ == "__main__":
    unittest.main()
