"""Regression tests based on the actual Qwen3 v1.3 uploaded output.

All readings are deterministic: no Ollama connection or paid APIs.
"""
import unittest
from scripts.pulse_editorial_ai import audit
from scripts.pulse_editorial_style import style_warnings
from scripts.pulse_editorial_brief import editorial_brief
from test_pulse_editorial_v13 import row_candidate


class V14RealPilotTests(unittest.TestCase):
    def test_real_arrivi_residenti_passed_numbers_but_fails_editorial_depth(self):
        candidate = row_candidate(12464038, -4.3, "Arrivi", "residenti")
        proposal = {
            "headline": "Arrivi clienti residenti negli esercizi alberghieri",
            "lead": ("Nel secondo trimestre 2026, gli arrivi dei clienti residenti "
                     "negli esercizi alberghieri sono stati 12.464.038, in calo "
                     "del 4,3% rispetto al secondo trimestre 2025."),
            "body": ("I dati mostrano un decremento degli arrivi di clienti "
                     "residenti nei locali alberghieri rispetto all'anno "
                     "precedente, con una variazione tendenziale negativa "
                     "nel periodo considerato."),
        }
        d = audit(candidate, proposal)
        self.assertEqual(d["quality"]["status"], "review_required")
        self.assertIn("headline_only_labels_indicator",
                      d["quality"]["editorial_warnings"])
        self.assertIn("body_restates_change_instead_of_explaining",
                      d["quality"]["editorial_warnings"])
        self.assertEqual(d["quality"]["issues"], [])

    def test_real_presenze_contains_unsupported_multiperiod_trend(self):
        candidate = row_candidate(32162873, 1.7, "Presenze", "residenti")
        proposal = {
            "headline": "Presenze clienti residenti negli esercizi alberghieri",
            "lead": ("Nel secondo trimestre 2026, le presenze dei clienti residenti "
                     "negli esercizi alberghieri sono state 32.162.873 notti, "
                     "in aumento dell'1,7% rispetto al secondo trimestre 2025."),
            "body": ("Le presenze dei clienti residenti negli esercizi alberghieri "
                     "hanno registrato un incremento rispetto al periodo precedente, "
                     "confermando una tendenza positiva nel periodo di riferimento."),
        }
        d = audit(candidate, proposal)
        self.assertEqual(d["quality"]["status"], "rejected")
        self.assertIn("unverified_multiperiod_trend", d["quality"]["issues"])

    def test_real_arrivi_nonresidents_claims_no_significant_changes(self):
        candidate = row_candidate(15184702, -0.9, "Arrivi", "non residenti")
        proposal = {
            "headline": "Arrivi clienti non residenti negli esercizi alberghieri",
            "lead": ("Nel secondo trimestre 2026, gli arrivi dei clienti non residenti "
                     "negli esercizi alberghieri sono stati 15.184.702, in calo "
                     "dello 0,9% rispetto al secondo trimestre 2025."),
            "body": ("I dati mostrano un piccolo decremento degli arrivi di clienti "
                     "non residenti, rispetto al periodo corrispondente del 2025, "
                     "senza variazioni significative in termini di struttura "
                     "o categoria di ospitazione."),
        }
        d = audit(candidate, proposal)
        self.assertEqual(d["quality"]["status"], "rejected")
        self.assertIn("unverified_statistical_significance", d["quality"]["issues"])
        self.assertIn("unverified_structure_stability", d["quality"]["issues"])

    def test_statistical_tendenziale_is_legitimate_and_not_long_term_trend(self):
        c = row_candidate(12464038, -4.3, "Arrivi", "residenti")
        proposal = {
            "headline": "Arrivi dei residenti in calo nel secondo trimestre 2026",
            "lead": ("Gli arrivi dei clienti residenti negli esercizi alberghieri "
                     "sono 12.464.038, con una variazione tendenziale negativa "
                     "del 4,3% rispetto allo stesso trimestre 2025."),
            "body": ("La variazione tendenziale si riferisce soltanto al confronto "
                     "fra il trimestre 2026 e quello corrispondente del 2025. "
                     "Non descrive da sola l'intero andamento storico degli arrivi."),
        }
        d = audit(c, proposal)
        self.assertNotIn("unverified_multiperiod_trend", d["quality"]["issues"])
        self.assertNotIn("unverified_statistical_significance", d["quality"]["issues"])

    def test_negative_statistical_significance_is_not_innocent(self):
        c = row_candidate(12464038, -4.3, "Arrivi", "residenti")
        proposal = {
            "headline": "Arrivi dei residenti in calo nel secondo trimestre 2026",
            "lead": ("Gli arrivi dei clienti residenti negli esercizi alberghieri "
                     "sono 12.464.038, in calo del 4,3% rispetto al 2025."),
            "body": ("La variazione non è statisticamente significativa. "
                     "Sono possibili molte interpretazioni, ma nessuna è "
                     "certificata dai dati pubblicati per il trimestre."),
        }
        self.assertIn("unverified_statistical_significance",
                      audit(c, proposal)["quality"]["issues"])

    def test_brief_includes_official_indicator_glossary(self):
        arrivals = row_candidate(12464038, -4.3, "Arrivi", "residenti")
        nights = row_candidate(32162873, 1.7, "Presenze", "residenti")
        self.assertIn("iniziano un soggiorno",
                      editorial_brief(arrivals["evidence"])["indicator_glossary"])
        self.assertIn("notti trascorse",
                      editorial_brief(nights["evidence"])["indicator_glossary"])

    def test_both_single_measure_and_full_article_remain_not_published(self):
        c = row_candidate(12464038, -4.3, "Arrivi", "residenti")
        proposal = {
            "headline": "Arrivi dei clienti residenti in calo nel secondo trimestre 2026",
            "lead": ("Nel secondo trimestre 2026, gli arrivi dei clienti residenti "
                     "negli esercizi alberghieri sono 12.464.038, "
                     "in calo del 4,3% sul 2025."),
            "body": ("Per questo indicatore si considerano i clienti "
                     "che iniziano un soggiorno in una struttura ricettiva. "
                     "La variazione confronta periodi corrispondenti "
                     "in anni consecutivi."),
        }
        d = audit(c, proposal)
        self.assertEqual(d["publication_status"], "draft_only")
        self.assertEqual(d["editorial_format"], "single_finding_statistical_brief")
        self.assertEqual(d["full_article_evidence_status"],
                         "requires_multiple_independent_findings")
        self.assertTrue(d["quality"]["requires_human_fact_check"])


if __name__ == "__main__":
    unittest.main()
