"""Offline contract tests for the real PULSE Editorial AI 1.0 pilot.

The Ollama replies are STUBBED; test runs cost zero AI tokens and no network.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_editorial_ai import (
    LocalOllama, _numbers_are_sourced, audit, candidates, main, MODEL_DEFAULT,
)

SOURCE = "https://www.istat.it/wp-content/uploads/2026/09/Statistica-Flash_II_Trimestre_2026.pdf"
SHA = "e" * 64

def finding(value=77611946, change=2.4, name="Presenze"):
    return {
        "indicator": name, "unit": "notti" if name == "Presenze" else "arrivi",
        "segment": {"structure": "Esercizi alberghieri", "residence": "totale"},
        "reference_period": "2026-Q2", "observed_total": value,
        "reported_yoy_change_pct": change,
        "source_url": SOURCE, "source_sha256": SHA, "location": "page:3:text:line:28",
        "extraction_method": "explicit_absolute_total_and_yoy_table",
        "editorial_status": "candidate_not_published", "verified": True,
    }

def primary(*items):
    return {
        "id": "PULSE-TEST-TURISMO",
        "public_source": {"url": SOURCE, "role": "primary_statistical_source"},
        "headline": "Flussi turistici: II trimestre 2026",
        "document_findings": list(items),
        "patterns": ["RECORD"], "pulse_score": 90,
        "publication_status": "published"
    }

PROPOSAL = {
    "headline": "Le presenze alberghiere aumentano nel secondo trimestre italiano",
    "lead": "Nel periodo 2026-Q2 le presenze negli alberghi raggiungono 77.611.946 notti, con una variazione tendenziale del +2,4%.",
    "body": ("Il confronto con lo stesso trimestre dell'anno precedente segnala una crescita "
             "delle presenze negli esercizi alberghieri. Il dato descrive il periodo "
             "considerato e, da solo, non prova una tendenza di lungo periodo."),
}

class CandidateTests(unittest.TestCase):
    def test_approved_primary_document_has_candidate(self):
        found = candidates(primary(finding()))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["evidence"]["value"], 77611946)

    def test_refuses_non_primary_or_journalistic_source(self):
        article = primary(finding())
        article["public_source"]["role"] = "journalistic_source"
        self.assertEqual(candidates(article), [])

    def test_refuses_cross_domain(self):
        bad = finding()
        bad["source_url"] = "https://unknown.example/data.csv"
        self.assertEqual(candidates(primary(bad)), [])

    def test_refuses_unverified_or_untraceable_values(self):
        for field, value in (("verified", False), ("source_sha256", None),
                             ("location", ""), ("reference_period", "2026"),
                             ("observed_total", float("nan"))):
            bad = finding()
            bad[field] = value
            self.assertEqual(candidates(primary(bad)), [], field)

    def test_deduplicates_repeated_pdf_lines(self):
        article = primary(finding(), finding(), finding(27648740, -2.5, "Arrivi"))
        found = candidates(article)
        self.assertEqual(len(found), 2)
        self.assertNotEqual(found[0]["candidate_id"], found[1]["candidate_id"])

    def test_never_reuses_unverified_pattern_or_score(self):
        c = candidates(primary(finding()))[0]
        result = audit(c, PROPOSAL)
        self.assertEqual(result["publication_status"], "draft_only")
        self.assertEqual(result["quality"]["status"], "review_required")
        self.assertEqual(result["patterns"], [])
        self.assertIsNone(result["pulse_score"])
        self.assertTrue(result["quality"]["requires_human_fact_check"])

    def test_rejects_unsupported_new_statistics(self):
        candidate = candidates(primary(finding()))[0]
        p = dict(PROPOSAL)
        p["body"] += " Le presenze raggiungono 95.000.000."
        result = audit(candidate, p)
        self.assertEqual(result["quality"]["status"], "rejected")
        self.assertTrue(any(i.startswith("unsourced_numbers") for i in result["quality"]["issues"]))

    def test_rejects_unsupported_record(self):
        candidate = candidates(primary(finding()))[0]
        p = dict(PROPOSAL)
        p["headline"] = "Record storico nelle presenze alberghiere del trimestre"
        self.assertEqual(audit(candidate, p)["quality"]["status"], "rejected")

    def test_rejects_missing_value(self):
        candidate = candidates(primary(finding()))[0]
        p = dict(PROPOSAL)
        p["lead"] = "Nel secondo trimestre le presenze negli alberghi aumentano rispetto all'anno prima."
        self.assertEqual(audit(candidate, p)["quality"]["status"], "rejected")

    def test_rejects_missing_yoy(self):
        candidate = candidates(primary(finding()))[0]
        p = dict(PROPOSAL)
        p["lead"] = p["lead"].replace("del +2,4%", "rispetto all'anno prima")
        self.assertEqual(audit(candidate, p)["quality"]["status"], "rejected")

    def test_no_external_url_from_model(self):
        candidate = candidates(primary(finding()))[0]
        p = dict(PROPOSAL)
        p["body"] += " Approfondisci su https://example.com"
        self.assertEqual(audit(candidate, p)["quality"]["status"], "rejected")

    def test_inspect_requires_no_model_or_writes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data.json"
            path.write_text(json.dumps({"articles": [primary(finding())]}))
            self.assertEqual(main(["--input", str(path), "--inspect"]), 0)
            self.assertFalse((Path(d)/"output.json").exists())

    def test_cli_writes_only_isolated_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "input.json"
            dest = Path(d) / "drafts.json"
            original = {"articles": [primary(finding())]}
            source.write_text(json.dumps(original))
            with patch.object(LocalOllama, "check", return_value=True), \
                 patch.object(LocalOllama, "generate", return_value=PROPOSAL):
                result = main(["--input", str(source), "--output", str(dest), "--limit", "1"])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(source.read_text()), original)
            draft = json.loads(dest.read_text())["drafts"][0]
            self.assertEqual(draft["quality"]["status"], "review_required")
            self.assertEqual(draft["publication_status"], "draft_only")

    def test_unavailable_model_does_not_create_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "input.json"
            dest = Path(d) / "output.json"
            source.write_text(json.dumps({"articles": [primary(finding())]}))
            with patch.object(LocalOllama, "check", return_value=False):
                code = main(["--input", str(source), "--output", str(dest)])
            self.assertEqual(code, 2)
            self.assertFalse(dest.exists())

    def test_forbids_live_feed_filename(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/"input.json"
            source.write_text(json.dumps({"articles": [primary(finding())]}))
            with self.assertRaises(SystemExit):
                main(["--input",str(source),"--output",str(Path(d)/"articles.json")])

if __name__ == "__main__":
    unittest.main()
