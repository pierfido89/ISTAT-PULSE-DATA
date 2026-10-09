import unittest
from scripts.pulse_evidence_adapters import (
    discover_attachments, compare_observations, parse_sdmx_csv
)

URL = "https://www.istat.it/comunicati/dati.html"

class Phase2Tests(unittest.TestCase):
    def test_attachment_discovery_same_host_only(self):
        html = b'<a href="/files/tavola.xlsx">Scarica</a><a href="https://other.org/data.pdf">esterno</a>'
        self.assertEqual(discover_attachments(html, URL), ["https://www.istat.it/files/tavola.xlsx"])

    def test_non_percent_absolute_units(self):
        x = compare_observations(
            [{"period":"2024","value":"12000"}, {"period":"2025","value":"12300"}],
            source_url=URL, dataset="d1", indicator="occupati", unit="persone",
            territory="IT", method_id="m1")
        self.assertEqual(x["status"], "verified")
        self.assertEqual(x["delta"], 300)

    def test_method_break_blocks(self):
        x = compare_observations(
            [{"period":"2024","value":40}, {"period":"2025","value":45}],
            source_url=URL, dataset="d1", indicator="quota", unit="%",
            territory="IT", method_id="m1", revision_notes="Rottura di serie 2025")
        self.assertEqual(x["reason"], "methodological_break")

    def test_missing_dimension_blocks(self):
        x = compare_observations(
            [{"period":"2024","value":40}, {"period":"2025","value":45}],
            source_url=URL, dataset="d1", indicator="quota", unit="%",
            territory="", method_id="m1")
        self.assertEqual(x["reason"], "missing_dimensions")

    def test_gap_blocks(self):
        x = compare_observations(
            [{"period":"2023","value":40}, {"period":"2025","value":45}],
            source_url=URL, dataset="d1", indicator="quota", unit="%",
            territory="IT", method_id="m1")
        self.assertEqual(x["reason"], "non_adjacent_years")

    def test_sdmx_multidimensional_no_mixing(self):
        text = ("DATAFLOW,INDICATOR,UNIT_MEASURE,REF_AREA,METHODOLOGY,TIME_PERIOD,OBS_VALUE\n"
                "flow,employment,persons,IT,m1,2024,100\n"
                "flow,employment,persons,IT,m1,2025,140\n"
                "flow,employment,persons,FR,m1,2024,900\n"
                "flow,employment,persons,FR,m1,2025,950\n")
        x = parse_sdmx_csv(text.encode(), URL)
        self.assertEqual(x["status"], "verified")
        self.assertEqual(sorted(y["delta"] for y in x["evidence"]), [40, 50])

    def test_sdmx_reject_missing_methodology(self):
        text = ("DATAFLOW,INDICATOR,UNIT_MEASURE,REF_AREA,TIME_PERIOD,OBS_VALUE\n"
                "flow,employment,persons,IT,2024,100\n"
                "flow,employment,persons,IT,2025,140\n")
        self.assertEqual(parse_sdmx_csv(text.encode(), URL)["status"], "no_comparable_series")

if __name__ == "__main__":
    unittest.main()
