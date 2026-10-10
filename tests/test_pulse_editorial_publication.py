"""PULSE Editorial Intelligence phase-2 acceptance: 6 domains, no Ollama needed.

Tests use synthetic source-shaped evidence; live CI separately downloads
six genuine ISTAT PDFs and runs the same publication pipeline.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_publication import (
    write_editorial_issue, independent_check, quality_report,
    LocalNarrativeDirector, main,
)
from scripts.pulse_research_engine import research_report
from test_pulse_editorial_storyboards import six_articles


class FullEditorialTests(unittest.TestCase):
    def test_six_valuable_multisection_drafts_one_per_source(self):
        data = six_articles()
        issue = write_editorial_issue(data)
        self.assertEqual(issue["schema_version"],
                         "pulse-editorial-intelligence-3.5")
        self.assertEqual(issue["source_documents"], 6)
        self.assertEqual(len(issue["drafts"]), 6)
        self.assertEqual(len({x["domain"] for x in issue["drafts"]}), 6)
        self.assertEqual(len({x["source_url"] for x in issue["drafts"]}), 6)
        self.assertTrue(all(
            x["quality"]["status"] == "review_required" for x in issue["drafts"]
        ))
        for article in issue["drafts"]:
            self.assertEqual(len(article["paragraphs"]), 4)
            self.assertEqual(article["quality"]["paragraph_count"], 4)
            self.assertGreaterEqual(article["quality"]["word_count"], 95)
            self.assertLessEqual(article["quality"]["word_count"], 270)
            self.assertEqual(article["publication_status"], "draft_only")
            self.assertTrue(article["requires_human_review"])
            self.assertFalse(independent_check(article, research_report(data)))
            self.assertEqual(article["evidence"]["source_url"],
                             article["source_url"])
        self.assertFalse(issue["publication"])

    def test_historical_middle_year_is_source_grounded(self):
        issue = write_editorial_issue(six_articles())
        edu = next(x for x in issue["drafts"]
                   if x["domain"] == "historical_annual_comparison")
        self.assertIn("2023", edu["body"])
        self.assertIn("punti percentuali", edu["body"])

    def test_no_phantom_exact_demographic_numbers(self):
        issue = write_editorial_issue(six_articles())
        pop = next(x for x in issue["drafts"] if x["domain"] ==
                   "provisional_population_balance_rounded_thousands")
        self.assertIn("355 mila", pop["lead"])
        self.assertIn("297 mila", pop["body"])
        self.assertIn("arrotond", pop["body"])
        self.assertNotIn("355.000 persone esatte", pop["body"])

    def test_safe_words_for_statistical_categories(self):
        issue = write_editorial_issue(six_articles())
        labor = next(x for x in issue["drafts"]
                     if x["domain"] == "labor_categories_yoy_evidence")
        self.assertIn("24.352.000", labor["lead"])
        self.assertIn("inattivi", labor["body"])
        prices = next(x for x in issue["drafts"] if x["domain"] ==
                      "different_price_baskets_yoy_rates")
        self.assertIn("base 2025=100", prices["body"])
        self.assertIn("panieri", prices["body"])

    def test_selection_promotes_only_preapproved_settings(self):
        data = six_articles()
        offline = write_editorial_issue(data)
        allowed = offline["drafts"][0]["id"]
        result = write_editorial_issue(data, {
            "story_id": allowed, "voice": "divulgazione",
            "focus": "metodo", "order": "spiegazione",
        })
        self.assertEqual(result["model_selection"]["status"],
                         "verified_local_editorial_plan_accepted")
        self.assertIn("La notizia sta nel contrasto", result["drafts"][0]["body"])
        self.assertEqual(result["drafts"][0]["quality"]["status"],
                         "review_required")

    def test_model_attempts_to_inject_claim_are_discarded(self):
        data = six_articles()
        result = write_editorial_issue(data, {
            "story_id": "FAKE-100-BILLION", "voice": "notizia",
            "focus": "fenomeno", "order": "comparazione",
            "headline": "ISTAT annuncia record storico 99999999",
        })
        self.assertEqual(result["model_selection"]["status"],
                         "invalid_model_plan_rejected")
        self.assertNotIn("99999999", json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["drafts"][0]["quality"]["status"],
                         "review_required")

    def test_independent_checker_rejects_tampering_on_all_fields(self):
        data = six_articles()
        research = research_report(data)
        for original in write_editorial_issue(data)["drafts"]:
            for key, forged in (
                ("headline", original["headline"]+" INVENTATO"),
                ("body", original["body"]+" 99,9%"),
                ("lead", original["lead"]+" record assoluto"),
                ("source_url", "https://unknown.invalid"),
            ):
                modified = deepcopy(original)
                modified[key] = forged
                self.assertTrue(independent_check(modified, research),
                                (original["domain"], key))

    def test_no_duplicate_or_extra_paragraphs_accepted(self):
        data = six_articles()
        draft = write_editorial_issue(data)["drafts"][0]
        duplicate = deepcopy(draft)
        duplicate["paragraphs"][1]["text"] = duplicate["paragraphs"][0]["text"]
        duplicate["body"] = "\n\n".join(x["text"] for x in duplicate["paragraphs"])
        self.assertIn("duplicate_paragraph",
                      quality_report(duplicate)["heuristic_issues"])
        self.assertTrue(independent_check(duplicate, research_report(data)))

    def test_cli_offline_and_live_qwen_mock(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for i, source in enumerate(six_articles()):
                path = Path(folder) / f"in_{i}.json"
                path.write_text(json.dumps({"articles": [source]}))
                paths.append(path)
            outfile = Path(folder) / "output.json"
            args = (["--input", str(paths[0]), "--additional-input"] +
                    [str(p) for p in paths[1:]] +
                    ["--output", str(outfile), "--limit", "6"])
            with patch.object(LocalNarrativeDirector, "check",
                              side_effect=AssertionError("Should not call Ollama")):
                self.assertEqual(main(args), 0)
            result = json.loads(outfile.read_text())
            self.assertEqual(len(result["drafts"]), 6)
            with patch.object(LocalNarrativeDirector, "check", return_value=True), \
                 patch.object(LocalNarrativeDirector, "propose", return_value={
                     "story_id": result["drafts"][1]["id"],
                     "voice": "analisi", "focus": "confronto",
                     "order": "comparazione",
                 }):
                self.assertEqual(main(args + ["--use-local-ai"]), 0)
            result = json.loads(outfile.read_text())
            self.assertEqual(result["drafts"][0]["id"],
                             result["model_selection"].get("story_id",
                                                           result["drafts"][0]["id"]))
            self.assertEqual(result["drafts"][0]["quality"]["status"],
                             "review_required")

    def test_model_not_available_fails_cleanly_without_file(self):
        with tempfile.TemporaryDirectory() as folder:
            input_ = Path(folder) / "in.json"
            output = Path(folder) / "absent.json"
            input_.write_text(json.dumps({"articles": [six_articles()[0]]}))
            with patch.object(LocalNarrativeDirector, "check", return_value=False):
                self.assertEqual(main(["--input", str(input_),
                                       "--output", str(output),
                                       "--use-local-ai"]), 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
