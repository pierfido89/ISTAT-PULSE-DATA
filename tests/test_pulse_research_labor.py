"""ISTAT labor research: official Prospetto 1 shape and fail-closed guards.

Synthetic fixture follows the structure shown by the ISTAT August 2026
table but is NOT itself primary evidence. CI smoke downloads the real
PDF and requires 9 independently sourced rows.
"""
import unittest
from unittest.mock import patch
from scripts.pulse_research_labor import (
    SOURCE_URL, extract_istat_labor_table, labor_research_signals,
)
from scripts.pulse_research_engine import research_report


SRC_SHA = "a" * 64
TEXT = """OCCUPATI
E DISOCCUPATI
LE DIFFERENZE DI GENERE
PROSPETTO 1. POPOLAZIONE PER GENERE E CONDIZIONE PROFESSIONALE
Agosto 2026, dati destagionalizzati
Valori assoluti
(migliaia di unità)
Variazioni congiunturali Variazioni tendenziali
ago26 ago25 (percentuali)
MASCHI
Occupati 13.977 -4 0,0 +40 +0,3 +157 +1,1
Disoccupati 838 +41 +5,2 +58 +7,6 +71 +9,3
Inattivi 15-64 anni 4.457 -18 -0,4 -88 -1,9 -170 -3,7
FEMMINE
Occupati 10.375 -1 0,0 0 0,0 +134 +1,3
Disoccupati 753 +7 +0,9 +65 +9,6 +57 +8,2
Inattivi 15-64 anni 7.667 -3 0,0 -76 -1,0 -211 -2,7
TOTALE
Occupati 24.352 -5 0,0 +40 +0,2 +291 +1,2
Disoccupati 1.591 +48 +3,1 +123 +8,5 +129 +8,8
Inattivi 15-64 anni 12.124 -21 -0,2 -164 -1,3 -381 -3,0
"""


def fixture():
    rows = extract_istat_labor_table(
        TEXT, url=SOURCE_URL, source_sha256=SRC_SHA, page_number=3,
    )
    assert len(rows) == 9
    return {
        "id": "SOURCE-TEST-LABOR",
        "public_source": {
            "url": SOURCE_URL, "role": "primary_statistical_source",
        },
        "source_sha256": SRC_SHA,
        "document_findings": rows,
        "verified_series": [],
        "publication_status": "workbench_only",
    }


class LaborExtractionTests(unittest.TestCase):
    def test_all_nine_rows_extracted_from_explicit_table(self):
        rows = fixture()["document_findings"]
        self.assertEqual(len(rows), 9)
        total = {x["indicator"]: x for x in rows
                 if x["segment"]["sex"] == "totale"}
        self.assertEqual(total["Occupati"]["observed_total"], 24352000)
        self.assertEqual(total["Occupati"]["reported_yoy_change_pct"], 1.2)
        self.assertEqual(total["Disoccupati"]["observed_total"], 1591000)
        self.assertEqual(total["Disoccupati"]["reported_yoy_change_pct"], 8.8)
        self.assertEqual(total["Inattivi 15-64 anni"]["observed_total"], 12124000)
        self.assertEqual(total["Disoccupati"]["reference_period"], "2026-08")
        self.assertEqual(total["Disoccupati"]["unit_multiplier"], 1000)
        self.assertIn("page:3:text:line:", total["Disoccupati"]["location"])

    def test_missing_caption_or_wrong_units_fail(self):
        for s in (
            TEXT.replace("PROSPETTO 1.", "GRAFICO 1."),
            TEXT.replace("migliaia di unità", "milioni di unità"),
            TEXT.replace("Variazioni tendenziali", "Altro dato"),
            TEXT.replace("Agosto 2026", "Data ignota"),
        ):
            rows = extract_istat_labor_table(
                s, url=SOURCE_URL, source_sha256=SRC_SHA, page_number=3)
            self.assertEqual(rows, [])

    def test_incomplete_or_ambiguous_table_fails(self):
        text_missing = TEXT.replace(
            "Disoccupati 1.591 +48 +3,1 +123 +8,5 +129 +8,8", "")
        self.assertEqual(extract_istat_labor_table(
            text_missing, url=SOURCE_URL, source_sha256=SRC_SHA,
            page_number=3), [])
        text_duplicate = TEXT + "\nOccupati 24.352 -5 0,0 +40 +0,2 +291 +1,2\n"
        self.assertEqual(extract_istat_labor_table(
            text_duplicate, url=SOURCE_URL, source_sha256=SRC_SHA,
            page_number=3), [])

    def test_untrusted_url_or_hash_fails(self):
        for u, sha in (
            ("https://www.other-site.it/file.pdf", SRC_SHA),
            ("http://www.istat.it/file.pdf", SRC_SHA),
            (SOURCE_URL, "fake"),
        ):
            self.assertEqual(extract_istat_labor_table(
                TEXT, url=u, source_sha256=sha, page_number=3), [])

    def test_labor_signal_is_still_research_only(self):
        rows = labor_research_signals([fixture()])
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r["publication_status"], "research_only")
            self.assertEqual(r["comparison"],
                             "different_category_yoy_changes_not_one_common_rate")
        dossier = research_report([fixture()])
        self.assertEqual(len(dossier["labor_signals"]), 3)
        self.assertEqual(len(dossier["research_stories"]), 3)
        self.assertEqual(dossier["verified_paired_candidate_count"], 0)

    def test_bad_multiplier_or_source_location_blocks_group(self):
        doc = fixture()
        doc["document_findings"][0]["unit_multiplier"] = 1
        found = labor_research_signals([doc])
        self.assertEqual(len(found), 2)
        doc = fixture()
        doc["document_findings"][0]["observed_total"] = 1
        found = labor_research_signals([doc])
        self.assertEqual(len(found), 2)

    def test_wrong_period_separates_groups(self):
        doc = fixture()
        doc["document_findings"][0]["reference_period"] = "2025-08"
        found = labor_research_signals([doc])
        self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
