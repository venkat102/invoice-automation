"""Stage 2: Alias table lookups for invoice matching."""

import frappe

from invoice_automation.matching.exact_matcher import MatchResult
from invoice_automation.matching.normalizer import normalize_text


class AliasMatcher:
	"""Matches extracted text against stored aliases in the Mapping Alias doctype."""

	def match(
		self,
		raw_text: str,
		source_doctype: str,
		supplier: str | None = None,
	) -> MatchResult:
		normalized = normalize_text(raw_text)
		if not normalized:
			return MatchResult(matched=False, doctype=source_doctype, stage="Alias")

		# Supplier-specific alias (99% base confidence, scaled by decay_weight)
		if supplier:
			supplier_key = f"{supplier}:{normalized}:{source_doctype}"
			result, decay_weight = self._lookup_alias(supplier_key)
			if result:
				confidence = 99.0 * decay_weight
				return MatchResult(
					matched=True, doctype=source_doctype, matched_name=result,
					confidence=confidence, stage="Alias",
					details={"match_type": "supplier_specific", "composite_key": supplier_key, "decay_weight": decay_weight},
				)

		# Supplier-agnostic alias (90% base confidence, scaled by decay_weight)
		agnostic_key = f"ANY:{normalized}:{source_doctype}"
		result, decay_weight = self._lookup_alias(agnostic_key)
		if result:
			confidence = 90.0 * decay_weight
			return MatchResult(
				matched=True, doctype=source_doctype, matched_name=result,
				confidence=confidence, stage="Alias",
				details={"match_type": "supplier_agnostic", "composite_key": agnostic_key, "decay_weight": decay_weight},
			)

		return MatchResult(matched=False, doctype=source_doctype, stage="Alias")

	def _lookup_alias(self, composite_key: str) -> tuple[str | None, float]:
		"""Query Mapping Alias by composite_key. Try Redis first, then DB.

		Returns (canonical_name, decay_weight) tuple.
		"""
		# Try Redis cache for fast canonical name lookup
		redis_key = f"invoice_automation:alias:{composite_key}"
		canonical_name = None
		try:
			canonical_name = frappe.cache().get_value(redis_key)
		except Exception:
			pass

		# Get decay_weight from DB (always needed for confidence scaling)
		decay_weight = 1.0
		try:
			alias = frappe.db.get_value(
				"Mapping Alias",
				{"composite_key": composite_key, "is_active": 1},
				["name", "canonical_name", "decay_weight"],
				as_dict=True,
			)
			if alias:
				canonical_name = canonical_name or alias.canonical_name
				decay_weight = alias.decay_weight if alias.decay_weight else 1.0
				# Ensure Redis cache is populated
				try:
					frappe.cache().set_value(redis_key, alias.canonical_name)
				except Exception:
					pass
				self._update_last_used_by_name(alias.name)
		except Exception:
			pass

		if canonical_name:
			return canonical_name, decay_weight
		return None, 1.0

	def _update_last_used_by_name(self, name: str):
		try:
			frappe.db.set_value(
				"Mapping Alias", name, "last_used",
				frappe.utils.now_datetime(), update_modified=False,
			)
		except Exception:
			pass


class AliasMatcherStrategy:
	"""Pluggable strategy wrapper for AliasMatcher."""

	name = "Alias"
	applies_to = ["Supplier", "Item"]

	def __init__(self, config=None):
		self.config = config or {}
		self._matcher = AliasMatcher()

	def match_supplier(self, extracted_data):
		supplier_name = (
			extracted_data.get("supplier_name", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "supplier_name", "")
		) or ""
		return self._matcher.match(supplier_name, "Supplier", None)

	def match_item(self, line_item, supplier=None):
		raw_text = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""
		return self._matcher.match(raw_text, "Item", supplier)
