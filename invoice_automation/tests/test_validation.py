"""Unit tests for validation modules."""

import unittest
from unittest.mock import patch

from invoice_automation.validation.amount_validator import validate_amounts
from invoice_automation.validation.tax_validator import validate_tax_consistency


class TestAmountValidator(unittest.TestCase):
	@patch("invoice_automation.validation.amount_validator.get_config_value")
	def test_matching_totals(self, mock_config):
		mock_config.return_value = 1.0

		extracted = {"total_amount": 1000.0}
		line_items = [
			{"qty": 10, "rate": 50, "tax_rate": 0},
			{"qty": 5, "rate": 100, "tax_rate": 0},
		]

		result = validate_amounts(extracted, line_items)
		self.assertTrue(result["is_valid"])
		self.assertEqual(result["computed_subtotal"], 1000.0)

	@patch("invoice_automation.validation.amount_validator.get_config_value")
	def test_mismatching_totals(self, mock_config):
		mock_config.return_value = 1.0

		extracted = {"total_amount": 1200.0}
		line_items = [
			{"qty": 10, "rate": 50, "tax_rate": 0},
		]

		result = validate_amounts(extracted, line_items)
		self.assertFalse(result["is_valid"])
		self.assertEqual(result["difference"], 700.0)

	@patch("invoice_automation.validation.amount_validator.get_config_value")
	def test_with_tax(self, mock_config):
		mock_config.return_value = 1.0

		extracted = {"total_amount": 1180.0}
		line_items = [
			{"qty": 10, "rate": 100, "tax_rate": 18},
		]

		result = validate_amounts(extracted, line_items)
		self.assertTrue(result["is_valid"])
		self.assertEqual(result["computed_total"], 1180.0)


class TestTaxConsistency(unittest.TestCase):
	def test_valid_intra_state(self):
		taxes = [
			{"tax_type": "CGST", "rate": 9},
			{"tax_type": "SGST", "rate": 9},
		]
		result = validate_tax_consistency(taxes, "27AAACT2727Q1ZW", "27BBBCT3333Q1ZX")
		self.assertTrue(result["is_valid"])

	def test_mixing_igst_cgst(self):
		taxes = [
			{"tax_type": "IGST", "rate": 18},
			{"tax_type": "CGST", "rate": 9},
		]
		result = validate_tax_consistency(taxes, "27AAACT2727Q1ZW", "27BBBCT3333Q1ZX")
		self.assertFalse(result["is_valid"])
		self.assertIn("Cannot mix IGST with CGST/SGST", result["errors"])

	def test_unequal_cgst_sgst(self):
		taxes = [
			{"tax_type": "CGST", "rate": 9},
			{"tax_type": "SGST", "rate": 6},
		]
		result = validate_tax_consistency(taxes, "27AAACT2727Q1ZW", "27BBBCT3333Q1ZX")
		self.assertFalse(result["is_valid"])


if __name__ == "__main__":
	unittest.main()
