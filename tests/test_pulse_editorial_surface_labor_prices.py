"""Regressions from the October 11 Surface labor/prices pilot.

These tests exercise the exact failure modes without invoking Ollama.
A better guard must not make unsupported claims acceptable.
"""
import unittest

from scripts.pulse_editorial_local_writer import (
    _number_inventory, _month_claims_preserved, assess_model_copy,
)


class SurfaceLaborPricesRegressions(unittest.TestCase):
    def test_verbal_decrease_matches_negative_source(self):
        source = _number_inventory("Inattivi 15-64 anni: -3,0%.")
        proposal = _number_inventory("Gli inattivi hanno subito una diminuzione del 3,0%.")
        self.assertIn("-3.0%", source)
        self.assertIn("-3.0%", proposal)
        self.assertNotIn("3.0%", proposal)

    def test_direction_cannot_be_inverted(self):
        source_decrease = _number_inventory("Variazione -3,0%.")
        false_increase = _number_inventory("Un aumento del 3,0%.")
        self.assertNotIn("3.0%", source_decrease)
        self.assertIn("3.0%", false_increase)
        self.assertNotEqual(set(source_decrease), set(false_increase))
        source_increase = _number_inventory("Variazione +3,0%.")
        false_decrease = _number_inventory("Una diminuzione del 3,0%.")
        self.assertNotEqual(set(source_increase), set(false_decrease))

    def test_year_month_not_fake_missing_number(self):
        source = _number_inventory("Indici osservati nel 2026-08: NIC +3,3%.")
        self.assertIn("2026", source)
        self.assertIn("3.3%", source)
        self.assertNotIn("08", source)
        self.assertEqual(
            _month_claims_preserved("Indici 2026-08", "NIC, agosto 2026"), []
        )

    def test_wrong_month_is_rejected_even_if_year_survives(self):
        self.assertIn(
            "reference_month_omitted_or_changed:2026-08",
            _month_claims_preserved("Prezzi 2026-08", "Prezzi settembre 2026"),
        )
        self.assertIn(
            "reference_month_omitted_or_changed:2026-08",
            _month_claims_preserved("Prezzi 2026-08", "Prezzi nel 2026"),
        )

    def test_full_labor_pilot_flags_wrong_population_scope(self):
        source = {
            "domain": "labor_categories_yoy_evidence",
            "headline": "Lavoro, 2026-08: 24.352.000 occupati in Italia",
            "lead": "Gli occupati sono 24.352.000 (+1,2% sull'anno); "
                    "i disoccupati sono 1.591.000 (+8,8%).",
            "paragraphs": [
                {"text": "Gli occupati sono 24.352.000 (+1,2% sull'anno); i disoccupati sono 1.591.000 (+8,8%)."},
                {"text": "Gli inattivi tra 15 e 64 anni sono 12.124.000, in diminuzione del -3,0%."},
                {"text": "La fonte misura categorie diverse senza motivare le cause."},
                {"text": "Confrontare le variazioni non restituisce automaticamente il tasso di disoccupazione."},
            ],
            "body": "Gli inattivi di 15-64 anni sono 12.124.000 (-3,0%).",
            "source_url": "https://www.istat.it/wp-content/uploads/2026/10/CS_Occupati-e-disoccupati_AGOSTO_2026.pdf",
        }
        proposal = {
            "headline": "Lavoro, agosto 2026: aumentano gli occupati registrati in Italia",
            "paragraphs": [
                "Nel mese di agosto 2026 le persone occupate in Italia risultano 24.352.000, in aumento dell'1,2% rispetto a un anno prima. I disoccupati arrivano a 1.591.000, con una variazione dell'8,8%.",
                "Gli indicatori presentati si riferiscono alle categorie di occupati, disoccupati e inattivi tra i 15 e i 64 anni: sono quindi grandezze distinte che richiedono una lettura attenta.",
                "Fra gli inattivi si registra una diminuzione del 3,0%, dato coerente con il confronto annuo riportato dalla fonte ufficiale e da leggere nel perimetro statistico di riferimento.",
                "L'evoluzione di queste categorie non permette, da sola, di spiegare le cause dei movimenti del mercato del lavoro o di ricavare automaticamente il tasso di disoccupazione.",
            ],
        }
        result = assess_model_copy(proposal, source)
        self.assertIn("labor_age_scope_overgeneralized", result["failures"])
        self.assertFalse(any(
            failure.startswith("unverified_numeric_literals:")
            for failure in result["failures"]
        ))
        self.assertFalse(any(
            failure.startswith("core_lead_numeric_claims_omitted:")
            for failure in result["failures"]
        ))
        self.assertTrue(result["human_review_required"])

    def test_no_automatic_publication_from_guard_change(self):
        source = {
            "domain": "different_price_baskets_yoy_rates",
            "headline": "Prezzi al consumo, NIC, IPCA e FOI a confronto",
            "lead": "Variazioni 2026-08: NIC +3,3%, IPCA +3,2%, FOI +3,4%.",
            "body": "Livelli degli indici in base 2025=100: 103,9; 102,7; 103,7.",
            "paragraphs": [],
        }
        proposal = {
            "headline": "Prezzi al consumo: confronto NIC, IPCA e FOI ad agosto 2026",
            "paragraphs": [
                "Per agosto 2026, NIC aumenta del 3,3%, IPCA del 3,2% e FOI del 3,4% rispetto allo stesso mese di un anno prima, secondo la diffusione statistica ufficiale.",
                "La base degli indici è 2025=100: i livelli comunicati ammontano rispettivamente a 103,9 per NIC, 102,7 per IPCA e 103,7 per FOI, valori non identici ai tassi annui.",
                "I diversi indicatori consentono di leggere aspetti differenti dell'andamento dei prezzi al consumo e non sono direttamente intercambiabili per ogni finalità statistica.",
                "La presenza di tre indici ufficiali non equivale a misurare la spesa aggiuntiva di una singola famiglia, né permette senza altre evidenze di attribuire cause specifiche alle variazioni.",
            ],
        }
        report = assess_model_copy(proposal, source)
        self.assertNotIn("core_lead_numeric_claims_omitted:08", report["failures"])
        self.assertEqual(report["status"], "needs_human_semantic_review")
        self.assertTrue(report["never_auto_publish_free_prose"])


if __name__ == "__main__":
    unittest.main()
