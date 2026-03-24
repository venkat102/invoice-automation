"""Post-match confidence modifier based on price validation."""

import frappe

from invoice_automation.matching.exact_matcher import MatchResult


def apply_price_validation(match_result: MatchResult, line_item: dict, supplier: str | None) -> MatchResult:
	"""Adjust match confidence based on historical price data.

	If the extracted rate is close to the average rate for this supplier-item pair,
	boost confidence. If it's way off, penalize.
	"""
	if not match_result.matched or not supplier:
		return match_result

	extracted_rate = line_item.get("rate") if isinstance(line_item, dict) else getattr(line_item, "rate", None)
	if not extracted_rate:
		return match_result

	try:
		extracted_rate = float(extracted_rate)
	except (ValueError, TypeError):
		return match_result

	if extracted_rate <= 0:
		return match_result

	catalog = frappe.db.get_value(
		"Supplier Item Catalog",
		{"supplier": supplier, "item": match_result.matched_name},
		["avg_rate", "min_rate", "max_rate", "occurrence_count"],
		as_dict=True,
	)

	if not catalog or not catalog.avg_rate or catalog.occurrence_count < 2:
		return match_result

	avg_rate = float(catalog.avg_rate)
	if avg_rate <= 0:
		return match_result

	deviation_pct = abs(extracted_rate - avg_rate) / avg_rate * 100

	details = dict(match_result.details) if match_result.details else {}
	details["price_validation"] = {
		"extracted_rate": extracted_rate,
		"avg_rate": avg_rate,
		"deviation_pct": round(deviation_pct, 1),
	}

	if deviation_pct <= 15:
		# Rate is within 15% of average — boost confidence
		confidence = min(match_result.confidence + 5.0, 100.0)
		details["price_validation"]["effect"] = "boost"
	elif deviation_pct > 50:
		# Rate is >50% off — penalize confidence
		confidence = max(match_result.confidence - 10.0, 0.0)
		details["price_validation"]["effect"] = "penalty"
	else:
		# Moderate deviation — no change
		confidence = match_result.confidence
		details["price_validation"]["effect"] = "neutral"

	return MatchResult(
		matched=match_result.matched,
		doctype=match_result.doctype,
		matched_name=match_result.matched_name,
		confidence=round(confidence, 1),
		stage=match_result.stage,
		details=details,
	)
