"""PULSE Editorial v1.3 tests grounded in the user's actual Qwen v1.2 drafts.

No model downloads, subscriptions or cloud AI calls.
"""
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_ai import (
    audit, candidates, generate_reviewed, LocalOllama,
)
from scripts.pulse_editorial_brief import editorial_brief, source_scope
from scripts.pulse_taxonomy import load_taxonomy
from test_pulse_editorial_ai import primary, finding

def row_candidate(value, change, indicator="Arrivi", residence="residenti"):
    x = finding(value, change, indicator)
    x["segment"]["residence"] = residence
    return candidates(primary(x))[0]

def clean_draft(value="12.464.038", delta="4,3", population="residenti",
                movement="calo"):
    return {
        "headline": f"Arrivi dei clienti {population} negli alberghi in {movement} nel secondo trimestre 2026",
        "lead": (f"Nel secondo trimestre 2026 gli arrivi dei clienti {population} "
                 f"negli esercizi alberghieri sono stati {value}, in {movement} "
                 f"del {delta}% rispetto allo stesso periodo del 2025."),
        "body": ("La variazione riguarda le registrazioni di arrivo nelle "
                 "strutture alberghiere durante il trimestre considerato. "
                 "Il confronto è con lo stesso periodo dell'anno precedente, "
                 "senza attribuire al dato significati non dimostrati.")
    }

class V13RegressionTests(unittest.TestCase):
    def test_positive_fact_brief_keeps_nonresident_population(self):
        fact = row_candidate(15184702, -0.9,
                             residence="non residenti")["evidence"]
        b = editorial_brief(fact)
        self.assertEqual(b["population_scope"], "non residenti")
        self.assertIn("dei clienti non residenti", b["exact_statistical_subject"])
        self.assertIn("15.184.702", b["canonical_reference_sentence"])
        self.assertIn("secondo trimestre 2025", b["canonical_reference_sentence"])

    def test_exact_facts_and_cohort_in_title_and_lead_are_eligible(self):
        candidate = row_candidate(12464038, -4.3)
        draft = audit(candidate, clean_draft())
        self.assertEqual(draft["quality"]["status"], "review_required")
        self.assertEqual(draft["quality"]["issues"], [])

    def test_actual_bad_nonresident_draft_is_rejected_even_with_correct_total(self):
        candidate = row_candidate(15184702, -0.9, residence="non residenti")
        p = clean_draft("15.184.702", "0,9", "residenti")
        draft = audit(candidate, p)
        self.assertEqual(draft["quality"]["status"], "rejected")
        self.assertIn("unsourced_population_residents", draft["quality"]["issues"])
        self.assertIn("missing_source_cohort_in_headline", draft["quality"]["issues"])
        self.assertIn("missing_source_cohort_in_lead", draft["quality"]["issues"])

    def test_actual_qwen_grammatical_error_is_rejected(self):
        candidate = row_candidate(12464038, -4.3)
        p = clean_draft()
        p["body"] += " I dati registrano un'abbassamento degli arrivi."
        draft = audit(candidate, p)
        self.assertIn("grammatical_error_un_abbassamento", draft["quality"]["issues"])

    def test_actual_qwen_style_is_marked_even_if_statistics_pass(self):
        candidate = row_candidate(32162873, 1.7, "Presenze")
        p = {
            "headline": "Presenze dei clienti residenti negli alberghi nel secondo trimestre 2026",
            "lead": "Nel secondo trimestre 2026 le presenze dei clienti residenti negli esercizi alberghieri salgono a 32.162.873 notti, in aumento del 1,7% sul 2025.",
            "body": ("Il dato è stato osservato e confrontato ufficialmente, "
                     "senza modifiche o arrotondamenti. "
                     "Nel secondo trimestre 2026 si registrano 32.162.873 "
                     "presenze. La variabilità è riferita a un periodo specifico."),
        }
        draft = audit(candidate, p)
        self.assertEqual(draft["quality"]["status"], "review_required")
        self.assertTrue(draft["quality"]["editorial_warnings"])

    def test_rewrite_cannot_replace_good_draft_with_hallucination(self):
        candidate = row_candidate(12464038, -4.3)
        first = clean_draft()
        first["body"] += " Il valore è stato osservato senza modifiche o arrotondamenti."
        bad = clean_draft()
        bad["headline"] = "Arrivi dei clienti non residenti in aumento nel secondo trimestre 2026"
        with patch.object(LocalOllama, "generate", side_effect=[first, bad]) as gen:
            chosen = generate_reviewed(candidate, LocalOllama(), load_taxonomy())
        self.assertEqual(gen.call_count, 2)
        self.assertEqual(chosen["quality"]["status"], "review_required")
        self.assertEqual(chosen["generator"]["attempts"], 2)
        self.assertEqual(chosen["generator"]["selected_attempt"], 1)

    def test_second_draft_is_kept_when_it_fixes_a_bad_first_attempt(self):
        candidate = row_candidate(12464038, -4.3)
        first = clean_draft()
        first["lead"] += " Il prezzo è 999 euro."
        with patch.object(LocalOllama, "generate",
                          side_effect=[first, clean_draft()]) as gen:
            chosen = generate_reviewed(candidate, LocalOllama(), load_taxonomy())
        self.assertEqual(gen.call_count, 2)
        self.assertEqual(chosen["quality"]["status"], "review_required")
        self.assertEqual(chosen["generator"]["selected_attempt"], 2)

    def test_canonical_percentage_positive_has_italian_elision(self):
        fact = row_candidate(32162873, 1.7, "Presenze")["evidence"]
        self.assertIn("dell'1,7%", editorial_brief(fact)["canonical_reference_sentence"])

if __name__ == "__main__":
    unittest.main()
