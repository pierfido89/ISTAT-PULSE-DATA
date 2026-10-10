"""Qwen3:4b-instruct genuinely writes a quarantine candidate; never auto-promote."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_local_writer import (
    ARTICLE_SCHEMA, assess_model_copy, LocalRewriteCandidate, make_rewrite_lab, main,
)
from scripts.pulse_editorial_publication import write_editorial_issue
from test_pulse_editorial_storyboards import six_articles


def fixture():
    return write_editorial_issue(six_articles())


def valid_sample(article):
    return {
        "headline": article["headline"],
        "paragraphs": [p["text"] for p in article["paragraphs"]],
    }


class StubWriter:
    def __init__(self, result):
        self.result = result
        self.calls = 0
    def rewrite(self, draft):
        self.calls += 1
        return copy.deepcopy(self.result)


class QwenFreeProseSafetyTests(unittest.TestCase):
    def test_copy_of_original_is_not_editorial_rewrite(self):
        draft = fixture()["drafts"][0]
        report = assess_model_copy(valid_sample(draft), draft)
        self.assertEqual(report["status"], "rejected")
        self.assertIn("insufficient_editorial_transformation", report["failures"])
        self.assertEqual(report["substantially_rewritten_paragraphs"], 0)
        self.assertTrue(report["never_auto_publish_free_prose"])

    def test_invented_numeric_literal_is_rejected(self):
        draft = fixture()["drafts"][0]
        copy_ = valid_sample(draft)
        copy_["paragraphs"][0] += " Nel 2035 arriveranno 999.999 turisti."
        checked = assess_model_copy(copy_, draft)
        self.assertEqual(checked["status"], "rejected")
        self.assertTrue(any(x.startswith("unverified_numeric_literals")
                            for x in checked["failures"]))

    def test_missing_critical_numeric_claim_refused(self):
        draft = fixture()["drafts"][0]
        copy_ = valid_sample(draft)
        copy_["paragraphs"][0] = (
            "I valori di origine indicano una situazione che merita "
            "attenzione, secondo gli indicatori della pubblicazione ISTAT."
        )
        report = assess_model_copy(copy_, draft)
        self.assertEqual(report["status"], "rejected")
        self.assertTrue(any(x.startswith("core_lead_numeric_claims_omitted")
                            for x in report["failures"]))

    def test_invented_causes_and_fake_record_rejected(self):
        draft = fixture()["drafts"][0]
        copy_ = valid_sample(draft)
        copy_["paragraphs"][1] += " Questo è un record storico."
        self.assertIn("unsupported_causal_or_record_claim",
                      assess_model_copy(copy_, draft)["failures"])

    def test_ungrammatical_i_arrivi_and_duplicate(self):
        draft = fixture()["drafts"][0]
        copy_ = valid_sample(draft)
        copy_["paragraphs"][2] += " I arrivi sono bassi."
        copy_["paragraphs"][3] = copy_["paragraphs"][2]
        report = assess_model_copy(copy_, draft)
        self.assertIn("known_italian_grammar_failure_i_arrivi", report["failures"])
        self.assertIn("repeated_identical_paragraphs", report["failures"])

    def test_non_numeric_semantic_truth_not_claimed(self):
        draft = fixture()["drafts"][0]
        copy_ = valid_sample(draft)
        checked = assess_model_copy(copy_, draft)
        self.assertTrue(checked["semantic_truth_not_automatically_certified"])
        self.assertTrue(checked["human_review_required"])

    def test_extra_fields_never_promoted(self):
        draft = fixture()["drafts"][0]
        copy_ = valid_sample(draft)
        copy_["source_url"] = "https://malicious.example"
        report = assess_model_copy(copy_, draft)
        self.assertEqual(report["status"], "rejected")

    def test_lab_never_overwrites_grounded_copy(self):
        original = fixture()
        top = original["drafts"][0]
        writer = StubWriter(valid_sample(top))
        lab = make_rewrite_lab(original, writer, limit=1)
        row = lab["rewrite_results"][0]
        self.assertEqual(row["publication_status"],
                         "not_publishable_model_text")
        self.assertEqual(row["approved_headline_unchanged"], top["headline"])
        self.assertEqual(row["approved_paragraphs_unchanged"], top["paragraphs"])
        self.assertEqual(row["model_copy_assessment"]["status"], "rejected")
        self.assertIn("insufficient_editorial_transformation",
                      row["model_copy_assessment"]["failures"])
        self.assertFalse(lab["published"])
        self.assertTrue(lab["cannot_promote_without_human_check"])

    def test_bad_model_json_is_quarantined_and_labeled(self):
        source = fixture()
        writer = StubWriter({"full_article": "totally invented"})
        lab = make_rewrite_lab(source, writer, limit=1)
        self.assertEqual(lab["rewrite_results"][0]
                         ["model_copy_assessment"]["status"], "rejected")


    def test_surface_real_tourism_output_regression(self):
        draft = fixture()["drafts"][0]
        proposal = valid_sample(draft)
        proposal["headline"] = (
            "Arrivi in calo, presenze in aumento: il turismo alberghiero "
            "nel secondo trimestre 2026"
        )
        # This is the user's observed Qwen failure: it changed ONLY the
        # headline and parroted four paragraphs. The previous gate let it through.
        assessment = assess_model_copy(proposal, draft)
        self.assertEqual(assessment["status"], "rejected")
        self.assertIn("headline_omits_resident_client_scope",
                      assessment["failures"])
        self.assertIn("insufficient_editorial_transformation",
                      assessment["failures"])

    def test_grammatical_sui_arrivi_is_rejected(self):
        draft = fixture()["drafts"][0]
        proposal = valid_sample(draft)
        proposal["paragraphs"][2] += " Il testo parla sui arrivi registrati."
        assessment = assess_model_copy(proposal, draft)
        self.assertIn("known_italian_grammar_failure_sui_arrivi",
                      assessment["failures"])

    def test_genuinely_rewritten_passes_only_to_human_review(self):
        draft = fixture()["drafts"][0]
        proposal = valid_sample(draft)
        proposal["paragraphs"][1] = (
            "Arrivi e presenze non sono la stessa misura. "
            "I primi contano gli ingressi nelle strutture, mentre "
            "le seconde indicano quante notti vengono trascorse "
            "complessivamente dai clienti."
        )
        proposal["paragraphs"][2] = (
            "Il confronto fra i due indicatori fa emergere una differenza: "
            "le notti complessive aumentano nonostante diminuiscano "
            "gli ingressi. Si tratta dello stesso gruppo di clienti "
            "e dello stesso trimestre, e non di due fenomeni distinti."
        )
        proposal["paragraphs"][3] = (
            "Questo andamento da solo non chiarisce le motivazioni "
            "dei soggiorni o le scelte delle persone. Una spiegazione "
            "richiederebbe ulteriori dati su strutture e viaggiatori."
        )
        assessment = assess_model_copy(proposal, draft)
        self.assertEqual(assessment["status"],
                         "needs_human_semantic_review")
        self.assertGreaterEqual(assessment["substantially_rewritten_paragraphs"], 2)
        self.assertTrue(assessment["semantic_truth_not_automatically_certified"])

    def test_surface_v2_extra_lead_does_not_hide_italian_and_semantic_errors(self):
        draft = fixture()["drafts"][0]
        proposal = {
            "headline": draft["headline"],
            "lead": draft["lead"],  # real Surface Qwen extra output
            "paragraphs": [
                draft["paragraphs"][0]["text"] + " Questo contrasto tra "
                "ingressi e notti evidenzia un'evoluzione del comportamento "
                "dei clienti residenti nei confronti delle strutture.",
                draft["paragraphs"][1]["text"],
                "L'andamento mostra che, sebbene i clienti residenti si "
                "verifichino in numero inferiore, la durata media delle "
                "loro stanzialità aumenta rispetto al trimestre precedente.",
                draft["paragraphs"][3]["text"],
            ],
        }
        assessment = assess_model_copy(proposal, draft)
        self.assertEqual(assessment["status"], "rejected")
        self.assertIn("invalid_json_structure_or_extra_fields",
                      assessment["failures"])
        self.assertIn("unsupported_inference_about_customer_behavior",
                      assessment["failures"])
        self.assertIn("unnatural_italian:clients_do_not_occur",
                      assessment["failures"])
        self.assertIn("unnatural_italian:misused_stanzialita",
                      assessment["failures"])
        self.assertIn("headline_unchanged_from_source",
                      assessment["style_warnings"])

    def test_json_schema_has_exactly_two_output_keys(self):
        self.assertFalse(ARTICLE_SCHEMA["additionalProperties"])
        self.assertEqual(set(ARTICLE_SCHEMA["required"]), {"headline", "paragraphs"})
        self.assertEqual(ARTICLE_SCHEMA["properties"]["paragraphs"]["minItems"], 4)
        self.assertEqual(ARTICLE_SCHEMA["properties"]["paragraphs"]["maxItems"], 4)

    def test_local_ollama_request_uses_strict_json_schema(self):
        draft = fixture()["drafts"][0]
        expected = {
            "headline": draft["headline"],
            "paragraphs": [p["text"] for p in draft["paragraphs"]],
        }
        seen = []
        def fake_urlopen(req, timeout):
            request_body = json.loads(req.data.decode("utf-8"))
            seen.append(request_body)
            return io.BytesIO(json.dumps({
                "response": json.dumps(expected, ensure_ascii=False)
            }).encode("utf-8"))
        with patch("scripts.pulse_editorial_local_writer.request.urlopen",
                   side_effect=fake_urlopen):
            response = LocalRewriteCandidate("qwen3:4b-instruct").rewrite(draft)
        self.assertEqual(response, expected)
        self.assertEqual(seen[0]["format"], ARTICLE_SCHEMA)
        self.assertFalse(seen[0]["stream"])

    def test_offline_cli_requires_existing_ollama(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "draft.json"
            out = Path(directory) / "rewrites.json"
            p.write_text(json.dumps(fixture()))
            with patch.object(LocalRewriteCandidate, "check", return_value=False):
                self.assertEqual(main(["--input", str(p),
                                       "--output", str(out)]), 2)
            self.assertFalse(out.exists())
            with patch.object(LocalRewriteCandidate, "check", return_value=True), \
                 patch.object(LocalRewriteCandidate, "rewrite",
                              side_effect=lambda a: valid_sample(a)):
                self.assertEqual(main(["--input", str(p), "--output",
                                       str(out), "--limit", "1"]), 0)
            result = json.loads(out.read_text())
            self.assertEqual(len(result["rewrite_results"]), 1)
            self.assertFalse(result["published"])


if __name__ == "__main__":
    unittest.main()
