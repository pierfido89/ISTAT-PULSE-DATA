"""Regressions learned from the FIRST REAL Surface/Qwen3 PDF pilot.

Official data: ISTAT II trimestre 2026; original actual draft
values are preserved in assertions, no cloud model is called.
"""
import unittest
from unittest.mock import patch
from scripts.pulse_editorial_ai import audit, candidates, generate_reviewed, LocalOllama
from scripts.pulse_taxonomy import load_taxonomy
from test_pulse_editorial_ai import primary, finding, PROPOSAL


def audit_fact(value, change, indicator, residence, draft):
    row = finding(value, change, indicator)
    row["segment"]["residence"] = residence
    cand = candidates(primary(row))[0]
    return audit(cand, draft)


class RealPilotRegression(unittest.TestCase):
    def test_real_arrivi_residenti_magnitude_and_2025_are_supported(self):
        lead = ("I dati ufficiali registrano un calo del 4,3% negli arrivi in "
                "esercizi alberghieri residenti nel secondo trimestre del 2026 "
                "rispetto allo stesso periodo dell'anno precedente. "
                "L'indicatore segnala una diminuzione rispetto al 2025-Q2, "
                "con 12.464.038 arrivi registrati. Il confronto rimane circoscritto.")
        body = ("Gli arrivi dei clienti residenti negli esercizi alberghieri "
                "ammontano a 12.464.038, in calo del 4,3% rispetto allo "
                "stesso periodo del 2025. Il confronto mostra una variazione "
                "di periodo e non dimostra un andamento pluriennale; "
                "l'indicatore riguarda gli arrivi, non le presenze notturne.")
        draft = {"headline": "Arrivi dei residenti negli alberghi in calo nel secondo trimestre",
                 "lead": lead, "body": body}
        result = audit_fact(12464038, -4.3, "Arrivi", "residenti", draft)
        self.assertFalse(any(s.startswith("unsourced_numbers") for s in result["quality"]["issues"]))
        self.assertNotIn("published_yoy_missing", result["quality"]["issues"])
        self.assertNotIn("secondary_indicator_without_evidence", result["quality"]["issues"])
        self.assertEqual(result["taxonomy"]["primary_category"], "SOC-04")

    def test_wrong_quadrimestre_is_rejected_despite_valid_statistics(self):
        text = {"headline": "Presenze dei residenti a +1,7% in II quadrimestre 2026",
                "lead": "Nel II quadrimestre 2026, rispetto al 2025, le presenze dei residenti negli esercizi alberghieri crescono di +1,7%, fino a 32.162.873 notti.",
                "body": "Le presenze dei residenti negli esercizi alberghieri aumentano del 1,7%, fino a 32.162.873 notti. Il riferimento corretto è il secondo trimestre 2026 e il confronto con l'anno precedente non dimostra una tendenza pluriennale."}
        result = audit_fact(32162873, 1.7, "Presenze", "residenti", text)
        self.assertIn("wrong_period_duration", result["quality"]["issues"])
        self.assertNotIn("unsourced_numbers:2025", result["quality"]["issues"])
        self.assertEqual(result["taxonomy"]["primary_category"], "SOC-04")

    def test_bed_and_breakfast_and_rounded_total_are_both_rejected(self):
        text = {"headline": "Arrivi turistici nei bed & breakfast in calo dello 0,9% nel 2026-Q2",
                "lead": "Negli esercizi alberghieri, gli arrivi dei non residenti nel secondo trimestre 2026 scendono dello 0,9% fino a 15.184.702 arrivi.",
                "body": "Gli arrivi turistici nei bed & breakfast sono in calo dello 0,9% nello stesso periodo rispetto all'anno precedente. Il volume è pari a 15.184.700 arrivi: tale valore non viene documentato esattamente dal prospetto ISTAT. Sono dati aggregati del periodo."}
        result = audit_fact(15184702, -.9, "Arrivi", "non residenti", text)
        self.assertIn("unsourced_accommodation_type", result["quality"]["issues"])
        self.assertTrue(any("15.184.700" in x for x in result["quality"]["issues"]))
        self.assertNotIn("published_yoy_missing", result["quality"]["issues"])

    def test_a_truthful_negative_change_does_not_require_written_minus_sign(self):
        text = {"headline": "Arrivi dei clienti residenti in calo nel secondo trimestre 2026",
                "lead": "Nel secondo trimestre del 2026 gli arrivi dei clienti residenti negli esercizi alberghieri diminuiscono del 4,3% rispetto al 2025, attestandosi a 12.464.038.",
                "body": "Il dato ufficiale relativo agli arrivi di clienti residenti negli esercizi alberghieri è di 12.464.038 nel secondo trimestre 2026. Rispetto allo stesso trimestre del 2025, il confronto indica una riduzione del 4,3% e non autorizza conclusioni sul lungo periodo."}
        result = audit_fact(12464038, -4.3, "Arrivi", "residenti", text)
        self.assertNotIn("published_yoy_missing", result["quality"]["issues"])
        self.assertFalse(any(x.startswith("unsourced_numbers") for x in result["quality"]["issues"]))
        self.assertNotIn("wrong_yoy_direction", result["quality"]["issues"])
        self.assertEqual(result["quality"]["status"], "review_required")

    def test_wrong_direction_is_not_accepted_as_just_a_valid_magnitude(self):
        text = {"headline": "Arrivi dei residenti in aumento nel secondo trimestre 2026",
                "lead": "Gli arrivi dei clienti residenti negli alberghi aumentano del 4,3% nel secondo trimestre 2026, raggiungendo 12.464.038 arrivi.",
                "body": "Le registrazioni di arrivo sono 12.464.038 e, secondo questa bozza, il dato aumenta del 4,3% rispetto allo stesso periodo dell'anno precedente. Il testo sostiene quindi che vi sia crescita nell'indicatore degli arrivi."}
        result = audit_fact(12464038, -4.3, "Arrivi", "residenti", text)
        self.assertIn("wrong_yoy_direction", result["quality"]["issues"])
        self.assertEqual(result["quality"]["status"], "rejected")

    def test_inaccurate_resident_buildings_rejected(self):
        text = dict(PROPOSAL)
        text["headline"] = "Arrivi negli esercizi alberghieri residenti: dato del trimestre"
        result = audit_fact(12464038, -4.3, "Arrivi", "residenti", text)
        self.assertIn("misassigned_residence_to_facilities", result["quality"]["issues"])

    def test_article_about_arrivals_cannot_be_about_presences(self):
        text = dict(PROPOSAL)
        text["headline"] = "Arrivi in calo e presenze in aumento nel turismo italiano"
        result = audit_fact(12464038, -4.3, "Arrivi", "residenti", text)
        self.assertIn("secondary_indicator_without_evidence", result["quality"]["issues"])

    def test_correct_quarter_not_mislabeled(self):
        text = dict(PROPOSAL)
        text["headline"] = "Presenze alberghiere in crescita nel secondo trimestre 2026"
        result = audit_fact(77611946, 2.4, "Presenze", "totale", text)
        self.assertNotIn("wrong_period_duration", result["quality"]["issues"])
        self.assertNotIn("wrong_quarter_number", result["quality"]["issues"])

    def test_positive_change_cannot_be_described_as_a_decrease(self):
        text = dict(PROPOSAL)
        text["lead"] = ("Nel secondo trimestre 2026 le presenze alberghiere "
                        "registrano un calo del 2,4%, fino a 77.611.946 notti.")
        result = audit_fact(77611946, 2.4, "Presenze", "totale", text)
        self.assertIn("wrong_yoy_direction", result["quality"]["issues"])

    def test_one_local_rewrite_can_fix_a_rejected_fabricated_facility(self):
        candidate = candidates(primary(finding()))[0]
        bad = dict(PROPOSAL)
        bad["body"] += " Nei B&B i numeri confermano il confronto."
        with patch.object(LocalOllama, "generate",
                          side_effect=[bad, PROPOSAL]) as gen:
            repaired = generate_reviewed(candidate, LocalOllama(),
                                         load_taxonomy(), max_retries=1)
        self.assertEqual(gen.call_count, 2)
        self.assertEqual(repaired["generator"]["attempts"], 2)
        self.assertIn("unsourced_accommodation_type",
                      repaired["quality"]["attempt_history"][0])
        self.assertEqual(repaired["quality"]["status"], "review_required")
        self.assertEqual(repaired["publication_status"], "draft_only")

    def test_failed_second_attempt_remains_rejected(self):
        candidate = candidates(primary(finding()))[0]
        bad = dict(PROPOSAL)
        bad["body"] += " Negli agriturismi si verificano le stesse variazioni."
        with patch.object(LocalOllama, "generate",
                          side_effect=[bad, bad]):
            repaired = generate_reviewed(candidate, LocalOllama(),
                                         load_taxonomy(), max_retries=1)
        self.assertEqual(repaired["quality"]["status"], "rejected")
        self.assertEqual(repaired["generator"]["attempts"], 2)

    def test_disabling_retry_makes_one_local_call(self):
        candidate = candidates(primary(finding()))[0]
        bad = dict(PROPOSAL)
        bad["body"] += " Negli agriturismi si verificano le stesse variazioni."
        with patch.object(LocalOllama, "generate",
                          return_value=bad) as gen:
            draft = generate_reviewed(candidate, LocalOllama(),
                                      load_taxonomy(), max_retries=0)
        self.assertEqual(gen.call_count, 1)
        self.assertEqual(draft["quality"]["status"], "rejected")

if __name__ == "__main__":
    unittest.main()
