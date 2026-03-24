"""Matching strategy: match items based on purchase history from Supplier Item Catalog."""

import frappe
from thefuzz import fuzz

from invoice_automation.matching.exact_matcher import MatchResult
from invoice_automation.matching.normalizer import normalize_item_text


class PurchaseHistoryMatcher:
	"""Matches line items against items this supplier has sold before.

	Uses the Supplier Item Catalog (populated from Purchase Invoices and corrections)
	to narrow candidates, then applies fuzzy matching on the narrowed set.
	"""

	name = "Purchase History"
	applies_to = ["Item"]

	def __init__(self, config=None):
		self.config = config or {}
		self.min_fuzzy_score = self.config.get("min_fuzzy_score", 70)

	def match_supplier(self, extracted_data):
		return MatchResult(matched=False, doctype="Supplier", stage="Purchase History")

	def match_item(self, line_item, supplier=None):
		if not supplier:
			return MatchResult(matched=False, doctype="Item", stage="Purchase History")

		description = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""

		if not description:
			return MatchResult(matched=False, doctype="Item", stage="Purchase History")

		normalized_desc = normalize_item_text(description)
		if not normalized_desc:
			return MatchResult(matched=False, doctype="Item", stage="Purchase History")

		# Get items this supplier has sold before
		catalog_entries = frappe.get_all(
			"Supplier Item Catalog",
			filters={"supplier": supplier},
			fields=["item", "item_group", "occurrence_count", "avg_rate"],
			order_by="occurrence_count desc",
			limit=100,
		)

		if not catalog_entries:
			return MatchResult(matched=False, doctype="Item", stage="Purchase History")

		# Get item names for fuzzy matching
		item_names = {}
		for entry in catalog_entries:
			item_name = frappe.db.get_value("Item", entry.item, "item_name")
			if item_name:
				item_names[entry.item] = {
					"item_name": item_name,
					"normalized": normalize_item_text(item_name),
					"occurrence_count": entry.occurrence_count or 1,
					"avg_rate": entry.avg_rate,
				}

		if not item_names:
			return MatchResult(matched=False, doctype="Item", stage="Purchase History")

		# Fuzzy match against catalog items
		best_match = None
		best_score = 0

		for item_code, info in item_names.items():
			if not info["normalized"]:
				continue

			token_sort = fuzz.token_sort_ratio(normalized_desc, info["normalized"])
			partial = fuzz.partial_ratio(normalized_desc, info["normalized"])
			score = max(token_sort, partial)

			# Boost score based on frequency (items bought often are more likely)
			frequency_boost = min(info["occurrence_count"] * 0.5, 5)
			adjusted_score = score + frequency_boost

			if adjusted_score > best_score:
				best_score = adjusted_score
				best_match = item_code
				best_info = info

		if best_match and best_score >= self.min_fuzzy_score:
			# Map score to confidence: 70-100 score → 70-85% confidence
			confidence = 70.0 + (min(best_score, 100) - 70) * (15.0 / 30.0)
			confidence = min(confidence, 85.0)

			return MatchResult(
				matched=True,
				doctype="Item",
				matched_name=best_match,
				confidence=round(confidence, 1),
				stage="Purchase History",
				details={
					"fuzzy_score": best_score,
					"occurrence_count": best_info["occurrence_count"],
					"avg_rate": float(best_info["avg_rate"] or 0),
					"raw_text": description,
				},
			)

		return MatchResult(matched=False, doctype="Item", stage="Purchase History")
