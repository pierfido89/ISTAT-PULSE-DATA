"""PULSE Editorial Intelligence 3.0: Qwen4B only picks audited story IDs.

No model is executed in tests; facts and generated copy remain deterministic.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_intelligence import (
    LocalAnglePlanner, draft_from_research, select_angle,
    check_locked_story, main,
)
from scripts.pulse_research_engine import research_report
from scripts.pulse_editorial_pairs import paired_candidates
from test_pulse_editorial_pairs import pair_fixture


def articles():
    return [pair_fixture()]


class EditorialIntelligenceTests(unittest.TestCase):
    def test_evidence_first_default_angle_and_draft_only(self):
        doc = draft_from_research(articles())
        self.assertEqual(doc["schema_version"],
                         "pulse-editorial-intelligence-3.0")
        self.assertEqual(doc["mode"], "offline_selection")
        d = doc["drafts"][0]
        self.assertEqual(d["editorial_angle_id"], "opposite_directions")
        self.assertEqual(d["quality"]["status"], "review_required")
        self.assertEqual(d["publication_status"], "draft_only")
        self.assertTrue(d["generator"]["no_free_form_factual_prose"])
        self.assertEqual(d["generator"]["model"], None)
        self.assertIn("12.464.038", d["lead"])
        self.assertIn("32.162.873", d["lead"])
        self.assertIn("2,58", d["body"])
        self.assertIsNone(d["pulse_score"])

    def test_qwen_4b_can_select_verified_derived_angle(self):
        base = draft_from_research(articles())
        id_ = base["drafts"][0]["id"]
        doc = draft_from_research(articles(), {
            "pair_id": id_, "angle_id": "average_stay_calculated"
        })
        d = doc["drafts"][0]
        self.assertEqual(d["editorial_selection"]["status"],
                         "valid_local_ai_angle_selection_not_fact_claim")
        self.assertEqual(d["quality"]["status"], "review_required")
        self.assertIn("permanenza media di 2,58", d["headline"])
        self.assertEqual(d["calculated_metrics"][0]["origin"],
                         "independent_PULSE_calculation_from_ISTAT")
        self.assertNotIn("cause specifiche", d["lead"])

    def test_malicious_proposed_text_is_never_promoted(self):
        p = research_report(articles())
        ident = p["research_candidates"][0]["pair_id"]
        suggestion = {
            "pair_id": ident, "angle_id": "average_stay_calculated",
            "headline": "RECORD STORICO TOTALE 999.999.999",
        }
        doc = draft_from_research(articles(), suggestion)
        d = doc["drafts"][0]
        self.assertEqual(d["editorial_selection"]["status"],
                         "ai_suggestion_rejected_offline_fallback")
        self.assertIn("selection_outside_verified_evidence_or_wrong_schema",
                      d["editorial_selection"]["issues"])
        self.assertNotIn("RECORD STORICO", d["headline"])
        self.assertEqual(d["quality"]["status"], "review_required")

    def test_unknown_pair_or_angle_rejected_and_fallback(self):
        p = research_report(articles())
        valid = p["research_candidates"][0]["pair_id"]
        for proposed in (
            {"pair_id": "INVENTED", "angle_id": "opposite_directions"},
            {"pair_id": valid, "angle_id": "record_storico"},
            {"pair_id": 42, "angle_id": "opposite_directions"},
            ["bad"],
        ):
            d = draft_from_research(articles(), proposed)["drafts"][0]
            self.assertEqual(d["editorial_selection"]["status"],
                             "ai_suggestion_rejected_offline_fallback")
            self.assertEqual(d["quality"]["status"], "review_required")

    def test_fact_checker_rejects_tampered_number(self):
        doc = draft_from_research(articles())
        d = doc["drafts"][0]
        pair = paired_candidates(articles())[0]
        d["lead"] = d["lead"].replace("12.464.038", "12.464.039")
        self.assertIn("lead_mismatch_against_verifiable_template",
                      check_locked_story(d, pair, d["editorial_angle_id"]))

    def test_fact_checker_rejects_fake_derived_metric(self):
        doc = draft_from_research(articles())
        d = doc["drafts"][0]
        pair = paired_candidates(articles())[0]
        d["calculated_metrics"][0]["value_nights_per_arrival"] = "6,50"
        self.assertIn("derived_metric_witness_mismatch",
                      check_locked_story(d, pair, d["editorial_angle_id"]))

    def test_fact_checker_rejects_wrong_population_title(self):
        doc = draft_from_research(articles())
        d = doc["drafts"][0]
        pair = paired_candidates(articles())[0]
        d["headline"] = d["headline"].replace("residenti", "non residenti")
        self.assertIn("headline_mismatch_against_verifiable_template",
                      check_locked_story(d, pair, d["editorial_angle_id"]))

    def test_ai_not_needed_for_offline_article(self):
        with tempfile.TemporaryDirectory() as dir_:
            source = Path(dir_) / "workbench.json"
            target = Path(dir_) / "draft.json"
            doc = {"articles": articles()}
            source.write_text(json.dumps(doc))
            with patch.object(LocalAnglePlanner, "choose",
                              side_effect=AssertionError("No Ollama permitted")), \
                 patch.object(LocalAnglePlanner, "check",
                              side_effect=AssertionError("No Ollama permitted")):
                result = main(["--input", str(source), "--output", str(target)])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(source.read_text()), doc)
            self.assertEqual(json.loads(target.read_text())["drafts"][0]
                             ["quality"]["status"], "review_required")

    def test_local_ai_receives_only_verified_angle_choices(self):
        with tempfile.TemporaryDirectory() as dir_:
            source = Path(dir_) / "workbench.json"
            target = Path(dir_) / "draft.json"
            source.write_text(json.dumps({"articles": articles()}))
            with patch.object(LocalAnglePlanner, "check", return_value=True), \
                 patch.object(LocalAnglePlanner, "choose",
                              return_value={"pair_id": "fake", "angle_id": "record"}):
                code = main(["--input", str(source), "--output", str(target),
                             "--use-local-ai"])
            self.assertEqual(code, 0)
            d = json.loads(target.read_text())["drafts"][0]
            self.assertEqual(d["editorial_selection"]["status"],
                             "ai_suggestion_rejected_offline_fallback")
            self.assertEqual(d["publication_status"], "draft_only")

    def test_local_model_absent_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as dir_:
            inp = Path(dir_) / "input.json"
            out = Path(dir_) / "not_created.json"
            inp.write_text(json.dumps({"articles": articles()}))
            with patch.object(LocalAnglePlanner, "check", return_value=False):
                code = main(["--input", str(inp), "--output", str(out),
                             "--use-local-ai"])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())

    def test_forbid_overwrite(self):
        with tempfile.TemporaryDirectory() as dir_:
            inp = Path(dir_) / "input.json"
            inp.write_text(json.dumps({"articles": articles()}))
            with self.assertRaises(SystemExit):
                main(["--input", str(inp), "--output", str(inp)])
            with self.assertRaises(SystemExit):
                main(["--input", str(inp),
                      "--output", str(Path(dir_) / "articles.json")])


if __name__ == "__main__":
    unittest.main()
