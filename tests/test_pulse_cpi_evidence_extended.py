"""Golden table regression, original PDF SHA and ten separate source facts.

Fixtures are NOT substitutes for live source verification in GitHub Actions.
"""
import copy
import unittest
from scripts.pulse_cpi_evidence_extended import (
    PINNED_SOURCE_SHA256, PRICE_STORY_ID, add_to_research_packet,
    table_rows, from_original_pdf
)

PDF_TABLE = """PREZZI AL CONSUMO
LE TIPOLOGIE DI PRODOTTO
PROSPETTO 3. INDICE DEI PREZZI AL CONSUMO NIC PER TIPOLOGIA DI PRODOTTO
Agosto 2026, pesi e variazioni congiunturali e tendenziali percentuali (base 2025=100)
TIPOLOGIE DI PRODOTTO Pesi
Variazioni congiunturali* Variazioni tendenziali Inflazione
Beni energetici, di cui: 105.124 +2,9 -1,9 +17,1 +11,6 +9,6
Energetici regolamentati 6.982 +3,0 -0,3 +18,6 +14,8 +10,1
Energetici non regolamentati 98.142 +2,9 -2,1 +17,0 +11,4 +9,5
Beni 557.656 +0,7 -0,2 +4,1 +3,2 +2,9
Servizi 442.344 +0,2 +0,5 +2,4 +2,7 +2,9
Indice generale 1.000.000 +0,5 +0,1 +3,3 +2,9 +2,9
Indice generale al netto degli energetici e alimentari freschi
(Componente di fondo) 825.043 +0,2 +0,3 +1,5 +1,6 +1,9
Indice generale al netto degli energetici 894.876 +0,2 +0,3 +1,7 +1,8 +2,1
Indice dei beni alimentari, per la cura della casa e della persona 204.361 +0,1 +0,2 +0,9 +1,0 +1,4
*Le variazioni percentuali congiunturali dell’anno precedente si riferiscono alle serie ricostruite secondo la ECOICOPv2.
"""


def source_packet():
    sha=PINNED_SOURCE_SHA256
    def f(code, i):
        return {"evidence_id":f"E-{PRICE_STORY_ID}-{i:02d}",
                "source_sha256":sha,"source_url":"https://www.istat.it/a.pdf",
                "source_locations":[f"page:2:text:line:{i}"],
                "verified_structured_data":{"price_index_code":code}}
    return {"schema_version":"pulse-research-to-chatgpt-v1",
            "publication_allowed":False,"human_review_required":True,
            "stories":[{"story_id":PRICE_STORY_ID,"source_sha256":sha,
                        "facts":[f("NIC",1),f("IPCA",2),f("FOI",3)]},
                        {"story_id":"OTHER","source_sha256":"f"*64,"facts":[{"id":"OTHER"}]}]}


class ExpandedCPITests(unittest.TestCase):
    def get_facts(self):
        return table_rows(PDF_TABLE,PINNED_SOURCE_SHA256,page_no=4)

    def test_ten_exact_rows_with_distinct_ids_and_source_positions(self):
        facts=self.get_facts()
        self.assertEqual(len(facts),10)
        self.assertEqual(len({f["evidence_id"] for f in facts}),10)
        self.assertTrue(all(f["source_locations"][0].startswith("page:4:text:line:")
                            for f in facts))
        values={f["verified_structured_data"]["indicator_code"]:
                f["verified_structured_data"] for f in facts}
        self.assertEqual((values["ENERGY_TOTAL"]["reported_yoy_change_pct"],
                          values["ENERGY_TOTAL"]["previous_month_yoy_change_pct"]), (17.1,11.6))
        self.assertEqual(values["SERVICES_MINUS_GOODS"]["difference_current_pp"],-1.7)
        self.assertEqual(values["SERVICES_MINUS_GOODS"]["difference_previous_pp"],-0.5)

    def test_official_source_integrity_or_missing_row_fails_closed(self):
        with self.assertRaises(ValueError):
            table_rows(PDF_TABLE,"f"*64)
        with self.assertRaises(ValueError):
            table_rows(PDF_TABLE.replace("PROSPETTO 3.", "PROSPETTO 6."),
                       PINNED_SOURCE_SHA256)
        with self.assertRaises(ValueError):
            table_rows(PDF_TABLE.replace(
                "Energetici regolamentati 6.982 +3,0 -0,3 +18,6 +14,8 +10,1", ""),
                PINNED_SOURCE_SHA256)

    def test_fake_price_positive_should_fail_acceptance(self):
        with self.assertRaises(ValueError):
            table_rows(PDF_TABLE.replace("+17,1 +11,6", "+18,4 +11,6"),PINNED_SOURCE_SHA256)
        with self.assertRaises(ValueError):
            table_rows(PDF_TABLE.replace("+0,9 +1,0", "+9,9 +1,0"),PINNED_SOURCE_SHA256)

    def test_rejoin_core_wrapped_row_without_inventing(self):
        values={x["verified_structured_data"]["indicator_code"]:
                x["verified_structured_data"] for x in self.get_facts()}
        self.assertEqual(values["CORE"]["reported_yoy_change_pct"],1.5)
        self.assertEqual(values["EX_ENERGY"]["previous_month_yoy_change_pct"],1.8)

    def test_merge_keeps_other_domains_and_original_packet_immutable(self):
        original=source_packet()
        saved=copy.deepcopy(original)
        supplement={"schema_version":"pulse-cpi-extended-evidence-v1",
                    "publication_allowed":False,
                    "source_sha256":PINNED_SOURCE_SHA256,
                    "facts":self.get_facts()}
        merged=add_to_research_packet(original,supplement)
        self.assertEqual(original,saved)
        self.assertEqual(len(merged["stories"]),2)
        self.assertEqual(len(merged["stories"][0]["facts"]),13)
        self.assertFalse(merged["publication_allowed"])
        self.assertTrue(merged["human_review_required"])
        supplement["facts"][0]["evidence_id"]=supplement["facts"][1]["evidence_id"]
        with self.assertRaises(ValueError):
            add_to_research_packet(original,supplement)

    def test_real_pdf_text_order_uses_label_numbers_then_parenthesized_suffix(self):
        actual=PDF_TABLE.replace(
            "Indice generale al netto degli energetici e alimentari freschi\\n"
            "(Componente di fondo) 825.043 +0,2 +0,3 +1,5 +1,6 +1,9",
            "Indice generale al netto degli energetici e alimentari freschi\\n"
            "825.043 +0,2 +0,3 +1,5 +1,6 +1,9\\n"
            "(Componente di fondo)")
        self.assertEqual(len(table_rows(actual,PINNED_SOURCE_SHA256)),10)
        missing=actual.replace("(Componente di fondo)", "(Componente mancante)")
        with self.assertRaises(ValueError):
            table_rows(missing,PINNED_SOURCE_SHA256)

    def test_invalid_pdf_never_returns_fake_evidence(self):
        with self.assertRaises(ValueError):
            from_original_pdf(b"Not a PDF")


if __name__=="__main__":
    unittest.main()
