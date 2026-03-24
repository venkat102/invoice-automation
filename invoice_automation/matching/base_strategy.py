"""Base class for pluggable matching strategies."""

from abc import ABC, abstractmethod

from invoice_automation.matching.exact_matcher import MatchResult


class BaseMatchingStrategy(ABC):
	"""All matching strategies must implement this interface.

	Strategies are loaded from the Matching Strategy doctype and executed
	in priority order by the matching pipeline.
	"""

	name: str = ""
	applies_to: list[str] = ["Supplier", "Item"]
	max_confidence: float = 100.0

	def __init__(self, config: dict | None = None):
		"""Initialize with optional strategy-specific config from settings_json."""
		self.config = config or {}

	@abstractmethod
	def match_supplier(self, extracted_data: dict) -> MatchResult:
		"""Match supplier from extracted invoice data.

		Args:
			extracted_data: Full pipeline input dict with supplier_name, supplier_tax_id, etc.

		Returns:
			MatchResult with matched supplier or matched=False.
		"""
		...

	@abstractmethod
	def match_item(self, line_item: dict, supplier: str | None = None) -> MatchResult:
		"""Match a single line item to an ERPNext Item.

		Args:
			line_item: Dict with description, qty, rate, amount, hsn_code.
			supplier: Matched supplier name for context.

		Returns:
			MatchResult with matched item or matched=False.
		"""
		...

	def applies_to_doctype(self, doctype: str) -> bool:
		"""Check if this strategy handles the given doctype."""
		return doctype in self.applies_to or "Both" in self.applies_to

	def cap_confidence(self, confidence: float) -> float:
		"""Ensure confidence does not exceed the strategy's max_confidence."""
		return min(confidence, self.max_confidence)
