"""Unit tests for the text normalizer."""

import unittest

from invoice_automation.matching.normalizer import (
	normalize_text,
	normalize_gstin,
	extract_pan_from_gstin,
	normalize_item_text,
)


class TestNormalizeText(unittest.TestCase):
	def test_basic_normalization(self):
		self.assertEqual(normalize_text("  hello  world  "), "HELLO WORLD")

	def test_removes_punctuation(self):
		result = normalize_text("Hello, World! (Test)")
		self.assertNotIn(",", result)
		self.assertNotIn("!", result)

	def test_removes_company_suffixes(self):
		self.assertEqual(normalize_text("Tata Steel Private Limited"), "TATA STEEL")
		self.assertEqual(normalize_text("Acme Corp Ltd"), "ACME CORP")
		self.assertEqual(normalize_text("XYZ Pvt Ltd"), "XYZ")

	def test_empty_string(self):
		self.assertEqual(normalize_text(""), "")
		self.assertEqual(normalize_text(None), "")

	def test_collapses_whitespace(self):
		self.assertEqual(normalize_text("a   b    c"), "A B C")


class TestNormalizeGstin(unittest.TestCase):
	def test_valid_gstin(self):
		self.assertEqual(normalize_gstin("27AAACT2727Q1ZW"), "27AAACT2727Q1ZW")

	def test_strips_special_chars(self):
		self.assertEqual(normalize_gstin("27-AAAC-T2727-Q1ZW"), "27AAACT2727Q1ZW")

	def test_invalid_length(self):
		# Returns empty string for non-15-char input
		self.assertEqual(normalize_gstin("12345"), "")

	def test_empty(self):
		self.assertEqual(normalize_gstin(""), "")
		self.assertEqual(normalize_gstin(None), "")


class TestExtractPan(unittest.TestCase):
	def test_valid_gstin(self):
		self.assertEqual(extract_pan_from_gstin("27AAACT2727Q1ZW"), "AAACT2727Q")

	def test_invalid_gstin(self):
		self.assertIsNone(extract_pan_from_gstin(""))
		self.assertIsNone(extract_pan_from_gstin("12345"))


class TestNormalizeItemText(unittest.TestCase):
	def test_removes_unit_info(self):
		result = normalize_item_text("Steel Rods 10 KG Pack")
		self.assertNotIn("KG", result)

	def test_basic_normalization_applied(self):
		result = normalize_item_text("test item ltd")
		self.assertEqual(result, "TEST ITEM")


if __name__ == "__main__":
	unittest.main()
