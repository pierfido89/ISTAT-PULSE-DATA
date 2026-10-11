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

    def test_surface_qwen35_9b_article_is_rejected_for_real_grammar_errors(self):
        """Actual first Qwen3.5 9B article passed old rules despite errors."""
        draft = fixture()["drafts"][0]
        proposal = {
            "headline": draft["headline"],
            "paragraphs": [
                "Nel secondo trimestre 2026, gli esercizi alberghieri hanno "
                "registrato un calo del 4,3% negli arrivi dei clienti "
                "residenti, pari a 12.464.038 unità, mentre le presenze "
                "sono salite dell'1,7% fino a raggiungere le 32.162.873 "
                "notti rispetto al secondo trimestre 2025.",
                "Gli arrivi indicano il numero di ingressi nelle strutture "
                "ricettive, mentre le presenze misurano l'insieme delle notti "
                "trascorse dai ospiti. Il rapporto tra queste due grandezze "
                "fornisce una permanenza media per arrivo di circa 2,58 notti.",
                "Il dato emerge dal confronto diretto: nonostante la "
                "diminuzione degli ingressi registrati negli alberghi, il "
                "totale delle notti aumentato segnala che i clienti residenti "
                "hanno prolungato la propria permanenza media rispetto al "
                "periodo analogo dell'anno precedente.",
                "È opportuno considerare che le variazioni riportate "
                "descrivono l'andamento osservato dei numeri senza poterne "
                "dedurre automaticamente le cause sottostanti, e che tali "
                "valori non costituiscono previsioni future.",
            ],
        }
        report = assess_model_copy(proposal, draft)
        self.assertEqual(report["status"], "rejected")
        self.assertIn(
            "unnatural_italian:dai_ospiti_instead_of_dagli_ospiti",
            report["failures"],
        )
        self.assertIn(
            "unnatural_italian:unnatural_increased_total_nights",
            report["failures"],
        )
        self.assertIn(
            "aggregate_average_presented_as_individual_behavior",
            report["failures"],
        )
        self.assertEqual(report["substantially_rewritten_paragraphs"], 4)
        self.assertIn("headline_unchanged_from_source", report["style_warnings"])
        self.assertTrue(report["human_review_required"])

    def test_aggregate_average_can_be_described_without_attributing_choices(self):
        draft = fixture()["drafts"][0]
        proposal = valid_sample(draft)
        proposal["paragraphs"][1] = (
            "Gli arrivi sono gli ingressi nelle strutture alberghiere, "
            "mentre le presenze corrispondono alle notti trascorse "
            "complessivamente. Il rapporto fra i due dati permette "
            "di descrivere una permanenza media per arrivo."
        )
        proposal["paragraphs"][2] = (
            "I due valori si muovono in direzioni opposte nello stesso "
            "trimestre e per la stessa clientela residente. Ne risulta "
            "una permanenza media per arrivo in aumento rispetto al "
            "periodo precedente, senza indicare scelte individuali."
        )
        proposal["paragraphs"][3] = (
            "Queste variazioni descrivono il rapporto matematico "
            "fra ingressi e notti osservate e non dimostrano quali "
            "fattori abbiano determinato il risultato statistico."
        )
        report = assess_model_copy(proposal, draft)
        self.assertNotIn(
            "aggregate_average_presented_as_individual_behavior",
            report["failures"],
        )
        self.assertNotIn(
            "unnatural_italian:dai_ospiti_instead_of_dagli_ospiti",
            report["failures"],
        )
        self.assertTrue(report["human_review_required"])

    def test_surface_qwen35_9b_second_full_article_flags_all_errors(self):
        """Second live Surface result: rejection must identify semantic failures."""
        draft = fixture()["drafts"][0]
        proposal = {
            "headline": (
                "Turismo alberghiero: calo degli arrivi, crescita delle "
                "presenze per i clienti residenti nel secondo trimestre 2026"
            ),
            "paragraphs": [
                "Nel secondo trimestre del 2026 gli esercizi alberghieri "
                "hanno registrato un decremento degli ingressi dei clienti "
                "residenti pari al 4,3%, attestandosi a 12.464.038 unità, "
                "mentre le notti trascorse sono aumentate dell'1,7% fino "
                "a raggiungere le 32.162.873.",
                "È importante distinguere tra i due concetti: gli arrivi "
                "indicano il numero di persone che entrano nelle strutture, "
                "mentre le presenze misurano l'ammontare delle notti dormite. "
                "Il rapporto tra queste due grandezze fornisce una media "
                "di circa 2,58 notti per ospite.",
                "L'analisi rivela un fenomeno inverso: nonostante la "
                "riduzione del flusso di nuovi ospiti, il totale delle notti "
                "offerte è salito. Questo implica che, in media, i clienti "
                "residenti hanno prolungato la propria permanenza rispetto "
                "al periodo corrispondente dell'anno precedente.",
                "Va tenuto presente che le cifre riportate descrivono "
                "solo l'andamento osservato e non consentono di risalire "
                "alle ragioni del cambiamento né di formulare previsioni future.",
            ],
        }
        report = assess_model_copy(proposal, draft)
        self.assertEqual(report["status"], "rejected")
        failures = report["failures"]
        self.assertIn("core_lead_numeric_claims_omitted:2025", failures)
        self.assertIn("arrivals_wrongly_defined_as_unique_people", failures)
        self.assertIn("mean_stay_wrong_denominator_unique_guest", failures)
        self.assertIn("actual_overnights_mislabeled_as_offered_nights", failures)
        self.assertIn(
            "aggregate_average_presented_as_individual_behavior",
            failures,
        )
        self.assertTrue(report["human_review_required"])
        self.assertFalse(report.get("publishable", False))

    def test_correct_aggregate_formulations_are_not_erroneously_rejected(self):
        draft = fixture()["drafts"][0]
        proposal = valid_sample(draft)
        proposal["paragraphs"][1] = (
            "Gli arrivi rappresentano gli ingressi registrati negli alberghi, "
            "non il numero di persone distinte. Le presenze indicano "
            "le notti effettivamente trascorse nelle strutture e il loro "
            "rapporto con gli arrivi descrive una media per arrivo."
        )
        proposal["paragraphs"][2] = (
            "Nei dati dei clienti residenti il numero degli ingressi "
            "diminuisce, mentre quello delle notti effettive cresce. "
            "Il rapporto aggregato si modifica, senza consentire "
            "attribuzioni di scelte o intenzioni ai singoli clienti."
        )
        report = assess_model_copy(proposal, draft)
        for code in (
            "arrivals_wrongly_defined_as_unique_people",
            "mean_stay_wrong_denominator_unique_guest",
            "actual_overnights_mislabeled_as_offered_nights",
            "aggregate_average_presented_as_individual_behavior",
        ):
            self.assertNotIn(code, report["failures"])
        self.assertTrue(report["human_review_required"])

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
            response = LocalRewriteCandidate("qwen3.5:9b").rewrite(draft)
        self.assertEqual(response, expected)
        self.assertEqual(seen[0]["format"], ARTICLE_SCHEMA)
        self.assertEqual(seen[0]["model"], "qwen3.5:9b")
        self.assertIs(seen[0]["think"], False)
        self.assertNotIn("think", seen[0]["options"])
        self.assertFalse(seen[0]["stream"])

    def test_selected_article_range_skips_previous_topics(self):
        source = fixture()
        selected = source["drafts"][1:3]
        writer = StubWriter(valid_sample(selected[0]))
        report = make_rewrite_lab(source, writer, limit=2, start=1)
        self.assertEqual(report["starting_article_index"], 1)
        self.assertEqual(report["number_of_model_calls"], 2)
        self.assertEqual(writer.calls, 2)
        self.assertEqual(
            [r["source_story_id"] for r in report["rewrite_results"]],
            [a["id"] for a in selected],
        )
        self.assertNotIn(source["drafts"][0]["id"],
                         [r["source_story_id"] for r in report["rewrite_results"]])
        self.assertFalse(report["published"])

    def test_selected_article_range_never_wraps_or_exceeds_articles(self):
        source = fixture()
        writer = StubWriter(valid_sample(source["drafts"][0]))
        for start, limit in ((-1, 1), (6, 1), (5, 2), (0, 7), (0, 0)):
            with self.subTest(start=start, limit=limit):
                with self.assertRaises(ValueError):
                    make_rewrite_lab(source, writer, limit=limit, start=start)
        self.assertEqual(writer.calls, 0)

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
