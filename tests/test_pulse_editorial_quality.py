import unittest
from scripts.pulse_editorial_evidence import enrich, source_metadata_from_text
from scripts.pulse_deep_tables import extract_mixed_table_rows
from scripts.pulse_evidence import matrix_evidence

SOURCE = "https://www.istat.it/dati/serie.csv"
def series(values, label="Arrivi"):
    return {
        "verified": True,
        "indicator": label,
        "unit": "%",
        "source_url": SOURCE,
        "extraction_method": "same_row_explicit_year_structured_table",
        "source_sha256": "f"*64,
        "location": "page:3:table:1:row:2",
        "observations": [{"period": str(2020+i), "value": v} for i,v in enumerate(values)]
    }
def article(patterns, values=None, headline="Il turismo in Italia"):
    return {"headline": headline, "summary": "Variazione tendenziale degli arrivi e delle presenze",
            "public_source": {"url": SOURCE}, "patterns": list(patterns),
            "verified_series": [series(values)] if values else [],
            "publication_status": "published", "pulse_score": 90}

class QualityGateTests(unittest.TestCase):
    def test_one_value_or_two_never_prove_record(self):
        a=article(["RECORD"], [30,40])
        enrich(a)
        self.assertEqual(a["patterns"], [])
        self.assertEqual(a["patterns_proposed"], ["RECORD"])
        self.assertEqual(a["pattern_validation_status"], "insufficient_evidence")
        self.assertEqual(a["pulse_score"], 90)

    def test_curated_record_with_no_series_is_not_certified(self):
        a=article(["RECORD"], headline="Pressione fiscale al 43,5% nel secondo trimestre")
        enrich(a)
        self.assertEqual(a["patterns"], [])
        self.assertEqual(a["publication_status"], "published")

    def test_unsupported_historical_superlative_requires_review(self):
        a=article(["RECORD"], [31,35], "Il mercato del lavoro resta su livelli record")
        enrich(a)
        self.assertEqual(a["publication_status"], "requires_quality_review")

    def test_true_record_needs_five_years(self):
        a=article(["RECORD"],[10,11,12,14,15])
        enrich(a)
        self.assertEqual(a["patterns"], ["RECORD"])
        self.assertEqual(len(a["pattern_evidence"]),1)

    def test_inversion_needs_previous_direction(self):
        a=article(["INVERSIONE"],[10,12,14,9])
        enrich(a)
        self.assertEqual(a["patterns"], ["INVERSIONE"])

    def test_methodological_mismatch_cannot_prove_pattern(self):
        a=article(["RECORD"],[1,2,3,4,5])
        a["verified_series"][0]["source_url"]="https://example.com/other.csv"
        enrich(a)
        self.assertEqual(a["patterns"], [])

    def test_two_independent_series_form_two_findings(self):
        a=article([], [30,33])
        a["verified_series"] += [series([50,58],"Presenze"), series([30,33],"Arrivi")]
        enrich(a)
        self.assertEqual(len(a["editorial_findings"]),2)
        self.assertEqual(a["findings_status"],"multiple_evidenced")
        self.assertEqual(a["editorial_findings"][0]["editorial_status"],"candidate_not_published")

    def test_next_release_needs_explicit_source(self):
        m=source_metadata_from_text("Dati provvisori. PROSSIMA DIFFUSIONE 23 novembre 2026")
        self.assertEqual(m["data_status"],"provisional")
        self.assertEqual(m["next_release_date"],"2026-11-23")
        other=source_metadata_from_text("Annuncio possibile a novembre")
        self.assertEqual(other["data_status"],"not_declared")
        self.assertIsNone(other["next_release_date"])

    def test_mixed_pdf_table_does_not_invent_baseline(self):
        table = [
            ["Esercizi alberghieri"],
            ["Totale","Arrivi","7.733.239","9.416.466","10.499.035","27.648.740","0,1","-0,3","-6,1","-2,5"],
            ["Totale","Presenze","19.802.014","24.522.478","33.287.454","77.611.946","-0,9","6,2","1,8","2,4"]
        ]
        findings=extract_mixed_table_rows(table,
            caption="PROSPETTO 1. Aprile-giugno 2026. Totale II trimestre. Valori assoluti e Variazioni % 2025-26",
            url=SOURCE, location="page:3:table:1", source_sha256="f"*64)
        self.assertEqual(len(findings),2)
        self.assertEqual(findings[0]["observed_total"],27648740.0)
        self.assertEqual(findings[1]["reported_yoy_change_pct"],2.4)
        self.assertNotIn("previous_value",findings[0])
        self.assertTrue(all(f["editorial_status"]=="candidate_not_published" for f in findings))

    def test_structured_five_year_histories_not_truncated(self):
        evidence=matrix_evidence(
            [["Indicatore", "2021", "2022", "2023", "2024", "2025"],
             ["Quota di presenze %", "20", "22", "25", "29", "35"]],
            SOURCE, "f"*64, "table:annual", "Quota (%)"
        )
        self.assertEqual(len(evidence),1)
        self.assertEqual(len(evidence[0]["observations"]),5)
        entry=article(["RECORD"])
        entry["verified_series"]=evidence
        enrich(entry)
        self.assertEqual(entry["patterns"], ["RECORD"])

    def test_mixed_table_requires_explicit_caption_and_segment(self):
        self.assertEqual(extract_mixed_table_rows(
            [["Totale","Arrivi","1","2","3","4","5","6","7","8"]],
            caption="Tabella generica",url=SOURCE,location="1",source_sha256="x"),[])

if __name__=="__main__":
    unittest.main()
