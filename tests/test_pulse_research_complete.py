"""PULSE Research full-document, history and territory contracts.

All fixtures are synthetic and labeled so; no claim these rates/series
were published by ISTAT. Tests prove parser/guard behaviour, NOT that
publications in other domains are already integrated.
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts.pulse_research_reading import (
    _extract_lines, match_passages, read_pdf_publication,
)
from scripts.pulse_research_comparisons import historical_signals, territorial_signals
from scripts.pulse_research_engine import research_report
from test_pulse_editorial_pairs import pair_fixture
from test_pulse_editorial_ai import SOURCE


SHA = "e" * 64


def annual_source():
    doc = pair_fixture()
    doc["verified_series"] = [{
        "indicator": "Indice di esempio",
        "unit": "indice",
        "territory": "Italia",
        "population_scope": "totale residenti",
        "source_url": SOURCE,
        "source_sha256": SHA,
        "location": "page:8:table:2",
        "verified": True,
        "extraction_method": "same_row_explicit_year_html_table",
        "observations": [
            {"period": "2022", "value": 100},
            {"period": "2023", "value": 104},
            {"period": "2024", "value": 107},
            {"period": "2025", "value": 109},
        ]
    }]
    return doc


def territorial_source():
    doc = pair_fixture()
    docs = []
    for code, label, val, line in (
        ("ITC4", "Lombardia", 8.3, 20),
        ("ITI4", "Lazio", 11.7, 21),
        ("ITF3", "Campania", 15.4, 22),
    ):
        docs.append({
            "indicator": "Tasso di esempio", "unit": "%",
            "denominator_id": "totale_regione_comparabile",
            "population_scope": "tutte le persone",
            "reference_period": "2025", "value": val,
            "territory": {"code": code, "name": label, "level": "regione"},
            "source_url": SOURCE, "source_sha256": SHA,
            "location": f"page:7:table:1:line:{line}",
            "verified": True,
            "extraction_method": "explicit_territorial_rate_table",
        })
    doc["document_findings"].extend(docs)
    return doc


class HistoryTests(unittest.TestCase):
    def test_verified_four_year_series(self):
        result = historical_signals([annual_source()])
        self.assertEqual(len(result), 1)
        record = result[0]
        self.assertEqual(record["comparison_direction"], "increase")
        self.assertEqual(record["first_value"], "100.0")
        self.assertEqual(record["last_value"], "109.0")
        self.assertEqual(record["periods"], [2022, 2023, 2024, 2025])
        self.assertTrue(record["monotone_at_least_four_years"])
        self.assertTrue(record["not_official_pulse_pattern"])

    def test_rejects_gaps_in_years_or_unverified_series(self):
        doc = annual_source()
        doc["verified_series"][0]["observations"][1]["period"] = "2026"
        self.assertEqual(historical_signals([doc]), [])
        doc = annual_source()
        doc["verified_series"][0]["verified"] = False
        self.assertEqual(historical_signals([doc]), [])

    def test_wrong_source_hash_or_missing_population_blocks(self):
        for key, value in (("source_sha256", ""), ("population_scope", ""),
                           ("location", ""), ("extraction_method", "fake")):
            doc = annual_source()
            doc["verified_series"][0][key] = value
            self.assertEqual(historical_signals([doc]), [], key)

    def test_zero_baseline_does_not_invent_relative_change(self):
        doc = annual_source()
        doc["verified_series"][0]["observations"][0]["value"] = 0
        row = historical_signals([doc])[0]
        self.assertIsNone(row["percent_change_from_first"])

    def test_annual_history_is_in_research_dossier(self):
        dossier = research_report([annual_source()])
        self.assertEqual(len(dossier["historical_signals"]), 1)
        self.assertEqual(dossier["coverage"]["historical_comparison_stories"],
                         "verified_records_available")
        self.assertIn("historical_annual_comparison",
                      [r["story_type"] for r in dossier["research_stories"]])


class TerritoryTests(unittest.TestCase):
    def test_territory_comparison_from_proven_normalized_rates(self):
        result = territorial_signals([territorial_source()])
        self.assertEqual(len(result), 1)
        r = result[0]
        self.assertEqual(r["low"]["name"], "Lombardia")
        self.assertEqual(r["high"]["name"], "Campania")
        self.assertEqual(r["gap"], "7.1")
        self.assertEqual(r["gap_unit"], "percentage_points")
        self.assertEqual(r["number_of_verified_territories"], 3)
        self.assertTrue(r["not_statistical_significance"])

    def test_totals_with_unknown_denominator_cannot_be_ranked(self):
        doc = territorial_source()
        for row in doc["document_findings"][-3:]:
            row["unit"] = "persone"
        self.assertEqual(territorial_signals([doc]), [])

    def test_different_population_or_denominator_cannot_be_combined(self):
        doc = territorial_source()
        doc["document_findings"][-1]["population_scope"] = "soltanto donne"
        doc["document_findings"][-2]["denominator_id"] = "altro_denominatore"
        self.assertEqual(territorial_signals([doc]), [])

    def test_duplicate_territory_code_invalidates_entire_comparison(self):
        doc = territorial_source()
        copied = dict(doc["document_findings"][-1])
        copied["value"] = 99.0
        doc["document_findings"].append(copied)
        self.assertEqual(territorial_signals([doc]), [])

    def test_unverified_record_does_not_count(self):
        doc = territorial_source()
        for row in doc["document_findings"][-2:]:
            row["verified"] = False
        self.assertEqual(territorial_signals([doc]), [])

    def test_research_dossier_includes_territory_story_only_if_proven(self):
        dossier = research_report([territorial_source()])
        self.assertEqual(len(dossier["territorial_signals"]), 1)
        self.assertIn("territorial_rate_comparison",
                      [r["story_type"] for r in dossier["research_stories"]])


class NarrativeTests(unittest.TestCase):
    def _fake_pdf(self, texts):
        data = b"%PDF-1.7\nsynthetic-for-unit-test-not-an-actual-pdf\n"
        pages = [types.SimpleNamespace(extract_text=lambda t=t: t)
                 for t in texts]
        class FakeDoc:
            def __init__(self): self.pages = pages
            def __enter__(self): return self
            def __exit__(self, *args): return False
        fake = types.SimpleNamespace(open=lambda _: FakeDoc())
        with patch.dict(sys.modules, {"pdfplumber": fake}):
            reading = read_pdf_publication(data, SOURCE)
        return reading

    def test_all_pages_not_only_first_four(self):
        text = "Gli arrivi in questa rilevazione sono numerosi. La fonte descrive i fenomeni turistici."
        report = self._fake_pdf([text] * 6)
        self.assertEqual(report["pdf_pages_total"], 6)
        self.assertEqual(report["pdf_pages_scanned"], 6)
        self.assertEqual(report["text_pages_scanned"], 6)
        self.assertTrue(report["complete_text_layer"])
        self.assertEqual(report["passages"][-1]["page"], 6)
        self.assertEqual(report["passages"][-1]["proof_status"],
                         "verbatim_context_not_statistical_proof")

    def test_unextractable_page_reports_incomplete_coverage(self):
        report = self._fake_pdf(["Prima pagina con contenuto testuale leggibile.",
                                 None, "Terza pagina con contenuto testuale leggibile."])
        self.assertFalse(report["complete_text_layer"])
        self.assertEqual(report["pages_without_text_layer"], [2])
        self.assertIn("pages_without_extractable_text",
                      report["coverage_warnings"])

    def test_context_lookups_do_not_mislabel_statistical_proof(self):
        report = self._fake_pdf([
            "Arrivi e presenze aumentano del 99% nel testo fittizio. "
            "La citazione e contestuale, non e una prova numerica."
        ])
        hits = match_passages(report, ["arrivi", "presenze"])
        self.assertTrue(hits)
        self.assertTrue(hits[0]["contains_numbers"])
        self.assertEqual(hits[0]["proof_status"],
                         "verbatim_context_not_statistical_proof")

    def test_research_joins_passages_only_with_matching_source_hash(self):
        doc = pair_fixture()
        reading = self._fake_pdf([
            "Arrivi e presenze sono due differenti indicatori "
            "che vengono analizzati nel report trimestrale."
        ])
        doc["document_reading"] = reading
        for f in doc["document_findings"]:
            f["source_sha256"] = reading["source_sha256"]
        dossier = research_report([doc])
        self.assertTrue(dossier["publication_coverage"][0]["full_text_layer_attached"])
        self.assertTrue(dossier["research_candidates"][0]["narrative_context"])
        self.assertTrue(dossier["research_candidates"][0]["context_is_not_numeric_proof"])
        doc["document_reading"]["source_sha256"] = "f" * 64
        blocked = research_report([doc])
        self.assertEqual(blocked["research_candidates"][0]["narrative_context"], [])
        self.assertFalse(blocked["publication_coverage"][0]["full_text_layer_attached"])

    def test_nested_workbench_report_contains_coverage(self):
        report = research_report([pair_fixture()])
        self.assertEqual(report["coverage"]["historical_comparison_stories"],
                         "no_comparable_data")
        self.assertEqual(report["coverage"]["territorial_comparison_stories"],
                         "no_comparable_data")
        self.assertEqual(len(report["publication_coverage"]), 1)


if __name__ == "__main__":
    unittest.main()
