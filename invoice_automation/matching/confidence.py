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


def get_config() -> dict:
	"""Read configuration from Invoice Automation Settings."""
	config = dict(DEFAULT_CONFIG)

	try:
		doc = frappe.get_cached_doc("Invoice Automation Settings")
		for key in DEFAULT_CONFIG:
			value = getattr(doc, key, None)
			if value is not None:
				config[key] = value
	except Exception:
		pass

	return config


def determine_routing(field_confidences: list[float]) -> str:
	"""Determine routing based on minimum confidence across all fields (0-100 scale)."""
	if not field_confidences:
		return "Manual Entry"

	config = get_config()
	min_confidence = min(field_confidences)

	if min_confidence >= config["auto_create_threshold"]:
		return "Auto Create"
	elif min_confidence >= config["review_threshold"]:
		return "Review Queue"
	else:
		return "Manual Entry"


class ConfidenceScorer:
	"""Combines scores from different matching stages."""

	def __init__(self):
		self.config = get_config()

	def combine_scores(self, results: list) -> float:
		"""Return the minimum confidence (weakest link)."""
		if not results:
			return 0.0

		confidences = []
		for result in results:
			if hasattr(result, "confidence"):
				confidences.append(result.confidence)
			elif isinstance(result, (int, float)):
				confidences.append(float(result))

		return round(min(confidences), 2) if confidences else 0.0
