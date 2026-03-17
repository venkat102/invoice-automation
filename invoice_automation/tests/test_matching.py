"""Unit tests for the matching stages and pipeline."""

import unittest
from unittest.mock import patch, MagicMock

from invoice_automation.matching.exact_matcher import MatchResult


class TestMatchResult(unittest.TestCase):
	def test_no_match(self):
		result = MatchResult(matched=False, doctype="Item")
		self.assertFalse(result.matched)
		self.assertEqual(result.confidence, 0.0)

	def test_to_dict(self):
		result = MatchResult(
			matched=True, doctype="Supplier", matched_name="SUP-001",
			confidence=95.0, stage="Exact", details={"match_type": "gstin"},
		)
		d = result.to_dict()
		self.assertTrue(d["matched"])
		self.assertEqual(d["matched_name"], "SUP-001")
		self.assertEqual(d["confidence"], 95.0)


class TestConfidenceRouting(unittest.TestCase):
	@patch("invoice_automation.matching.confidence.frappe")
	def test_auto_create(self, mock_frappe):
		mock_frappe.get_cached_doc.side_effect = Exception("no config")
		from invoice_automation.matching.confidence import determine_routing

		self.assertEqual(determine_routing([95.0, 92.0, 98.0]), "Auto Create")

	@patch("invoice_automation.matching.confidence.frappe")
	def test_review_queue(self, mock_frappe):
		mock_frappe.get_cached_doc.side_effect = Exception("no config")
		from invoice_automation.matching.confidence import determine_routing

		self.assertEqual(determine_routing([75.0, 92.0]), "Review Queue")

	@patch("invoice_automation.matching.confidence.frappe")
	def test_manual_entry(self, mock_frappe):
		mock_frappe.get_cached_doc.side_effect = Exception("no config")
		from invoice_automation.matching.confidence import determine_routing

		self.assertEqual(determine_routing([30.0, 92.0]), "Manual Entry")

	@patch("invoice_automation.matching.confidence.frappe")
	def test_empty_confidences(self, mock_frappe):
		mock_frappe.get_cached_doc.side_effect = Exception("no config")
		from invoice_automation.matching.confidence import determine_routing

		self.assertEqual(determine_routing([]), "Manual Entry")


class TestFuzzyMatcher(unittest.TestCase):
	@patch("invoice_automation.matching.fuzzy_matcher.frappe")
	def test_fuzzy_match(self, mock_frappe):
		mock_frappe.get_cached_doc.side_effect = Exception("no config")
		mock_frappe.get_all.return_value = [
			{"name": "Steel Rod 10mm", "item_name": "Steel Rod 10mm", "description": ""},
			{"name": "Copper Wire 5mm", "item_name": "Copper Wire 5mm", "description": ""},
		]

		from invoice_automation.matching.fuzzy_matcher import FuzzyMatcher

		FuzzyMatcher.clear_cache()
		matcher = FuzzyMatcher()
		result = matcher.match("Steel Rod 10 mm", "Item")

		self.assertTrue(result.matched)
		self.assertEqual(result.matched_name, "Steel Rod 10mm")
		self.assertEqual(result.stage, "Fuzzy")
		self.assertGreater(result.confidence, 60)


class TestLLMMatcher(unittest.TestCase):
	def test_disabled_llm(self):
		with patch("invoice_automation.matching.llm_matcher.frappe") as mock_frappe, \
			patch("invoice_automation.matching.llm_matcher.get_config") as mock_config:
			mock_config.return_value = {"enable_lm_matching": False}

			from invoice_automation.matching.llm_matcher import LLMMatcher

			matcher = LLMMatcher()
			result = matcher.match("test", "Item", None, ["Item1"], [])
			self.assertFalse(result.matched)
			self.assertIn("disabled", result.details.get("reason", ""))

	def test_parse_valid_response(self):
		from invoice_automation.matching.llm_matcher import LLMMatcher

		matcher = LLMMatcher()
		result = matcher._parse_response(
			'{"matched_item": "ITEM-001", "confidence": 85, "reasoning": "Good match"}',
			"Item",
		)
		self.assertTrue(result.matched)
		self.assertEqual(result.matched_name, "ITEM-001")
		self.assertLessEqual(result.confidence, 88)  # Capped

	def test_parse_no_match(self):
		from invoice_automation.matching.llm_matcher import LLMMatcher

		matcher = LLMMatcher()
		result = matcher._parse_response(
			'{"matched_item": "NO_MATCH", "confidence": 0, "reasoning": "No match found"}',
			"Item",
		)
		self.assertFalse(result.matched)


if __name__ == "__main__":
	unittest.main()
