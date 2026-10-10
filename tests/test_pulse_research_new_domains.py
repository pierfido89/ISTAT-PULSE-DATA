"""Strict adapters for three other actual ISTAT PDF publication layouts.

Fixture data here is synthetic *in shape*, and matched to the tables
visible on the official PDF. CI separately downloads every actual PDF
and fails if the source layout is not verified.
"""
import unittest

from scripts.pulse_research_new_domains import (
    SOURCES, demography_page, education_page,
    environment_page, demography_research_signals,
)
from scripts.pulse_research_comparisons import historical_signals, territorial_signals
from scripts.pulse_research_engine import research_report

SHA = "a" * 64

DEMOGRAPHY = """
INDICATORI DEMOGRAFICI
Popolazione in crescita al Nord e in calo nel Mezzogiorno
BILANCIO DELLA POPOLAZIONE RESIDENTE PER RIPARTIZIONE GEOGRAFICA.
Anno 2025 (a). Valori in migliaia.
RIPARTIZIONI Popolazione al 1 gennaio Nascite Decessi
Immigrati dall'estero Emigrati per l'estero Popolazione al 31 dicembre
Nord 27.513 167 306 239 79 840 801 27.574
Centro 11.699 64 132 88 26 259 253 11.699
Mezzogiorno 19.731 124 214 113 39 356 401 19.670
ITALIA 58.943 355 652 440 144 1.455 1.455 58.943
Fonte Istat Bilanci demografici dei comuni (dati provvisori)
"""

EDUCATION = """
LIVELLI DI ISTRUZIONE E RITORNI OCCUPAZIONALI
LIVELLI DI ISTRUZIONE E RITORNI OCCUPAZIONALI: I NUMERI CHIAVE.
Anni 2022, 2023 e 2024 valori percentuali
Livelli di istruzione della popolazione 2022 - Italia 2023 - Italia 2024 - Italia 2022 - Ue27 2023 - Ue27 2024 - Ue27
Quota di 25-64enni con almeno un titolo secondario superiore 63,0 65,5 66,7 79,4 79,8 80,5
Quota di 25-64enni con un titolo terziario 20,3 21,6 22,3 34,2 35,1 36,1
Quota di 25-34enni con un titolo terziario 29,2 30,6 31,6 42,0 43,1 44,1
Giovani 18-24 anni usciti precocemente dal sistema di istruzione e formazione 11,5 10,5 9,8 9,6 9,6 9,4
"""

ENVIRONMENT = """
RACCOLTA DIFFERENZIATA DEI RIFIUTI
RIFIUTI URBANI, RACCOLTA DIFFERENZIATA E SODDISFAZIONE DELLE FAMIGLIE
PER RIPARTIZIONE. Anni 2024-2025
RIPARTIZIONI Rifiuti urbani
(kg/abitante)
Raccolta differenziata (%)
Popolazione residente in comuni con almeno 65% di raccolta differenziata
Famiglie soddisfatte del servizio di raccolta porta a porta
Nord-ovest 502,7 71,3 70,2 73,0
Nord-est 577,1 77,8 89,3 74,3
Centro 538,2 63,2 53,2 68,4
Sud 451,7 59,9 47,7 73,3
Isole 455,5 60,8 62,8 73,6
Italia 507,7 67,7 64,7 72,6
"""


def source_doc(domain, findings, history=False):
    return {
        "id": "SAMPLE-" + domain,
        "public_source": {
            "url": SOURCES[domain],
            "role": "primary_statistical_source",
        },
        "source_sha256": SHA,
        "document_findings": [] if history else findings,
        "verified_series": findings if history else [],
    }


class NewDomainsTests(unittest.TestCase):
    def test_demography_eight_provisional_measures_not_exact_people(self):
        rows = demography_page(
            DEMOGRAPHY, SOURCES["popolazione"], SHA, 2
        )
        self.assertEqual(len(rows), 8)
        d = {r["indicator_code"]: r for r in rows}
        self.assertEqual(d["population_dec31"]["value"], 58943)
        self.assertEqual(d["births"]["value"], 355)
        self.assertEqual(d["deaths"]["value"], 652)
        self.assertTrue(all(r["rounded_at_thousands"] and r["provisional"]
                            and r["not_exact_individual_counts"] for r in rows))
        signals = demography_research_signals([
            source_doc("popolazione", rows)
        ])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["publication_status"], "research_only")
        self.assertEqual(
            research_report([source_doc("popolazione", rows)])["demography_signals"],
            signals,
        )

    def test_demography_incomplete_header_or_row_is_blocked(self):
        for text in (
            DEMOGRAPHY.replace("Valori in migliaia", "Valori esatti"),
            DEMOGRAPHY.replace("ITALIA 58.943", "ITALIA n.d."),
            DEMOGRAPHY.replace("Anno 2025", "Anno 2024"),
        ):
            self.assertEqual(demography_page(
                text, SOURCES["popolazione"], SHA, 2), [])

    def test_education_real_histories_italy_and_europe(self):
        rows = education_page(
            EDUCATION, SOURCES["istruzione"], SHA, 2
        )
        self.assertEqual(len(rows), 4)
        a = next(r for r in rows if r["territory"] == "Italia" and
                 r["population_scope"] == "residenti 25-64 anni")
        self.assertEqual(
            [x["value"] for x in a["observations"]], [20.3, 21.6, 22.3]
        )
        series = historical_signals([source_doc("istruzione", rows, True)])
        self.assertEqual(len(series), 4)
        self.assertTrue(all(x["periods"] == [2022, 2023, 2024]
                            for x in series))
        self.assertTrue(all(x["not_official_pulse_pattern"] for x in series))

    def test_education_ambiguous_history_refused(self):
        for text in (
            EDUCATION.replace("2024 - Italia", "2025 - Italia"),
            EDUCATION.replace("2022, 2023 e 2024", "2021, 2022 e 2024"),
            EDUCATION.replace("Quota di 25-34enni con un titolo terziario", "Non attestato"),
        ):
            self.assertEqual(education_page(
                text, SOURCES["istruzione"], SHA, 2), [])

    def test_environment_five_geographical_rates(self):
        rows = environment_page(
            ENVIRONMENT, SOURCES["ambiente"], SHA, 2
        )
        self.assertEqual(len(rows), 20)
        self.assertEqual(
            len([r for r in rows if r["indicator_code"] ==
                 "separate_waste_share"]), 5
        )
        env = territorial_signals([source_doc("ambiente", rows)])
        self.assertEqual(len(env), 4)
        collection = next(
            c for c in env if c["indicator"] ==
            "raccolta differenziata rifiuti urbani"
        )
        self.assertEqual(collection["low"]["name"], "Sud")
        self.assertEqual(collection["low"]["value"], "59.9")
        self.assertEqual(collection["high"]["name"], "Nord-est")
        self.assertEqual(collection["high"]["value"], "77.8")
        self.assertEqual(collection["gap_unit"], "percentage_points")
        self.assertEqual(collection["number_of_verified_territories"], 5)

    def test_env_no_population_mixing(self):
        rows = environment_page(
            ENVIRONMENT, SOURCES["ambiente"], SHA, 2
        )
        rows[0]["denominator_id"] = "different_population"
        comparisons = territorial_signals([source_doc("ambiente", rows)])
        # Four remain only if each has >=2 same-denominator rates;
        # mutated one is not compared against all other five.
        per_capita = next(x for x in comparisons
                          if x["indicator"] == "rifiuti urbani pro capite")
        self.assertEqual(per_capita["number_of_verified_territories"], 4)

    def test_environment_incomplete_table_refused(self):
        self.assertEqual(environment_page(
            ENVIRONMENT.replace("Isole 455,5 60,8 62,8 73,6", ""),
            SOURCES["ambiente"], SHA, 2), [])
        self.assertEqual(environment_page(
            ENVIRONMENT.replace("kg/abitante", "milioni"),
            SOURCES["ambiente"], SHA, 2), [])

    def test_source_integrity_rejects_nonofficial_url_and_hash(self):
        for domain, fn, text in (
            ("popolazione", demography_page, DEMOGRAPHY),
            ("istruzione", education_page, EDUCATION),
            ("ambiente", environment_page, ENVIRONMENT),
        ):
            self.assertEqual(fn(text, "https://example.com/a.pdf", SHA, 2), [])
            self.assertEqual(fn(text, SOURCES[domain], "invalid_sha", 2), [])


if __name__ == "__main__":
    unittest.main()
