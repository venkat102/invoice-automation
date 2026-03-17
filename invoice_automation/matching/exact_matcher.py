"""Stage 1: Redis/memory exact lookups for invoice matching."""

from dataclasses import dataclass, field

import frappe

from invoice_automation.matching.normalizer import (
	extract_pan_from_gstin,
	normalize_gstin,
	normalize_item_text,
	normalize_text,
)


@dataclass
class MatchResult:
	matched: bool
	doctype: str
	matched_name: str | None = None
	confidence: float = 0.0
	stage: str = ""
	details: dict = field(default_factory=dict)

	def to_dict(self):
		return {
			"matched": self.matched,
			"doctype": self.doctype,
			"matched_name": self.matched_name,
			"confidence": self.confidence,
			"stage": self.stage,
			"details": self.details,
		}


REDIS_KEY_PREFIX = "invoice_automation"


class ExactMatcher:
	"""Stage 1: Uses Frappe's Redis to look up normalized values."""

	def _redis_lookup(self, doctype: str, normalized_value: str) -> str | None:
		if not normalized_value:
			return None
		key = f"{REDIS_KEY_PREFIX}:{doctype}:lookup:{normalized_value}"
		try:
			result = frappe.cache().get_value(key)
			return result
		except Exception:
			return None

	def match_supplier(self, extracted_data) -> MatchResult:
		"""Try GSTIN (100%), PAN (98%), normalized name (95%). Accepts dict or pydantic model."""
		doctype = "Supplier"

		gstin_raw = (
			extracted_data.get("supplier_gstin", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "supplier_gstin", "")
		) or ""

		supplier_name = (
			extracted_data.get("supplier_name", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "supplier_name", "")
		) or ""

		# GSTIN lookup (100% confidence)
		gstin = normalize_gstin(gstin_raw)
		if gstin:
			matched = self._redis_lookup(doctype, gstin)
			if matched:
				return MatchResult(
					matched=True, doctype=doctype, matched_name=matched,
					confidence=100.0, stage="Exact",
					details={"match_type": "gstin", "gstin": gstin},
				)

			# PAN lookup (98% confidence)
			pan = extract_pan_from_gstin(gstin)
			if pan:
				matched = self._redis_lookup(doctype, pan)
				if matched:
					return MatchResult(
						matched=True, doctype=doctype, matched_name=matched,
						confidence=98.0, stage="Exact",
						details={"match_type": "pan", "pan": pan},
					)

		# Normalized name lookup (95% confidence)
		normalized_name = normalize_text(supplier_name)
		if normalized_name:
			matched = self._redis_lookup(doctype, normalized_name)
			if matched:
				return MatchResult(
					matched=True, doctype=doctype, matched_name=matched,
					confidence=95.0, stage="Exact",
					details={"match_type": "name", "normalized": normalized_name},
				)

		return MatchResult(matched=False, doctype=doctype, stage="Exact")

	def match_item(self, line_item, supplier: str | None = None) -> MatchResult:
		"""Try item_code, barcode, manufacturer_part_no, normalized name."""
		doctype = "Item"

		description = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""

		hsn_code = (
			line_item.get("hsn_code", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "hsn_code", "")
		) or ""

		qty = (
			line_item.get("qty") if isinstance(line_item, dict) else getattr(line_item, "qty", None)
		)
		rate = (
			line_item.get("rate") if isinstance(line_item, dict) else getattr(line_item, "rate", None)
		)
		amount = (
			line_item.get("amount") if isinstance(line_item, dict) else getattr(line_item, "amount", None)
		)

		# Try normalized item name/description (95% confidence)
		normalized = normalize_item_text(description)
		if normalized:
			matched = self._redis_lookup(doctype, normalized)
			if matched:
				return MatchResult(
					matched=True, doctype=doctype, matched_name=matched,
					confidence=95.0, stage="Exact",
					details={
						"match_type": "name", "normalized": normalized,
						"raw_text": description, "qty": qty, "rate": rate,
						"amount": amount, "hsn_code": hsn_code,
					},
				)

		return MatchResult(
			matched=False, doctype=doctype, stage="Exact",
			details={
				"raw_text": description, "qty": qty, "rate": rate,
				"amount": amount, "hsn_code": hsn_code,
			},
		)

	def match_tax_template(self, tax_detail, supplier_gstin, company_gstin) -> MatchResult:
		"""Rule-based tax template lookup."""
		from invoice_automation.validation.tax_validator import match_tax_template

		result = match_tax_template(tax_detail, supplier_gstin, company_gstin)
		if result.get("matched_template"):
			return MatchResult(
				matched=True,
				doctype="Purchase Taxes and Charges Template",
				matched_name=result["matched_template"],
				confidence=result.get("confidence", 95.0),
				stage="Exact",
				details=result.get("details", {}),
			)
		return MatchResult(matched=False, doctype="Purchase Taxes and Charges Template", stage="Exact")
