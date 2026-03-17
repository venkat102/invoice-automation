"""Stage 3: thefuzz-based fuzzy matching for invoice matching."""

import frappe
from thefuzz import fuzz

from invoice_automation.matching.confidence import get_config
from invoice_automation.matching.exact_matcher import MatchResult
from invoice_automation.matching.normalizer import normalize_item_text, normalize_text


class FuzzyMatcher:
	"""Fuzzy string matching using thefuzz library."""

	_master_data_cache: dict[str, list[dict]] = {}

	def match(
		self,
		raw_text: str,
		source_doctype: str,
		supplier: str | None = None,
	) -> MatchResult:
		"""Fuzzy match raw_text against master data names for the given doctype.

		Confidence is on 0-100 percentage scale:
		  score >= 85 → confidence 75-89
		  score 60-84 → confidence 60-74
		  score < 60  → no match
		"""
		config = get_config()
		normalized = normalize_text(raw_text)
		if not normalized:
			return MatchResult(matched=False, doctype=source_doctype, stage="Fuzzy")

		master_data = self._load_master_data(source_doctype)
		if not master_data:
			return MatchResult(matched=False, doctype=source_doctype, stage="Fuzzy")

		best_score = 0
		best_match = None

		for entry in master_data:
			candidate_name = entry["name"]
			candidate_texts = [normalize_text(candidate_name)]

			if source_doctype == "Item":
				if entry.get("item_name"):
					candidate_texts.append(normalize_item_text(entry["item_name"]))
				if entry.get("description"):
					candidate_texts.append(normalize_item_text(entry["description"]))

			for candidate_text in candidate_texts:
				if not candidate_text:
					continue

				token_sort = fuzz.token_sort_ratio(normalized, candidate_text)
				partial = fuzz.partial_ratio(normalized, candidate_text)
				token_set = fuzz.token_set_ratio(normalized, candidate_text)
				score = max(token_sort, partial, token_set)

				if score > best_score:
					best_score = score
					best_match = candidate_name

		if best_match is None:
			return MatchResult(matched=False, doctype=source_doctype, stage="Fuzzy")

		fuzzy_high = config.get("fuzzy_match_threshold", 85)

		if best_score >= fuzzy_high:
			# 85-100 → confidence 75-89
			confidence = 75 + (best_score - fuzzy_high) / (100 - fuzzy_high) * 14
		elif best_score >= 60:
			# 60-84 → confidence 60-74
			confidence = 60 + (best_score - 60) / (fuzzy_high - 60) * 14
		else:
			return MatchResult(
				matched=False, doctype=source_doctype, stage="Fuzzy",
				details={"best_score": best_score, "best_match": best_match},
			)

		return MatchResult(
			matched=True, doctype=source_doctype, matched_name=best_match,
			confidence=round(confidence, 1), stage="Fuzzy",
			details={"fuzzy_score": best_score, "raw_text": raw_text},
		)

	def _load_master_data(self, doctype: str) -> list[dict]:
		if doctype in FuzzyMatcher._master_data_cache:
			return FuzzyMatcher._master_data_cache[doctype]

		try:
			if doctype == "Item":
				data = frappe.get_all(
					doctype, filters={"disabled": 0},
					fields=["name", "item_name", "description"], limit=0,
				)
			elif doctype == "Supplier":
				data = frappe.get_all(
					doctype, filters={"disabled": 0},
					fields=["name", "supplier_name"], limit=0,
				)
			else:
				data = frappe.get_all(doctype, fields=["name"], limit=0)

			FuzzyMatcher._master_data_cache[doctype] = data
			return data
		except Exception:
			return []

	@classmethod
	def clear_cache(cls):
		cls._master_data_cache.clear()
