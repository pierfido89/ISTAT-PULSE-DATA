"""Research Engine 3.0 offline evidence-selection tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_research_engine import research_report, angle_options, main
from test_pulse_editorial_pairs import pair_fixture, pair
from scripts.pulse_editorial_pairs import paired_candidates


class ResearchEngineTests(unittest.TestCase):
    def test_source_facts_are_read_across_document_not_one_indicator(self):
        source = pair_fixture()
        out = research_report([source])
        self.assertEqual(out["source_document_count"], 1)
        self.assertEqual(out["extracted_findings_count"], 2)
        self.assertEqual(out["verified_single_findings_count"], 2)
        self.assertEqual(out["verified_paired_candidate_count"], 1)
        self.assertEqual(len(out["research_candidates"]), 1)
        self.assertEqual(out["research_candidates"][0]["publication_status"],
                         "research_only")
        self.assertIsNone(out["research_candidates"][0]["pulse_score"])

    def test_opposite_changes_and_method_based_ratio_both_eligible(self):
        out = research_report([pair_fixture()])
        candidate = out["research_candidates"][0]
        names = {x["id"] for x in candidate["angles"]}
        self.assertEqual(names, {"opposite_directions", "average_stay_calculated"})
        metric = next(x["derived_metric"] for x in candidate["angles"]
                      if x["id"] == "average_stay_calculated")
        self.assertEqual(metric["value_nights_per_arrival"], "2,58")
        self.assertIn("two_official_yoy_rates_with_opposite_signs",
                      candidate["ranking"]["ranking_reasons"])
        self.assertTrue(candidate["ranking"]["not_pulse_score"])
        self.assertTrue(candidate["ranking"]["not_statistical_significance"])

    def test_no_historical_or_territorial_evidence_is_explicit(self):
        out = research_report([pair_fixture()])
        self.assertFalse(out["coverage"]["historical_series_supplied"])
        self.assertFalse(out["coverage"]["territorial_dimensions_supplied"])
        self.assertEqual(out["coverage"]["historical_comparison_stories"],
                         "not_implemented")
        self.assertIn("not_entire_pdf_prose", out["coverage"]["scope"])
        self.assertEqual(out["coverage"]["missing_evidence_policy"],
                         "withhold_inference")

    def test_pair_scoring_is_stable_on_input_order(self):
        resident = pair_fixture()
        nonresident = pair_fixture(residents="non residenti")
        nonresident["id"] = "TEST-NONRESIDENT"
        left = research_report([resident, nonresident])
        right = research_report([nonresident, resident])
        self.assertEqual(
            [(r["pair_id"], r["ranking"]["priority_points"])
             for r in left["research_candidates"]],
            [(r["pair_id"], r["ranking"]["priority_points"])
             for r in right["research_candidates"]],
        )

    def test_same_trend_is_not_called_opposite(self):
        source = pair_fixture(change_arrivals=1.8, change_nights=3.0)
        card = research_report([source])["research_candidates"][0]
        self.assertNotIn("opposite_directions", [x["id"] for x in card["angles"]])
        self.assertIn("parallel_changes", [x["id"] for x in card["angles"]])

    def test_source_incoherence_blocks_angle(self):
        bad = pair_fixture()
        bad["document_findings"][1]["source_sha256"] = "f" * 64
        out = research_report([bad])
        self.assertEqual(out["verified_paired_candidate_count"], 0)
        self.assertEqual(out["research_candidates"], [])

    def test_invalid_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            research_report([pair_fixture()], limit=0)

    def test_inspect_does_not_require_ollama_or_write(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "workbench.json"
            source.write_text(json.dumps({"articles": [pair_fixture()]}))
            with patch("scripts.pulse_research_engine.paired_candidates",
                       wraps=paired_candidates):
                self.assertEqual(main(["--input", str(source), "--inspect"]), 0)
            self.assertFalse((Path(folder) / "research.json").exists())

    def test_research_report_written_without_live_feed_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / "in.json"
            out = Path(folder) / "research.json"
            doc = {"articles": [pair_fixture()]}
            inp.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(main(["--input", str(inp),
                                   "--output", str(out)]), 0)
            self.assertEqual(json.loads(inp.read_text()), doc)
            report = json.loads(out.read_text())
            self.assertEqual(report["schema_version"], "pulse-research-engine-3.0")
            self.assertEqual(report["mode"], "offline_research_only")
            with self.assertRaises(SystemExit):
                main(["--input", str(inp),
                      "--output", str(Path(folder) / "articles.json")])


if __name__ == "__main__":
    unittest.main()
