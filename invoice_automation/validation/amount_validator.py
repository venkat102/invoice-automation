import frappe

from invoice_automation.utils.helpers import get_config_value


def validate_amounts(extracted_data, matched_line_items):
	"""Cross-verify line totals vs invoice total.

	Args:
		extracted_data: Object or dict with total_amount and optionally subtotal.
		matched_line_items: List of dicts each containing qty, rate, and optionally tax_rate.

	Returns:
		dict with is_valid, computed_subtotal, computed_total, extracted_total, difference, tolerance.
	"""
	tolerance = float(get_config_value("amount_tolerance", 1.0))

	computed_subtotal = 0.0
	for item in matched_line_items:
		qty = float(item.get("qty") or 0)
		rate = float(item.get("rate") or 0)
		computed_subtotal += qty * rate

	total_tax = 0.0
	for item in matched_line_items:
		qty = float(item.get("qty") or 0)
		rate = float(item.get("rate") or 0)
		line_amount = qty * rate
		tax_rate = float(item.get("tax_rate") or 0)
		total_tax += line_amount * tax_rate / 100.0

	computed_total = computed_subtotal + total_tax

	if hasattr(extracted_data, "total_amount"):
		extracted_total = float(extracted_data.total_amount or 0)
	elif isinstance(extracted_data, dict):
		extracted_total = float(extracted_data.get("total_amount") or 0)
	else:
		extracted_total = 0.0

	difference = abs(computed_total - extracted_total)
	is_valid = difference <= tolerance

	return {
		"is_valid": is_valid,
		"computed_subtotal": round(computed_subtotal, 2),
		"computed_total": round(computed_total, 2),
		"extracted_total": round(extracted_total, 2),
		"difference": round(difference, 2),
		"tolerance": tolerance,
	}
