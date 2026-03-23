"""Unit tests for the extraction schema and JSON extractor."""

import json
import unittest

from invoice_automation.extraction.schema import ExtractedInvoice, ExtractedLineItem
from invoice_automation.extraction.json_extractor import JSONExtractor


SAMPLE_INVOICE = {
	"vendor_name": "Tata Steel Private Limited",
	"vendor_tax_id": "27AAACT2727Q1ZW",
	"invoice_number": "INV-2024-001",
	"invoice_date": "2024-01-15",
	"line_items": [
		{
			"line_number": 1,
			"description": "Steel Rod 10mm TMT Bar",
			"quantity": "100",
			"unit_price": "45.50",
			"line_total": "4550.00",
			"hsn_sac_code": "7214",
		},
		{
			"line_number": 2,
			"description": "Steel Plate 5mm",
			"quantity": "50",
			"unit_price": "120.00",
			"line_total": "6000.00",
		},
	],
	"tax_details": [
		{"tax_type": "CGST", "rate": 9, "amount": 949.50},
		{"tax_type": "SGST", "rate": 9, "amount": 949.50},
	],
	"total_amount": "12449.00",
	"currency": "INR",
}


class TestExtractedInvoice(unittest.TestCase):
	def test_parse_valid_data(self):
		data = ExtractedInvoice(**SAMPLE_INVOICE)
		self.assertEqual(data.vendor_name, "Tata Steel Private Limited")
		self.assertEqual(data.vendor_tax_id, "27AAACT2727Q1ZW")
		self.assertEqual(len(data.line_items), 2)
		self.assertEqual(data.line_items[0].description, "Steel Rod 10mm TMT Bar")
		self.assertEqual(data.total_amount, "12449.00")

	def test_optional_fields(self):
		minimal = {
			"vendor_name": "Test",
			"invoice_number": "INV-1",
			"invoice_date": "2024-01-01",
			"line_items": [{"line_number": 1, "description": "Item A"}],
			"total_amount": "100",
		}
		data = ExtractedInvoice(**minimal)
		self.assertIsNone(data.vendor_tax_id)
		self.assertIsNone(data.currency)

	def test_line_item_fields(self):
		item = ExtractedLineItem(
			line_number=1, description="Test Item",
			quantity="10", unit_price="50.00", line_total="500.00",
			hsn_sac_code="7214",
		)
		self.assertEqual(item.quantity, "10")
		self.assertEqual(item.hsn_sac_code, "7214")


class TestJSONExtractor(unittest.TestCase):
	def test_from_dict(self):
		data = JSONExtractor.from_dict(SAMPLE_INVOICE)
		self.assertIsInstance(data, ExtractedInvoice)
		self.assertEqual(data.invoice_number, "INV-2024-001")

	def test_from_json_string(self):
		json_str = json.dumps(SAMPLE_INVOICE)
		data = JSONExtractor.from_json_string(json_str)
		self.assertIsInstance(data, ExtractedInvoice)
		self.assertEqual(len(data.line_items), 2)

	def test_supports_json_file(self):
		extractor = JSONExtractor()
		self.assertTrue(extractor.supports_file_type("invoice.json"))
		self.assertFalse(extractor.supports_file_type("invoice.pdf"))


if __name__ == "__main__":
	unittest.main()
