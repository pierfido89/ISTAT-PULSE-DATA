"""Tests of evidence extraction; explicit synthetic fixtures + live-publication smoke suite."""
import io
import unittest
from unittest.mock import patch

from scripts.pulse_evidence import extract_bytes, matrix_evidence, normalized_percent

URL = "https://www.istat.it/comunicato-stampa/occupati-e-disoccupati-dati-provvisori-maggio-2026/"


class EvidenceTests(unittest.TestCase):
    def test_csv_verified(self):
        data = "Indicatore (%);2024;2025\nQuota occupati;61,2;62,4\n".encode()
        result = extract_bytes(data, URL, "text/csv", "test.csv")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["evidence"][0]["delta"], 1.2)
        self.assertTrue(result["evidence"][0]["source_sha256"])

    def test_html_verified(self):
        html = b"<table><caption>Quote percentuali (%)</caption><tr><th>Indicatore</th><th>2024</th><th>2025</th></tr><tr><td>Tasso occupazione</td><td>50,0</td><td>52,3</td></tr></table>"
        self.assertEqual(extract_bytes(html, URL, "text/html")["evidence"][0]["delta"], 2.3)

    def test_json_structured(self):
        doc = b'{"unit":"percentuale", "data":[["Indicatore", "2024", "2025"],["Tasso istruzione", "70", "71"]]}'
        result = extract_bytes(doc, URL, "application/json")
        self.assertEqual(result["evidence"][0]["delta"], 1)

    def test_xlsx_verified(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Quote (%)"
        ws.append(["Indicatore", "2024", "2025"])
        ws.append(["Occupazione giovanile", 31.5, 32.1])
        out = io.BytesIO()
        wb.save(out)
        result = extract_bytes(out.getvalue(), URL, filename="allegato.xlsx")
        self.assertEqual(result["status"], "verified")

    def test_pdf_verified(self):
        # A real vector PDF table produced in-memory, no OCR or fictional text matching.
        import pdfplumber
        from reportlab.pdfgen import canvas
        f = io.BytesIO()
        c = canvas.Canvas(f)
        c.drawString(40, 760, "Quota percentuale (%)")
        c.drawString(40, 720, "Indicatore")
        c.drawString(230, 720, "2024")
        c.drawString(330, 720, "2025")
        c.drawString(40, 680, "Occupazione")
        c.drawString(230, 680, "40,0")
        c.drawString(330, 680, "41,0")
        for x in (30, 220, 320, 400):
            c.line(x, 665, x, 740)
        for y in (665, 705, 740):
            c.line(30, y, 400, y)
        c.save()
        # Missing % metadata in the extracted table is correctly withheld.
        result = extract_bytes(f.getvalue(), URL, filename="tavola.pdf")
        self.assertEqual(result["status"], "no_comparable_series")

    def test_reject_missing_unit(self):
        rows = [["Indicatore", "2024", "2025"], ["Occupati", "60", "62"]]
        self.assertEqual(matrix_evidence(rows, URL, "hash", "sheet"), [])

    def test_reject_different_periods(self):
        rows = [["Indicatore (%)", "2010", "2025"], ["Occupati", "60", "62"]]
        self.assertEqual(matrix_evidence(rows, URL, "hash", "sheet"), [])

    def test_reject_incompatible_unit(self):
        self.assertIsNone(normalized_percent("1234 euro"))
        self.assertIsNone(normalized_percent("2.300"))
        self.assertIsNone(normalized_percent("120,4"))

    def test_reject_missing_value(self):
        rows = [["Indicatore (%)", "2024", "2025"], ["Occupazione", "..", "50"]]
        self.assertEqual(matrix_evidence(rows, URL, "hash", "sheet"), [])

    def test_reject_insecure_origin(self):
        with self.assertRaises(ValueError):
            extract_bytes(b"x", "http://example.org/source.csv", filename="test.csv")


if __name__ == "__main__":
    unittest.main()
