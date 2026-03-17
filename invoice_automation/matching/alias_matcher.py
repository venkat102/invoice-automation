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

		# Supplier-specific alias (99% confidence)
		if supplier:
			supplier_key = f"{supplier}:{normalized}:{source_doctype}"
			result = self._lookup_alias(supplier_key)
			if result:
				return MatchResult(
					matched=True, doctype=source_doctype, matched_name=result,
					confidence=99.0, stage="Alias",
					details={"match_type": "supplier_specific", "composite_key": supplier_key},
				)

		# Supplier-agnostic alias (90% confidence)
		agnostic_key = f"ANY:{normalized}:{source_doctype}"
		result = self._lookup_alias(agnostic_key)
		if result:
			return MatchResult(
				matched=True, doctype=source_doctype, matched_name=result,
				confidence=90.0, stage="Alias",
				details={"match_type": "supplier_agnostic", "composite_key": agnostic_key},
			)

		return MatchResult(matched=False, doctype=source_doctype, stage="Alias")

	def _lookup_alias(self, composite_key: str) -> str | None:
		"""Query Mapping Alias by composite_key. Try Redis first, then DB."""
		# Try Redis cache
		redis_key = f"invoice_automation:alias:{composite_key}"
		try:
			cached = frappe.cache().get_value(redis_key)
			if cached:
				self._update_last_used(composite_key)
				return cached
		except Exception:
			pass

		# Fallback to DB
		try:
			alias = frappe.db.get_value(
				"Mapping Alias",
				{"composite_key": composite_key, "is_active": 1},
				["name", "canonical_name"],
				as_dict=True,
			)
			if alias:
				# Cache for next time
				try:
					frappe.cache().set_value(redis_key, alias.canonical_name)
				except Exception:
					pass
				self._update_last_used_by_name(alias.name)
				return alias.canonical_name
		except Exception:
			pass

		return None

	def _update_last_used(self, composite_key: str):
		try:
			frappe.db.set_value(
				"Mapping Alias",
				{"composite_key": composite_key},
				"last_used",
				frappe.utils.now_datetime(),
				update_modified=False,
			)
		except Exception:
			pass

	def _update_last_used_by_name(self, name: str):
		try:
			frappe.db.set_value(
				"Mapping Alias", name, "last_used",
				frappe.utils.now_datetime(), update_modified=False,
			)
		except Exception:
			pass
