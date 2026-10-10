"""PULSE Editorial 2.1 — true added value, not made-up AI text.

The official ISTAT methodology defines average stay as
nights (presenze) divided by arrivals for the same scope/period.
All tests run offline with no model or API call.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_derived import derive_average_stay
from scripts.pulse_editorial_pairs import (
    PairOllama, grounded_story, paired_audit,
)
from scripts.pulse_editorial_review import main, recheck
from test_pulse_editorial_pairs import pair, pair_fixture, SAFE_CONTEXT


REAL_QWEN_CONTEXT = (
    "I arrivi diminuiscono mentre le presenze aumentano, "
    "indicando un movimento in direzioni opposte tra i due indicatori."
)


class DerivedAverageStayTests(unittest.TestCase):
    def test_real_istat_ratio_is_258_and_rounding_proves_increase(self):
        p = pair()
        result = derive_average_stay(*p["evidence"])
        self.assertIsNotNone(result)
        self.assertEqual(result["value_nights_per_arrival"], "2,58")
        self.assertEqual(result["comparison_direction_rounded_yoy"], "increased")
        self.assertEqual(result["origin"],
                         "independent_PULSE_calculation_from_ISTAT")
        self.assertEqual(result["formula"],
                         "official_presenze_total / official_arrivi_total")
        self.assertEqual(len(result["source_locations"]), 2)
        self.assertNotIn("previous_total", result)

    def test_grounded_text_provides_verifiable_calculation(self):
        story = grounded_story(pair())
        self.assertIn("2,58 notti per arrivo", story["body"])
        self.assertIn("elaborazione PULSE su dati ISTAT", story["body"])
        self.assertIn("questo rapporto è aumentato", story["body"])
        self.assertNotIn("perché", story["body"])
        self.assertNotIn("31.738.000", story["body"])
        self.assertIsNotNone(story["calculated_metric"])

    def test_strictly_different_sources_or_scopes_do_not_derive(self):
        original = pair()
        a, n = original["evidence"]
        for key, value in (
            ("source_sha256", "f" * 64),
            ("source_url", "https://example.com/not_the_source"),
            ("period", "2026-Q1"),
            ("segment", "Esercizi alberghieri · non residenti"),
            ("unit", "arrivi"),
        ):
            changed = dict(n, **{key: value})
            self.assertIsNone(derive_average_stay(a, changed), key)

    def test_forged_unverified_or_missing_provenance_fails(self):
        a, n = pair()["evidence"]
        for key, value in (
            ("proof_type", "unverified"),
            ("source_location", None),
        ):
            self.assertIsNone(derive_average_stay(a, dict(n, **{key: value})))
        self.assertIsNone(derive_average_stay(a, dict(n, source_location=a["source_location"])))

    def test_invalid_counts_cannot_produce_metric(self):
        a, n = pair()["evidence"]
        for val in (0, -1, 0.6, float("nan")):
            self.assertIsNone(derive_average_stay(dict(a, value=val), n))
        self.assertIsNone(derive_average_stay(a, dict(n, value=-1)))

    def test_rate_comparison_is_only_reported_if_rounding_proves_it(self):
        a, n = pair()["evidence"]
        uncertain = derive_average_stay(
            dict(a, change_pct=0.0), dict(n, change_pct=0.0)
        )
        self.assertEqual(uncertain["comparison_direction_rounded_yoy"],
                         "not_determined")
        decline = derive_average_stay(
            dict(a, change_pct=2.3), dict(n, change_pct=-0.7)
        )
        self.assertEqual(decline["comparison_direction_rounded_yoy"],
                         "decreased")
        out = grounded_story({
            **pair(),
            "evidence": [dict(a, change_pct=0.0), dict(n, change_pct=0.0)],
        })
        self.assertIn("non consentono di determinare", out["body"])


class RealQwenEditorialTests(unittest.TestCase):
    def test_actual_qwen_context_is_not_published(self):
        draft = paired_audit(pair(), {"context": REAL_QWEN_CONTEXT})
        self.assertIn("ungrammatical_indicator_article", draft["quality"]["issues"])
        self.assertEqual(draft["quality"]["status"], "rejected")
        self.assertFalse(draft["quality"]["validated_generated_context"])
        self.assertFalse(draft["quality"]["generated_context_included"])
        self.assertEqual(draft["quality"]["safe_core_status"], "review_required")
        self.assertEqual(draft["quality"]["model_context_status"], "rejected")
        self.assertIn("2,58 notti per arrivo", draft["body"])
        self.assertNotIn("I arrivi diminuiscono", draft["body"])
        self.assertEqual(draft["model_proposed_context"], REAL_QWEN_CONTEXT)

    def test_no_extra_editorial_value_means_ai_text_is_withheld(self):
        draft = paired_audit(pair(), {"context": SAFE_CONTEXT})
        self.assertEqual(draft["quality"]["status"], "review_required")
        self.assertIn("repeats_headline_without_new_evidence",
                      draft["quality"]["editorial_warnings"])
        self.assertFalse(draft["quality"]["generated_context_included"])
        self.assertEqual(draft["quality"]["model_context_status"],
                         "omitted_as_redundant")
        self.assertIn("2,58 notti per arrivo", draft["body"])
        self.assertNotIn("Per i clienti residenti i due indicatori", draft["body"])


class OfflineReviewTests(unittest.TestCase):
    def _source_and_previous(self, directory: Path):
        from scripts.pulse_editorial_pairs import paired_candidates
        workbench = directory / "turismo.json"
        previous = directory / "bozza.json"
        source_obj = {"articles": [pair_fixture()]}
        workbench.write_text(json.dumps(source_obj), encoding="utf-8")
        p = paired_candidates(source_obj["articles"])[0]
        original = paired_audit(p, {"context": REAL_QWEN_CONTEXT})
        previous.write_text(json.dumps({
            "schema_version": "pulse-editorial-paired-2.0",
            "mode": "local_drafts_only", "model": "qwen3:4b-instruct",
            "drafts": [original],
        }), encoding="utf-8")
        return workbench, previous

    def test_reuse_existing_output_no_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            inp, prev = self._source_and_previous(d)
            target = d / "rivisto.json"
            original_bytes = inp.read_bytes(), prev.read_bytes()
            with patch.object(PairOllama, "check", side_effect=AssertionError("AI forbidden")), \
                 patch.object(PairOllama, "generate", side_effect=AssertionError("AI forbidden")):
                status = main(["--input", str(inp),
                               "--previous", str(prev),
                               "--output", str(target)])
            self.assertEqual(status, 0)
            self.assertEqual((inp.read_bytes(), prev.read_bytes()), original_bytes)
            result = json.loads(target.read_text())
            self.assertEqual(result["schema_version"],
                             "pulse-editorial-paired-review-2.1")
            self.assertEqual(result["reviewed_count"], 1)
            self.assertIn("2,58", result["drafts"][0]["body"])
            self.assertEqual(result["drafts"][0]["publication_status"], "draft_only")

    def test_tampered_old_draft_evidence_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, prev = self._source_and_previous(Path(folder))
            obj = json.loads(prev.read_text())
            obj["drafts"][0]["evidence"][0]["value"] = 999
            prev.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "does not match"):
                recheck(inp, prev)

    def test_refuses_overwrite_of_old_or_production_file(self):
        with tempfile.TemporaryDirectory() as folder:
            inp, prev = self._source_and_previous(Path(folder))
            with self.assertRaises(SystemExit):
                main(["--input", str(inp), "--previous", str(prev),
                      "--output", str(prev)])
            with self.assertRaises(SystemExit):
                main(["--input", str(inp), "--previous", str(prev),
                      "--output", str(Path(folder) / "articles.json")])


if __name__ == "__main__":
    unittest.main()
