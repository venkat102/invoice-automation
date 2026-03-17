"""Orchestrates the full matching pipeline for invoice processing."""

import time
from dataclasses import dataclass, field

import frappe

from invoice_automation.matching.alias_matcher import AliasMatcher
from invoice_automation.matching.confidence import (
	ConfidenceScorer,
	determine_routing,
	get_config,
)
from invoice_automation.matching.embedding_matcher import EmbeddingMatcher
from invoice_automation.matching.exact_matcher import ExactMatcher, MatchResult  # noqa: F401
from invoice_automation.matching.fuzzy_matcher import FuzzyMatcher
from invoice_automation.matching.llm_matcher import LLMMatcher

# Re-export MatchResult for convenience
__all__ = ["MatchingPipeline", "PipelineResult", "MatchResult"]


@dataclass
class PipelineResult:
	supplier_match: MatchResult
	line_item_matches: list[MatchResult] = field(default_factory=list)
	tax_matches: list[MatchResult] = field(default_factory=list)
	routing_decision: str = "Manual Entry"
	overall_confidence: float = 0.0
	processing_time_ms: int = 0

	def to_dict(self):
		return {
			"supplier_match": self.supplier_match.to_dict(),
			"line_item_matches": [m.to_dict() for m in self.line_item_matches],
			"tax_matches": [m.to_dict() for m in self.tax_matches],
			"routing_decision": self.routing_decision,
			"overall_confidence": self.overall_confidence,
			"processing_time_ms": self.processing_time_ms,
		}


class MatchingPipeline:
	"""Orchestrates the full matching pipeline through all stages."""

	def __init__(self):
		self.exact_matcher = ExactMatcher()
		self.alias_matcher = AliasMatcher()
		self.fuzzy_matcher = FuzzyMatcher()
		self.embedding_matcher = EmbeddingMatcher()
		self.llm_matcher = LLMMatcher()
		self.confidence_scorer = ConfidenceScorer()
		self.config = get_config()

	def process(self, extracted_data) -> PipelineResult:
		"""Run the full matching pipeline. Accepts dict or ExtractedInvoiceData."""
		start_time = time.time()

		# Step 1: Match supplier
		supplier_match = self._match_supplier(extracted_data)
		matched_supplier = supplier_match.matched_name if supplier_match.matched else None

		# Step 2: Match each line item
		line_items = (
			extracted_data.get("line_items", [])
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "line_items", [])
		)

		line_item_matches = []
		for line_item in line_items:
			item_match = self._match_item(line_item, matched_supplier)
			line_item_matches.append(item_match)

		# Step 3: Match tax templates (rule-based only)
		tax_matches = []
		supplier_gstin = (
			extracted_data.get("supplier_gstin", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "supplier_gstin", "")
		) or ""
		company_gstin = (
			extracted_data.get("company_gstin", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "company_gstin", "")
		) or ""
		taxes = (
			extracted_data.get("taxes", [])
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "taxes", [])
		) or []

		for tax_detail in taxes:
			tax_dict = tax_detail if isinstance(tax_detail, dict) else tax_detail.model_dump()
			tax_match = self.exact_matcher.match_tax_template(
				tax_dict, supplier_gstin, company_gstin
			)
			tax_matches.append(tax_match)

		# Step 4: Determine routing
		all_confidences = [supplier_match.confidence] if supplier_match.matched else [0.0]
		for m in line_item_matches:
			all_confidences.append(m.confidence if m.matched else 0.0)
		for m in tax_matches:
			all_confidences.append(m.confidence if m.matched else 0.0)

		routing_decision = determine_routing(all_confidences)
		overall_confidence = self.confidence_scorer.combine_scores(
			[supplier_match] + line_item_matches + tax_matches
		)

		processing_time_ms = int((time.time() - start_time) * 1000)

		return PipelineResult(
			supplier_match=supplier_match,
			line_item_matches=line_item_matches,
			tax_matches=tax_matches,
			routing_decision=routing_decision,
			overall_confidence=overall_confidence,
			processing_time_ms=processing_time_ms,
		)

	def _match_supplier(self, extracted_data) -> MatchResult:
		# Stage 1: Exact
		result = self.exact_matcher.match_supplier(extracted_data)
		if result.matched and result.confidence >= self.config["auto_create_threshold"]:
			return result

		supplier_name = (
			extracted_data.get("supplier_name", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "supplier_name", "")
		) or ""

		# Stage 2: Alias
		result = self._try_stage(self.alias_matcher.match, supplier_name, "Supplier", None)
		if result:
			return result

		# Stage 3: Fuzzy
		result = self._try_stage(self.fuzzy_matcher.match, supplier_name, "Supplier", None)
		if result:
			return result

		# Stage 4: Embedding
		result = self._try_stage(self.embedding_matcher.match, supplier_name, "Supplier", None)
		if result:
			return result

		# Stage 5: LLM
		result = self._try_llm(supplier_name, "Supplier", None)
		if result:
			return result

		return MatchResult(matched=False, doctype="Supplier", stage="Exhausted")

	def _match_item(self, line_item, supplier: str | None) -> MatchResult:
		# Stage 1: Exact
		result = self.exact_matcher.match_item(line_item, supplier)
		if result.matched and result.confidence >= self.config["auto_create_threshold"]:
			return result

		raw_text = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""

		# Stage 2-4
		for matcher in [self.alias_matcher.match, self.fuzzy_matcher.match, self.embedding_matcher.match]:
			result = self._try_stage(matcher, raw_text, "Item", supplier)
			if result:
				return result

		# Stage 5: LLM
		result = self._try_llm(raw_text, "Item", supplier)
		if result:
			return result

		return MatchResult(
			matched=False, doctype="Item", stage="Exhausted",
			details={
				"raw_text": raw_text,
				"qty": line_item.get("qty") if isinstance(line_item, dict) else getattr(line_item, "qty", None),
				"rate": line_item.get("rate") if isinstance(line_item, dict) else getattr(line_item, "rate", None),
				"amount": line_item.get("amount") if isinstance(line_item, dict) else getattr(line_item, "amount", None),
				"hsn_code": line_item.get("hsn_code") if isinstance(line_item, dict) else getattr(line_item, "hsn_code", None),
			},
		)

	def _try_stage(self, match_fn, raw_text, source_doctype, supplier) -> MatchResult | None:
		try:
			result = match_fn(raw_text, source_doctype, supplier)
			if result.matched:
				return result
		except Exception:
			pass
		return None

	def _try_llm(self, raw_text, source_doctype, supplier) -> MatchResult | None:
		try:
			# Gather candidates from fuzzy cache
			candidates = []
			if source_doctype in FuzzyMatcher._master_data_cache:
				candidates = [e["name"] for e in FuzzyMatcher._master_data_cache[source_doctype][:50]]

			# Get correction context
			corrections_context = self._get_corrections_context(raw_text, source_doctype, supplier)

			result = self.llm_matcher.match(
				raw_text, source_doctype, supplier, candidates, corrections_context
			)
			if result.matched:
				return result
		except Exception:
			pass
		return None

	def _get_corrections_context(self, raw_text, source_doctype, supplier) -> list[dict]:
		try:
			from invoice_automation.memory.reasoning_retriever import ReasoningRetriever

			retriever = ReasoningRetriever()
			return retriever.get_relevant_corrections(raw_text, supplier, source_doctype)
		except Exception:
			return []
