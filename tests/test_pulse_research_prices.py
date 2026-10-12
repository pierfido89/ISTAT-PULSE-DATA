"""CI tests for the 3-value ISTAT CPI 'Prospetto 1' research extraction.

Fixtures reflect the reported official August 2026 figures; the real
ISTAT PDF must separately pass the live smoke test before validation.
"""
import unittest

from scripts.pulse_research_prices import (
    SOURCE_URL, extract_istat_cpi_table, price_research_signals,
)
from scripts.pulse_research_engine import research_report

SHA = "f" * 64
TEXT = """PREZZI AL CONSUMO
FIGURA 1. INDICI DEI PREZZI AL CONSUMO NIC
PROSPETTO 1. INDICI DEI PREZZI AL CONSUMO NIC, IPCA E FOI
Agosto 2026, indici e variazioni percentuali congiunturali e tendenziali (base 2025=100)
Indici Variazioni congiunturali Variazioni tendenziali
agosto 2026 ago-26
lug-26
ago-26
ago-25
Indice nazionale per l’intera collettività NIC 103,9 +0,5 +3,3
Indice armonizzato IPCA 102,7 +0,1 +3,2
Indice per le famiglie di operai e impiegati FOI (senza tabacchi) 103,7 +0,6 +3,4
"""


def prices_fixture():
    rows = extract_istat_cpi_table(
        TEXT, url=SOURCE_URL, source_sha256=SHA, page_number=2
    )
    assert len(rows) == 3
    return {
        "id": "TEST-PRICES-2026-08",
        "source_sha256": SHA,
        "public_source": {"url": SOURCE_URL, "role": "primary_statistical_source"},
        "document_findings": rows, "verified_series": [],
    }


class PricesTests(unittest.TestCase):
    def test_three_distinct_indices_with_percent_changes(self):
        rows = prices_fixture()["document_findings"]
        indexed = {x["price_index_code"]: x for x in rows}
        self.assertEqual(indexed["NIC"]["observed_index"], 103.9)
        self.assertEqual(indexed["NIC"]["reported_yoy_change_pct"], 3.3)
        self.assertEqual(indexed["IPCA"]["reported_yoy_change_pct"], 3.2)
        self.assertEqual(indexed["FOI"]["reported_yoy_change_pct"], 3.4)
        self.assertTrue(all(row["unit"] == "indice_base_2025_100" for row in rows))
        self.assertEqual({x["segment"]["basket"] for x in rows},
                         {"NIC", "IPCA", "FOI"})

    def test_missing_index_or_duplicate_rejects_all(self):
        self.assertEqual(extract_istat_cpi_table(
            TEXT.replace("Indice armonizzato IPCA 102,7 +0,1 +3,2", ""),
            url=SOURCE_URL, source_sha256=SHA, page_number=2), [])
        self.assertEqual(extract_istat_cpi_table(
            TEXT + "\nIndice armonizzato IPCA 102,7 +0,1 +3,2",
            url=SOURCE_URL, source_sha256=SHA, page_number=2), [])

    def test_wrong_base_and_header_fails(self):
        for changed in (
            TEXT.replace("base 2025=100", "base 2015=100"),
            TEXT.replace("PROSPETTO 1.", "GRAFICO 1."),
            TEXT.replace("Variazioni tendenziali", "Altro"),
        ):
            self.assertEqual(extract_istat_cpi_table(
                changed, url=SOURCE_URL, source_sha256=SHA, page_number=2), [])

    def test_wrong_source_hash_or_domain_rejected(self):
        for url, sha in (
            (SOURCE_URL, "bad"), ("http://www.istat.it/invalid.pdf", SHA),
            ("https://www.example.org/file.pdf", SHA),
        ):
            self.assertEqual(extract_istat_cpi_table(
                TEXT, url=url, source_sha256=sha, page_number=2), [])

    def test_research_dossier_preserves_basket_comparability(self):
        doc = prices_fixture()
        signals = price_research_signals([doc])
        self.assertEqual(len(signals), 1)
        self.assertEqual(
            signals[0]["comparison"],
            "three_independent_price_baskets_rates_not_common_index_level",
        )
        report = research_report([doc])
        self.assertEqual(len(report["price_signals"]), 1)
        self.assertEqual(report["research_stories"][0]["story_type"],
                         "different_price_baskets_yoy_rates")
        self.assertEqual(report["verified_paired_candidate_count"], 0)
        self.assertEqual(report["research_candidates"], [])

    def test_price_signals_reject_unknown_source_or_ambiguity(self):
        doc = prices_fixture()
        doc["source_sha256"] = "e" * 64
        self.assertEqual(price_research_signals([doc]), [])
        doc = prices_fixture()
        doc["document_findings"].append(doc["document_findings"][0].copy())
        self.assertEqual(price_research_signals([doc]), [])


if __name__ == "__main__":
    unittest.main()
