"""Matching strategy: lookup vendor-specific item codes (SKUs)."""

import frappe

from invoice_automation.matching.exact_matcher import MatchResult


class VendorSKUMatcher:
	"""Matches extracted item codes against Vendor SKU Mapping records.

	When a vendor prints their own item code on the invoice, this strategy
	looks it up in the Vendor SKU Mapping table for an exact match.
	"""

	name = "Vendor SKU"
	applies_to = ["Item"]

	def __init__(self, config=None):
		self.config = config or {}

	def match_supplier(self, extracted_data):
		return MatchResult(matched=False, doctype="Supplier", stage="Vendor SKU")

	def match_item(self, line_item, supplier=None):
		if not supplier:
			return MatchResult(matched=False, doctype="Item", stage="Vendor SKU")

		# Get item_code from the line item (vendor's SKU printed on invoice)
		item_code = (
			line_item.get("item_code", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "item_code", "")
		) or ""

		if not item_code:
			return MatchResult(matched=False, doctype="Item", stage="Vendor SKU")

		# Look up in Vendor SKU Mapping
		mapping = frappe.db.get_value(
			"Vendor SKU Mapping",
			{"supplier": supplier, "vendor_item_code": item_code},
			["item", "occurrence_count"],
			as_dict=True,
		)

		if mapping and mapping.item:
			return MatchResult(
				matched=True,
				doctype="Item",
				matched_name=mapping.item,
				confidence=97.0,
				stage="Vendor SKU",
				details={
					"vendor_item_code": item_code,
					"occurrence_count": mapping.occurrence_count,
				},
			)

		return MatchResult(matched=False, doctype="Item", stage="Vendor SKU")
