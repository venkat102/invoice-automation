"""Unit tests for the extraction schema and JSON extractor."""

import json
import unittest

from invoice_automation.extraction.schema import ExtractedInvoiceData, ExtractedLineItem
from invoice_automation.extraction.json_extractor import JSONExtractor


SAMPLE_INVOICE = {
	"supplier_name": "Tata Steel Private Limited",
	"supplier_gstin": "27AAACT2727Q1ZW",
	"invoice_number": "INV-2024-001",
	"invoice_date": "2024-01-15",
	"line_items": [
		{
			"line_number": 1,
			"description": "Steel Rod 10mm TMT Bar",
			"qty": 100,
			"rate": 45.50,
			"amount": 4550.00,
			"hsn_code": "7214",
		},
		{
			"line_number": 2,
			"description": "Steel Plate 5mm",
			"qty": 50,
			"rate": 120.00,
			"amount": 6000.00,
		},
	],
	"taxes": [
		{"tax_type": "CGST", "rate": 9, "amount": 949.50},
		{"tax_type": "SGST", "rate": 9, "amount": 949.50},
	],
	"total_amount": 12449.00,
	"currency": "INR",
}


class TestExtractedInvoiceData(unittest.TestCase):
	def test_parse_valid_data(self):
		data = ExtractedInvoiceData(**SAMPLE_INVOICE)
		self.assertEqual(data.supplier_name, "Tata Steel Private Limited")
		self.assertEqual(data.supplier_gstin, "27AAACT2727Q1ZW")
		self.assertEqual(len(data.line_items), 2)
		self.assertEqual(data.line_items[0].description, "Steel Rod 10mm TMT Bar")
		self.assertEqual(data.total_amount, 12449.00)

	def test_optional_fields(self):
		minimal = {
			"supplier_name": "Test",
			"invoice_number": "INV-1",
			"invoice_date": "2024-01-01",
			"line_items": [{"line_number": 1, "description": "Item A"}],
			"total_amount": 100,
		}
		data = ExtractedInvoiceData(**minimal)
		self.assertIsNone(data.supplier_gstin)
		self.assertEqual(data.currency, "INR")


class TestJSONExtractor(unittest.TestCase):
	def test_from_dict(self):
		data = JSONExtractor.from_dict(SAMPLE_INVOICE)
		self.assertIsInstance(data, ExtractedInvoiceData)
		self.assertEqual(data.invoice_number, "INV-2024-001")

	def test_from_json_string(self):
		json_str = json.dumps(SAMPLE_INVOICE)
		data = JSONExtractor.from_json_string(json_str)
		self.assertIsInstance(data, ExtractedInvoiceData)
		self.assertEqual(len(data.line_items), 2)

	def test_supports_json_file(self):
		extractor = JSONExtractor()
		self.assertTrue(extractor.supports_file_type("invoice.json"))
		self.assertFalse(extractor.supports_file_type("invoice.pdf"))


if __name__ == "__main__":
	unittest.main()
