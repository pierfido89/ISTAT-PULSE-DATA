"""Strict offline tests for the PULSE Editorial AI 2.0 paired-source pilot.

No Ollama is started in CI. Evidence was modeled after the official
ISTAT tourism Q2 2026 table: same quarter, structure, residence,
source SHA and two independently verified cells.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_pairs import (
    paired_candidates, grounded_story, paired_audit, PairOllama, main,
)
from test_pulse_editorial_ai import primary, finding


SAFE_CONTEXT = (
    "Per i clienti residenti i due indicatori procedono in direzioni "
    "opposte: calano gli arrivi mentre aumentano le presenze."
)


def pair_fixture(*, change_arrivals=-4.3, change_nights=1.7,
                 residents="residenti"):
    a = finding(12464038, change_arrivals, "Arrivi")
    n = finding(32162873, change_nights, "Presenze")
    for item, line in ((a, 14), (n, 16)):
        item["segment"]["residence"] = residents
        item["location"] = f"page:3:text:line:{line}"
    return primary(a, n)


def pair():
    pairs = paired_candidates([pair_fixture()])
    assert len(pairs) == 1
    return pairs[0]


class PairEvidenceTests(unittest.TestCase):
    def test_matches_real_residents_arrivals_and_nights(self):
        p = pair()
        self.assertEqual([x["indicator"] for x in p["evidence"]],
                         ["Arrivi", "Presenze"])
        self.assertEqual(p["population"], "residenti")
        self.assertEqual(p["evidence"][0]["change_pct"], -4.3)
        self.assertEqual(p["evidence"][1]["change_pct"], 1.7)
        self.assertEqual(p["evidence"][0]["source_sha256"],
                         p["evidence"][1]["source_sha256"])
        self.assertNotEqual(p["evidence"][0]["source_location"],
                            p["evidence"][1]["source_location"])

    def test_grounded_title_lead_are_real_comparative_news(self):
        story = grounded_story(pair())
        self.assertIn("arrivi in calo, presenze in aumento", story["headline"])
        self.assertIn("12.464.038", story["lead"])
        self.assertIn("32.162.873", story["lead"])
        self.assertIn("4,3%", story["lead"])
        self.assertIn("1,7%", story["lead"])
        self.assertIn("secondo trimestre 2025", story["lead"])
        self.assertIn("arrivi contano", story["body"].lower())

    def test_cohort_and_direction_are_consistent_in_assembled_article(self):
        p = pair()
        draft = paired_audit(p, {"context": SAFE_CONTEXT})
        self.assertEqual(draft["quality"]["status"], "review_required")
        self.assertEqual(draft["quality"]["issues"], [])
        self.assertEqual(draft["evidence_count"], 2)
        self.assertEqual(draft["insight_type"], "opposite_directions")
        self.assertEqual(draft["publication_status"], "draft_only")
        self.assertEqual(draft["editorial_format"], "paired_indicator_draft")
        self.assertIsNone(draft["pulse_score"])
        self.assertEqual(draft["patterns"], [])

    def test_without_both_indicators_no_paired_article(self):
        only_arrival = pair_fixture()
        only_arrival["document_findings"] = only_arrival["document_findings"][:1]
        self.assertEqual(paired_candidates([only_arrival]), [])

    def test_wrong_period_is_not_combined(self):
        x = pair_fixture()
        x["document_findings"][1]["reference_period"] = "2026-Q1"
        self.assertEqual(paired_candidates([x]), [])

    def test_different_residency_is_not_combined(self):
        x = pair_fixture()
        x["document_findings"][1]["segment"]["residence"] = "non residenti"
        self.assertEqual(paired_candidates([x]), [])

    def test_different_official_source_hash_not_combined(self):
        x = pair_fixture()
        x["document_findings"][1]["source_sha256"] = "f" * 64
        self.assertEqual(paired_candidates([x]), [])

    def test_same_table_location_is_not_two_independent_proofs(self):
        x = pair_fixture()
        x["document_findings"][1]["location"] = "page:3:text:line:14"
        self.assertEqual(paired_candidates([x]), [])

    def test_mismatched_units_not_combined(self):
        x = pair_fixture()
        x["document_findings"][1]["unit"] = "arrivi"
        self.assertEqual(paired_candidates([x]), [])

    def test_unverified_values_cannot_complete_pair(self):
        x = pair_fixture()
        x["document_findings"][1]["verified"] = False
        self.assertEqual(paired_candidates([x]), [])

    def test_ambiguous_duplicate_cannot_be_resolved_by_guessing(self):
        x = pair_fixture()
        conflicting_arrival = finding(12464039, -4.2, "Arrivi")
        conflicting_arrival["segment"]["residence"] = "residenti"
        conflicting_arrival["location"] = "page:3:text:line:15"
        x["document_findings"].append(conflicting_arrival)
        self.assertEqual(paired_candidates([x]), [])

    def test_comparably_sourced_positive_both(self):
        x = pair_fixture(change_arrivals=2.0, change_nights=1.7)
        p = paired_candidates([x])[0]
        title = grounded_story(p)["headline"]
        self.assertIn("arrivi e presenze in aumento", title)

    def test_separate_nonresident_pair_has_exact_population(self):
        x = pair_fixture(residents="non residenti")
        p = paired_candidates([x])[0]
        self.assertIn("non residenti", grounded_story(p)["headline"])
        self.assertNotIn("dei clienti residenti", grounded_story(p)["lead"])


class PairAuditTests(unittest.TestCase):
    def test_wrong_direction_from_model_is_rejected(self):
        draft = paired_audit(pair(), {
            "context": "Gli arrivi aumentano sensibilmente mentre le presenze "
                       "aumentano, con un confronto riferito allo stesso trimestre."
        })
        self.assertEqual(draft["quality"]["status"], "rejected")
        self.assertIn("wrong_direction_arrivi", draft["quality"]["issues"])

    def test_reversed_verb_order_is_verified_in_both_directions(self):
        correct = paired_audit(pair(), {"context": (
            "Tra i clienti residenti calano gli arrivi, mentre "
            "aumentano le presenze alberghiere nello stesso trimestre."
        )})
        self.assertNotIn("wrong_direction_arrivi",
                         correct["quality"]["issues"])
        self.assertNotIn("wrong_direction_presenze",
                         correct["quality"]["issues"])
        wrong = paired_audit(pair(), {"context": (
            "Tra i clienti residenti aumentano gli arrivi, "
            "mentre diminuiscono le presenze alberghiere nello stesso periodo."
        )})
        self.assertIn("wrong_direction_arrivi", wrong["quality"]["issues"])
        self.assertIn("wrong_direction_presenze", wrong["quality"]["issues"])

    def test_fake_previous_absolute_not_appended(self):
        p = pair()
        context = ("Gli arrivi e le presenze cambiano, mentre nel periodo "
                   "precedente gli arrivi erano 12.000.000, "
                   "secondo una stima aggiuntiva.")
        d = paired_audit(p, {"context": context})
        self.assertIn("numbers_in_generated_context", d["quality"]["issues"])
        self.assertNotIn("12.000.000", d["body"])
        self.assertIn("12.000.000", d["model_proposed_context"])

    def test_unverified_longer_stays_rejected_despite_two_metrics(self):
        d = paired_audit(pair(), {"context": (
            "I due indicatori si muovono in direzioni opposte, "
            "suggerendo una permanenza media più lunga per i residenti."
        )})
        self.assertIn("unsupported_average_stay", d["quality"]["issues"])

    def test_unsupported_trend_and_significance_rejected(self):
        d = paired_audit(pair(), {"context": (
            "La tendenza positiva si conferma nonostante il calo, "
            "con una variazione statisticamente significativa."
        )})
        self.assertIn("unverified_multiperiod_trend", d["quality"]["issues"])
        self.assertIn("unverified_statistical_significance", d["quality"]["issues"])

    def test_mistaken_quarter_duration_rejected(self):
        d = paired_audit(pair(), {"context": (
            "Le presenze aumentano a fronte di arrivi in calo: "
            "il confronto copre il trimestre di due mesi."
        )})
        self.assertIn("wrong_quarter_month_count", d["quality"]["issues"])

    def test_nonresident_vs_resident_misattribution_rejected(self):
        x = pair_fixture(residents="non residenti")
        p = paired_candidates([x])[0]
        d = paired_audit(p, {"context": (
            "I clienti residenti fanno registrare arrivi inferiori, "
            "mentre le presenze crescono nel trimestre considerato."
        )})
        self.assertIn("unsourced_population_residents", d["quality"]["issues"])

    def test_missing_model_output_is_rejected_but_safe_lead_survives(self):
        d = paired_audit(pair(), {})
        self.assertEqual(d["quality"]["status"], "rejected")
        self.assertIn("12.464.038", d["lead"])
        self.assertEqual(d["publication_status"], "draft_only")

    def test_no_cloud_or_live_data_implicit_in_output(self):
        d = paired_audit(pair(), {"context": SAFE_CONTEXT})
        self.assertEqual(d["generator"]["engine"], "ollama_local")
        self.assertEqual(d["generator"]["zero_paid_api_calls"], True)
        self.assertEqual(d["publication_status"], "draft_only")


class PairCLITests(unittest.TestCase):
    def test_inspect_needs_no_ollama_and_never_writes(self):
        with tempfile.TemporaryDirectory() as t:
            source = Path(t) / "input.json"
            source.write_text(json.dumps({"articles": [pair_fixture()]}))
            with patch.object(PairOllama, "check") as check:
                self.assertEqual(main(["--input", str(source), "--inspect"]), 0)
                check.assert_not_called()

    def test_safe_local_drafts_and_input_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            source = Path(t) / "input.json"
            dest = Path(t) / "paired_drafts.json"
            original = {"articles": [pair_fixture()]}
            source.write_text(json.dumps(original))
            with patch.object(PairOllama, "check", return_value=True), \
                 patch.object(PairOllama, "generate",
                              return_value={"context": SAFE_CONTEXT}):
                self.assertEqual(main([
                    "--input", str(source), "--output", str(dest), "--limit", "1"
                ]), 0)
            self.assertEqual(json.loads(source.read_text()), original)
            out = json.loads(dest.read_text())
            self.assertEqual(out["schema_version"], "pulse-editorial-paired-2.0")
            self.assertEqual(len(out["drafts"]), 1)
            self.assertEqual(out["drafts"][0]["quality"]["status"],
                             "review_required")

    def test_no_model_no_file(self):
        with tempfile.TemporaryDirectory() as t:
            source = Path(t) / "input.json"
            output = Path(t) / "paired.json"
            source.write_text(json.dumps({"articles": [pair_fixture()]}))
            with patch.object(PairOllama, "check", return_value=False):
                self.assertEqual(main([
                    "--input", str(source), "--output", str(output)
                ]), 2)
            self.assertFalse(output.exists())

    def test_refuses_live_filename(self):
        with tempfile.TemporaryDirectory() as t:
            source = Path(t) / "input.json"
            source.write_text(json.dumps({"articles": [pair_fixture()]}))
            with self.assertRaises(SystemExit):
                main(["--input", str(source),
                      "--output", str(Path(t) / "articles.json")])


if __name__ == "__main__":
    unittest.main()
