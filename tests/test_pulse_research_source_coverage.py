"""Source coverage guards: a live feed is not an independently verified fact."""
import unittest
from scripts.pulse_research_source_coverage import make_coverage


def fixtures():
    return (
        {"sources":[
            {"name":"ISPRA - indicators","url":"https://indicatoriambientali.isprambiente.it/","official":True,"integration_status":"feed"},
            {"name":"GSE - renewable","url":"https://www.gse.it/dati-e-scenari","official":True,"integration_status":"connected"},
            {"name":"Unofficial media","url":"https://example.com/","official":False,"integration_status":"feed"},
        ]},
        {"schema_version":"pulse-research-to-chatgpt-v1","publication_allowed":False,
         "stories":[{
             "story_id":"LABOR-01-TEST","domain":"labor",
             "source_url":"https://www.istat.it/wp-content/uploads/source.pdf",
             "source_sha256":"a"*64,
             "facts":[{"evidence_id":"E-LABOR-01-TEST-01","verified_structured_data":{"value":123}}],
         }]}
    )


class ResearchSourceCoverageTest(unittest.TestCase):
    def test_official_catalogue_not_equivalent_to_verified_pdfs(self):
        c,p=fixtures()
        result=make_coverage(c,p)
        self.assertEqual(result["catalogue_official_sources"],2)
        self.assertEqual(result["verified_primary_pdf_count"],1)
        self.assertEqual(result["verified_fact_count"],1)
        self.assertEqual(result["catalogue_status_distribution"],{"connected":1,"feed":1})
        self.assertTrue(all(x["research_intake"]=="candidate_only_unverified"
                            and x["numeric_research_verified"] is False
                            and x["editorial_publication_allowed"] is False
                            for x in result["sources"]))
        self.assertFalse(result["auto_publish"])

    def test_rejects_unverified_packet(self):
        c,p=fixtures()
        p["publication_allowed"]=True
        with self.assertRaises(ValueError): make_coverage(c,p)

    def test_rejects_duplicate_official_source_names(self):
        c,p=fixtures()
        c["sources"].append(dict(c["sources"][0]))
        with self.assertRaises(ValueError): make_coverage(c,p)

    def test_rejects_non_https_and_fake_provenance(self):
        c,p=fixtures()
        c["sources"][0]["url"]="http://example.com"
        with self.assertRaises(ValueError): make_coverage(c,p)
        c,p=fixtures()
        p["stories"][0]["source_sha256"]="unknown"
        with self.assertRaises(ValueError): make_coverage(c,p)


if __name__=="__main__":
    unittest.main()
