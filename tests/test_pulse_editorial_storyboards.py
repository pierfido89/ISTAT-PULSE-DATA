"""First six-domain editorial pipeline tests: no model, network or publishing."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_storyboards import (
    _article, check_editorial_story, create_editorial_stories,
    editorial_cards, LocalEditorialPlanner, main,
)
from scripts.pulse_research_engine import research_report
from scripts.pulse_research_new_domains import (
    SOURCES, demography_page, education_page, environment_page,
)
from test_pulse_editorial_pairs import pair_fixture
from test_pulse_research_labor import fixture as labor_fixture
from test_pulse_research_prices import prices_fixture
from test_pulse_research_new_domains import (
    DEMOGRAPHY, EDUCATION, ENVIRONMENT, SHA, source_doc,
)

def six_articles():
    return [
        pair_fixture(),
        labor_fixture(),
        prices_fixture(),
        source_doc("popolazione", demography_page(
            DEMOGRAPHY, SOURCES["popolazione"], SHA, 2)),
        source_doc("istruzione", education_page(
            EDUCATION, SOURCES["istruzione"], SHA, 2), True),
        source_doc("ambiente", environment_page(
            ENVIRONMENT, SOURCES["ambiente"], SHA, 2)),
    ]


class SixDomainEditorialTests(unittest.TestCase):
    def test_one_draft_per_domain_and_all_sources_remain_traced(self):
        data = six_articles()
        result = create_editorial_stories(data)
        self.assertEqual(result["schema_version"], "pulse-editorial-storyboards-3.4")
        self.assertEqual(result["source_documents"], 6)
        self.assertEqual(result["verified_research_options"], 16)
        self.assertEqual(len(result["drafts"]), 6)
        self.assertEqual(len({d["domain"] for d in result["drafts"]}), 6)
        self.assertEqual(len({d["source_url"] for d in result["drafts"]}), 6)
        for draft in result["drafts"]:
            self.assertEqual(draft["publication_status"], "draft_only")
            self.assertIsNone(draft["pulse_score"])
            self.assertTrue(draft["requires_human_review"])
            self.assertEqual(draft["quality"]["status"], "review_required")
            self.assertTrue(draft["quality"]["exact_evidence_match"])
            self.assertTrue(draft["evidence"]["source_locations"])
            self.assertTrue(draft["evidence"]["source_hashes"])
            self.assertFalse(check_editorial_story(draft, research_report(data)))

    def test_labor_units_and_no_mix_of_unemployment_rates(self):
        result = create_editorial_stories(six_articles())
        labor = next(d for d in result["drafts"]
                     if d["domain"] == "labor_categories_yoy_evidence")
        self.assertIn("24.352.000", labor["lead"])
        self.assertIn("1.591.000", labor["lead"])
        self.assertIn("ciascun indicatore", labor["body"])

    def test_education_percentage_points_not_relative_percent(self):
        result = create_editorial_stories(six_articles())
        education = next(d for d in result["drafts"]
                         if d["domain"] == "historical_annual_comparison")
        self.assertIn("punti percentuali", education["lead"])
        self.assertNotIn("% punti percentuali", education["lead"])
        self.assertIn("2022", education["lead"])
        self.assertIn("2024", education["lead"])

    def test_demography_provisional_rounding_and_prices_distinct(self):
        result = create_editorial_stories(six_articles())
        population = next(d for d in result["drafts"] if d["domain"] ==
                          "provisional_population_balance_rounded_thousands")
        self.assertIn("355 mila", population["lead"])
        self.assertIn("652 mila", population["lead"])
        self.assertIn("provvisorie", population["body"])
        prices = next(d for d in result["drafts"] if d["domain"] ==
                      "different_price_baskets_yoy_rates")
        for term in ("NIC", "IPCA", "FOI"):
            self.assertIn(term, prices["lead"])
        self.assertIn("panieri", prices["body"])

    def test_territorial_numbers_and_dimension_explanation(self):
        result = create_editorial_stories(six_articles())
        territory = next(d for d in result["drafts"]
                         if d["domain"] == "territorial_rate_comparison")
        self.assertIn("punti percentuali", territory["lead"])
        self.assertIn("stesso indicatore", territory["body"])

    def test_source_lock_rejects_any_tampered_fact(self):
        data = six_articles()
        report = research_report(data)
        stories = create_editorial_stories(data)["drafts"]
        for original in stories:
            for key, changed in (
                ("lead", original["lead"] + " Record assoluto inventato."),
                ("source_url", "https://untrusted.invalid/fake.pdf"),
                ("body", original["body"] + " Affermazione causale inventata."),
            ):
                tampered = copy.deepcopy(original)
                tampered[key] = changed
                self.assertTrue(check_editorial_story(tampered, report),
                                (original["domain"], key))

    def test_local_model_can_choose_verified_story_and_method_angle(self):
        data = six_articles()
        cards = editorial_cards(research_report(data))
        chosen = next(x for x in cards if x["domain"] ==
                      "historical_annual_comparison")
        result = create_editorial_stories(
            data, {"story_id": chosen["story_id"], "angle_id": "method"},
        )
        self.assertEqual(result["selection"]["status"],
                         "local_model_selected_verified_angle")
        self.assertEqual(result["drafts"][0]["angle_id"], "method")
        self.assertEqual(result["drafts"][0]["domain"],
                         "historical_annual_comparison")
        self.assertIn("punti percentuali", result["drafts"][0]["body"])

    def test_model_cannot_provide_unverified_prose_or_numbers(self):
        data = six_articles()
        suggested = {
            "story_id": editorial_cards(research_report(data))[0]["story_id"],
            "angle_id": "main",
            "headline": "ISTAT CONFERMA DISCOVERY 999.999",
        }
        result = create_editorial_stories(data, suggested)
        self.assertEqual(result["selection"]["status"],
                         "unsupported_model_selection_discarded")
        self.assertNotIn("999.999", result["drafts"][0]["headline"])

    def test_missing_domain_is_not_fabricated(self):
        result = create_editorial_stories(six_articles()[:1])
        self.assertEqual(result["source_documents"], 1)
        self.assertEqual(len(result["drafts"]), 1)
        self.assertEqual(result["drafts"][0]["domain"], "paired_indicators")

    def test_cli_offline_and_ollama_mock_with_six_sources(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            docs = []
            originals = six_articles()
            for i, article in enumerate(originals):
                path = folder / f"source_{i}.json"
                path.write_text(json.dumps({"articles": [article]}), encoding="utf-8")
                docs.append(path)
            output = folder / "editorial.json"
            args = ["--input", str(docs[0]), "--additional-input",
                    *(str(d) for d in docs[1:]), "--output", str(output)]
            with patch.object(LocalEditorialPlanner, "check",
                              side_effect=AssertionError("Cannot call AI")):
                self.assertEqual(main(args), 0)
            received = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(received["drafts"]), 6)
            self.assertEqual([json.loads(d.read_text())["articles"][0]
                              for d in docs], originals)
            with patch.object(LocalEditorialPlanner, "check", return_value=True), \
                 patch.object(LocalEditorialPlanner, "choose", return_value={
                     "story_id": "FAKE-INVENTED", "angle_id": "method"
                 }):
                self.assertEqual(main(args + ["--use-local-ai"]), 0)
            received = json.loads(output.read_text())
            self.assertEqual(received["selection"]["status"],
                             "unsupported_model_selection_discarded")

    def test_cli_rejects_overwrite_and_missing_model(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "a.json"
            f.write_text(json.dumps({"articles": six_articles()[:1]}))
            for dst in (f, Path(td) / "articles.json"):
                with self.assertRaises(SystemExit):
                    main(["--input", str(f), "--output", str(dst)])
            out = Path(td) / "unwritten.json"
            with patch.object(LocalEditorialPlanner, "check", return_value=False):
                self.assertEqual(main(["--input", str(f),
                                       "--output", str(out), "--use-local-ai"]), 2)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
