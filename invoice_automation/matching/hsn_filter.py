"""Matching strategy: HSN code-filtered fuzzy matching."""

import frappe
from thefuzz import fuzz

from invoice_automation.matching.exact_matcher import MatchResult
from invoice_automation.matching.normalizer import normalize_item_text


class HSNFilteredMatcher:
	"""Pre-filters candidate items by HSN code before fuzzy matching.

	When the extracted invoice line has an HSN/SAC code, this strategy narrows
	candidates to items sharing the same HSN code, then applies fuzzy matching
	on that narrowed set for higher precision.
	"""

	name = "HSN Filter"
	applies_to = ["Item"]

	def __init__(self, config=None):
		self.config = config or {}
		self.min_score = self.config.get("min_fuzzy_score", 60)
		self.confidence_boost = self.config.get("confidence_boost", 5)

	def match_supplier(self, extracted_data):
		return MatchResult(matched=False, doctype="Supplier", stage="HSN Filter")

	def match_item(self, line_item, supplier=None):
		hsn_code = (
			line_item.get("hsn_code", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "hsn_code", "")
		) or ""

		if not hsn_code:
			return MatchResult(matched=False, doctype="Item", stage="HSN Filter")

		description = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""

		if not description:
			return MatchResult(matched=False, doctype="Item", stage="HSN Filter")

		normalized_desc = normalize_item_text(description)
		if not normalized_desc:
			return MatchResult(matched=False, doctype="Item", stage="HSN Filter")

		# Find items with matching HSN code
		hsn_items = frappe.get_all(
			"Item",
			filters={"gst_hsn_code": hsn_code, "disabled": 0},
			fields=["name", "item_name"],
			limit=200,
		)

		if not hsn_items:
			# Try prefix match (first 4 digits)
			if len(hsn_code) >= 4:
				hsn_items = frappe.get_all(
					"Item",
					filters={"gst_hsn_code": ["like", f"{hsn_code[:4]}%"], "disabled": 0},
					fields=["name", "item_name"],
					limit=200,
				)

		if not hsn_items:
			return MatchResult(matched=False, doctype="Item", stage="HSN Filter")

		# Fuzzy match within HSN-filtered candidates
		best_match = None
		best_score = 0

		for item in hsn_items:
			item_normalized = normalize_item_text(item.item_name or item.name)
			if not item_normalized:
				continue

			token_sort = fuzz.token_sort_ratio(normalized_desc, item_normalized)
			partial = fuzz.partial_ratio(normalized_desc, item_normalized)
			token_set = fuzz.token_set_ratio(normalized_desc, item_normalized)
			score = max(token_sort, partial, token_set)

			if score > best_score:
				best_score = score
				best_match = item.name

		if best_match and best_score >= self.min_score:
			# HSN match provides a confidence boost over regular fuzzy
			if best_score >= 85:
				confidence = 75.0 + self.confidence_boost
			elif best_score >= 60:
				confidence = 60.0 + self.confidence_boost
			else:
				confidence = 55.0 + self.confidence_boost

			confidence = min(confidence, 89.0)

			return MatchResult(
				matched=True,
				doctype="Item",
				matched_name=best_match,
				confidence=round(confidence, 1),
				stage="HSN Filter",
				details={
					"hsn_code": hsn_code,
					"fuzzy_score": best_score,
					"candidates_count": len(hsn_items),
					"raw_text": description,
				},
			)

		return MatchResult(matched=False, doctype="Item", stage="HSN Filter")
