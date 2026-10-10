"""Actual Surface v1.4 regressions: distinguish code false alarms from Qwen errors."""
import unittest
from scripts.pulse_editorial_ai import audit
from scripts.pulse_editorial_numeric_guard import inspect_numbers
from test_pulse_editorial_v13 import row_candidate


V14 = [
    {
        "headline": "Gli arrivi dei clienti residenti negli esercizi alberghieri calano del 4,3%",
        "lead": "Nel secondo trimestre 2026, gli arrivi dei clienti residenti negli esercizi alberghieri sono stati 12.464.038, in calo del 4,3% rispetto al secondo trimestre 2025.",
        "body": "Gli arrivi contano le registrazioni di clienti che iniziano un soggiorno negli esercizi ricettivi. Il dato riferito ai clienti residenti e alle strutture alberghiere si riferisce al periodo di due mesi, con una variazione tendenziale rispetto al secondo trimestre 2025.",
    },
    {
        "headline": "Le presenze dei clienti residenti negli esercizi alberghieri aumentano di 1,7%",
        "lead": "Nel secondo trimestre 2026, le presenze dei clienti residenti negli esercizi alberghieri sono state 32.162.873 notti, in aumento dell'1,7% rispetto al secondo trimestre",
        "body": "Le presenze contano le notti trascorse dai clienti negli esercizi ricettivi. Nel secondo trimestre 2026, le notti occupate dai clienti residenti negli esercizi alberghieri sono state 32.162.873, in crescita rispetto al secondo trimestre 2025, quando erano state 31.738.000 notti.",
    },
    {
        "headline": "Gli arrivi dei clienti non residenti negli esercizi alberghieri calano dello 0,9%",
        "lead": "Nel secondo trimestre 2026, gli arrivi dei clienti non residenti negli esercizi alberghieri sono stati 15.184.702, in calo dello 0,9% rispetto al secondo trimestre 2025.",
        "body": "Gli arrivi contano le registrazioni di clienti che iniziano un soggiorno negli esercizi ricettivi. Il dato riferito ai clienti non residenti e agli esercizi alberghieri si riferisce al periodo di due mesi, con una variazione tendenziale rispetto al secondo trimestre 2025.",
    }
]


class RealV14Regressions(unittest.TestCase):
    def test_arrivals_residents_qualifier_is_valid_but_two_months_is_not(self):
        draft = audit(row_candidate(12464038, -4.3), V14[0])
        q = draft["quality"]
        self.assertNotIn("unqualified_yoy_direction", q["issues"])
        self.assertIn("wrong_quarter_month_count", q["issues"])
        self.assertNotIn("headline_only_labels_indicator", q["editorial_warnings"])

    def test_presences_false_prior_total_remains_rejected(self):
        draft = audit(row_candidate(32162873, 1.7, "Presenze"), V14[1])
        q = draft["quality"]
        self.assertIn("unsourced_numbers:31.738.000", q["issues"])
        self.assertNotIn("headline_only_labels_indicator", q["editorial_warnings"])

    def test_arrivals_nonresidents_qualifier_is_valid_but_two_months_is_not(self):
        draft = audit(row_candidate(15184702, -0.9, residence="non residenti"), V14[2])
        q = draft["quality"]
        self.assertNotIn("unqualified_yoy_direction", q["issues"])
        self.assertIn("wrong_quarter_month_count", q["issues"])
        self.assertNotIn("headline_only_labels_indicator", q["editorial_warnings"])

    def test_verb_calano_cannot_invert_positively_sourced_yoy(self):
        source = row_candidate(12464038, 4.3)["evidence"]
        _, issues = inspect_numbers("Gli arrivi calano del 4,3%.", source)
        self.assertIn("wrong_yoy_direction", issues)

    def test_verb_aumentano_cannot_invert_negatively_sourced_yoy(self):
        source = row_candidate(12464038, -4.3)["evidence"]
        _, issues = inspect_numbers("Gli arrivi aumentano del 4,3%.", source)
        self.assertIn("wrong_yoy_direction", issues)

    def test_valid_quarter_and_two_unrelated_months_not_misidentified(self):
        proposal = dict(V14[0])
        proposal["body"] = (
            "Il secondo trimestre copre tre mesi. Nei due mesi precedenti "
            "all'analisi non sono disponibili altri dati."
        )
        result = audit(row_candidate(12464038, -4.3), proposal)
        self.assertNotIn("wrong_quarter_month_count", result["quality"]["issues"])

    def test_quarter_duration_error_detected_without_inserting_new_numeric_value(self):
        proposal = dict(V14[2])
        proposal["body"] = (
            "Il dato fa riferimento al secondo trimestre 2026, "
            "un bimestre. I dati restano parziali."
        )
        result = audit(row_candidate(15184702, -0.9, residence="non residenti"), proposal)
        self.assertIn("wrong_period_duration", result["quality"]["issues"])


if __name__ == "__main__":
    unittest.main()
