"""Confidence scoring and routing logic for invoice matching."""

import frappe


# Fallback defaults (percentage scale for thresholds)
DEFAULT_CONFIG = {
	"auto_create_threshold": 90,
	"review_threshold": 60,
	"fuzzy_match_threshold": 85,
	"embedding_similarity_threshold": 0.85,
	"embedding_review_threshold": 0.65,
	"human_correction_weight_boost": 1.1,
	"agreement_confidence_boost": 10,
	"duplicate_check_amount_tolerance_pct": 5,
	"duplicate_check_date_range_days": 7,
	"llm_max_candidates": 10,
	"llm_max_corrections_context": 5,
	"embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
	"enable_llm_matching": 1,
	"enable_auto_create": 0,
}

# Weights for combining scores: supplier is critical, line items are the bulk of the invoice
SUPPLIER_WEIGHT = 0.30
LINE_ITEM_WEIGHT = 0.60
TAX_WEIGHT = 0.10


def get_config() -> dict:
	"""Read configuration from Invoice Automation Settings."""
	config = dict(DEFAULT_CONFIG)

	try:
		doc = frappe.get_cached_doc("Invoice Automation Settings")
		for key in DEFAULT_CONFIG:
			value = getattr(doc, key, None)
			if value is not None:
				config[key] = value
	except frappe.DoesNotExistError:
		pass  # Settings not configured yet, use defaults
	except Exception as e:
		frappe.log_error(f"Failed to load Invoice Automation Settings: {e}", "Invoice Config Error")

	return config


def determine_routing(field_confidences: list[float]) -> str:
	"""Determine routing based on weighted average confidence (0-100 scale).

	Uses weighted average instead of minimum so that one low-confidence field
	doesn't force the entire invoice to manual entry. However, if any field
	has zero confidence (completely unmatched), it caps the routing at Review Queue.
	"""
	if not field_confidences:
		return "Manual Entry"

	config = get_config()
	avg_confidence = sum(field_confidences) / len(field_confidences)

	# If any field is completely unmatched, don't auto-create
	has_unmatched = any(c == 0.0 for c in field_confidences)

	if not has_unmatched and avg_confidence >= config["auto_create_threshold"]:
		return "Auto Create"
	elif avg_confidence >= config["review_threshold"]:
		return "Review Queue"
	else:
		return "Manual Entry"


class ConfidenceScorer:
	"""Combines scores from different matching stages using weighted average."""

	def __init__(self):
		self.config = get_config()

	def combine_scores(self, results: list) -> float:
		"""Return weighted average confidence across supplier, line items, and tax matches.

		Supplier match carries 30% weight, line items 60%, tax matches 10%.
		If a category has no results, its weight is redistributed proportionally.
		"""
		if not results:
			return 0.0

		supplier_scores = []
		line_item_scores = []
		tax_scores = []

		for result in results:
			if hasattr(result, "confidence") and hasattr(result, "doctype"):
				if result.doctype == "Supplier":
					supplier_scores.append(result.confidence)
				elif result.doctype == "Item":
					line_item_scores.append(result.confidence)
				else:
					tax_scores.append(result.confidence)
			elif isinstance(result, (int, float)):
				line_item_scores.append(float(result))

		# Build weighted components
		components = []
		weights = []

		if supplier_scores:
			components.append(sum(supplier_scores) / len(supplier_scores))
			weights.append(SUPPLIER_WEIGHT)

		if line_item_scores:
			components.append(sum(line_item_scores) / len(line_item_scores))
			weights.append(LINE_ITEM_WEIGHT)

		if tax_scores:
			components.append(sum(tax_scores) / len(tax_scores))
			weights.append(TAX_WEIGHT)

		if not components:
			return 0.0

		# Normalize weights to sum to 1.0
		total_weight = sum(weights)
		weighted_avg = sum(c * w / total_weight for c, w in zip(components, weights))

		return round(weighted_avg, 2)
