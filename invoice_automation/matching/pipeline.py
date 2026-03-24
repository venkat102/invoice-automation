"""Orchestrates the full matching pipeline for invoice processing."""

import importlib
import time
from dataclasses import dataclass, field

import frappe

from invoice_automation.matching.confidence import (
	ConfidenceScorer,
	determine_routing,
	get_config,
)
from invoice_automation.matching.exact_matcher import ExactMatcher, MatchResult  # noqa: F401

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
	"""Orchestrates the full matching pipeline through pluggable strategies."""

	def __init__(self):
		self.config = get_config()
		self.confidence_scorer = ConfidenceScorer()
		self.strategies = self._load_strategies()
		# Keep ExactMatcher for tax template matching (rule-based, not pluggable)
		self._exact_matcher = ExactMatcher()

	def _load_strategies(self):
		"""Load enabled strategies from Matching Strategy doctype, sorted by priority.

		Falls back to the hardcoded default strategy set if no records exist.
		"""
		try:
			rows = frappe.get_all(
				"Matching Strategy",
				filters={"enabled": 1},
				fields=["strategy_name", "strategy_class", "priority", "max_confidence", "settings_json", "applies_to"],
				order_by="priority asc",
			)
		except Exception:
			rows = []

		if not rows:
			return self._default_strategies()

		strategies = []
		for row in rows:
			try:
				instance = self._instantiate_strategy(row)
				if instance:
					strategies.append(instance)
			except Exception as e:
				frappe.log_error(
					f"Failed to load matching strategy '{row.strategy_name}': {e}",
					"Matching Strategy Load Error",
				)

		return strategies or self._default_strategies()

	def _instantiate_strategy(self, row):
		"""Dynamically import and instantiate a strategy class."""
		module_path, class_name = row.strategy_class.rsplit(".", 1)
		module = importlib.import_module(module_path)
		cls = getattr(module, class_name)

		config = {}
		if row.settings_json:
			import json
			try:
				config = json.loads(row.settings_json) if isinstance(row.settings_json, str) else row.settings_json
			except (json.JSONDecodeError, TypeError):
				config = {}

		instance = cls(config=config)
		instance.name = row.strategy_name
		instance.max_confidence = row.max_confidence or 100.0
		instance.applies_to = [row.applies_to] if row.applies_to != "Both" else ["Supplier", "Item"]
		return instance

	def _default_strategies(self):
		"""Fallback: return hardcoded strategy instances (pre-registry behavior)."""
		from invoice_automation.matching.alias_matcher import AliasMatcher, AliasMatcherStrategy
		from invoice_automation.matching.embedding_matcher import EmbeddingMatcherStrategy
		from invoice_automation.matching.exact_matcher import ExactMatcherStrategy
		from invoice_automation.matching.fuzzy_matcher import FuzzyMatcherStrategy
		from invoice_automation.matching.llm_matcher import LLMMatcherStrategy

		return [
			ExactMatcherStrategy(),
			AliasMatcherStrategy(),
			FuzzyMatcherStrategy(),
			EmbeddingMatcherStrategy(),
			LLMMatcherStrategy(),
		]

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

		# Step 3: Match tax templates (rule-based only, not pluggable)
		tax_matches = []
		if isinstance(extracted_data, dict):
			supplier_tax_id = extracted_data.get("supplier_tax_id", "") or extracted_data.get("supplier_gstin", "") or ""
			company_tax_id = extracted_data.get("company_tax_id", "") or extracted_data.get("company_gstin", "") or ""
		else:
			supplier_tax_id = getattr(extracted_data, "supplier_tax_id", "") or getattr(extracted_data, "supplier_gstin", "") or ""
			company_tax_id = getattr(extracted_data, "company_tax_id", "") or getattr(extracted_data, "company_gstin", "") or ""
		taxes = (
			extracted_data.get("taxes", [])
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "taxes", [])
		) or []

		for tax_detail in taxes:
			tax_dict = tax_detail if isinstance(tax_detail, dict) else tax_detail.model_dump()
			tax_match = self._exact_matcher.match_tax_template(
				tax_dict, supplier_tax_id, company_tax_id
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
		"""Run through strategies to match the supplier."""
		for strategy in self.strategies:
			if "Supplier" not in getattr(strategy, "applies_to", ["Supplier", "Item"]):
				continue

			# LLM strategy needs special handling (candidates + correction context)
			if getattr(strategy, "is_llm", False):
				result = self._try_llm_supplier(extracted_data)
				if result:
					return result
				continue

			try:
				result = strategy.match_supplier(extracted_data)
				if result.matched:
					result.confidence = min(result.confidence, strategy.max_confidence)
					if result.confidence >= self.config["auto_create_threshold"]:
						return result
					# Still return if matched, even below threshold
					return result
			except Exception as e:
				frappe.log_error(
					f"Strategy {strategy.name} failed for Supplier: {e}",
					"Invoice Matching Error",
				)

		return MatchResult(matched=False, doctype="Supplier", stage="Exhausted")

	def _match_item(self, line_item, supplier: str | None) -> MatchResult:
		"""Run through strategies to match a line item."""
		from invoice_automation.matching.price_validator import apply_price_validation

		for strategy in self.strategies:
			if "Item" not in getattr(strategy, "applies_to", ["Supplier", "Item"]):
				continue

			# LLM strategy needs special handling
			if getattr(strategy, "is_llm", False):
				result = self._try_llm_item(line_item, supplier)
				if result:
					result = apply_price_validation(result, line_item, supplier)
					return result
				continue

			try:
				result = strategy.match_item(line_item, supplier)
				if result.matched:
					result.confidence = min(result.confidence, strategy.max_confidence)
					result = apply_price_validation(result, line_item, supplier)
					return result
			except Exception as e:
				frappe.log_error(
					f"Strategy {strategy.name} failed for Item: {e}",
					"Invoice Matching Error",
				)

		raw_text = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""

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

	def _try_llm_supplier(self, extracted_data) -> MatchResult | None:
		"""LLM matching for supplier — needs candidates and correction context."""
		supplier_name = (
			extracted_data.get("supplier_name", "")
			if isinstance(extracted_data, dict)
			else getattr(extracted_data, "supplier_name", "")
		) or ""

		return self._try_llm(supplier_name, "Supplier", None)

	def _try_llm_item(self, line_item, supplier) -> MatchResult | None:
		"""LLM matching for item — needs candidates and correction context."""
		raw_text = (
			line_item.get("description", "")
			if isinstance(line_item, dict)
			else getattr(line_item, "description", "")
		) or ""

		return self._try_llm(raw_text, "Item", supplier)

	def _try_llm(self, raw_text, source_doctype, supplier) -> MatchResult | None:
		try:
			from invoice_automation.matching.fuzzy_matcher import FuzzyMatcher
			from invoice_automation.matching.llm_matcher import LLMMatcher

			# Gather candidates from fuzzy cache
			candidates = []
			if source_doctype in FuzzyMatcher._master_data_cache:
				candidates = [e["name"] for e in FuzzyMatcher._master_data_cache[source_doctype][:50]]

			# Get correction context
			corrections_context = self._get_corrections_context(raw_text, source_doctype, supplier)

			matcher = LLMMatcher()
			result = matcher.match(
				raw_text, source_doctype, supplier, candidates, corrections_context
			)
			if result.matched:
				return result
		except Exception as e:
			frappe.log_error(
				f"LLM matching failed for {source_doctype}: {e}",
				"Invoice LLM Matching Error",
			)
		return None

	def _get_corrections_context(self, raw_text, source_doctype, supplier) -> list[dict]:
		try:
			from invoice_automation.memory.reasoning_retriever import ReasoningRetriever

			retriever = ReasoningRetriever()
			return retriever.get_relevant_corrections(raw_text, supplier, source_doctype)
		except Exception as e:
			frappe.log_error(
				f"Corrections context retrieval failed: {e}",
				"Invoice Corrections Error",
			)
			return []
