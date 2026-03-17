"""Normalize line items: deduplicate, clean empty rows, recalculate totals."""

from decimal import Decimal, InvalidOperation

from invoice_automation.extraction.normalizers.decimal_normalizer import normalize_decimal


def normalize_line_items(items: list[dict] | None) -> list[dict]:
	"""Clean and normalize a list of raw line items."""
	if not items:
		return []

	normalized = []
	seen = set()

	for i, item in enumerate(items):
		if not item:
			continue

		desc = (item.get("description") or "").strip()

		# Skip empty rows
		if not desc and not item.get("line_total") and not item.get("quantity"):
			continue

		# Deduplicate by (description, quantity, unit_price)
		dedup_key = (desc, item.get("quantity"), item.get("unit_price"))
		if dedup_key in seen and desc:
			continue
		if desc:
			seen.add(dedup_key)

		# Normalize numeric fields
		cleaned = {
			"line_number": item.get("line_number") or (i + 1),
			"description": desc or None,
			"quantity": normalize_decimal(item.get("quantity")),
			"unit": (item.get("unit") or "").strip() or None,
			"unit_price": normalize_decimal(item.get("unit_price")),
			"tax_rate": normalize_decimal(item.get("tax_rate")),
			"tax_amount": normalize_decimal(item.get("tax_amount")),
			"discount_amount": normalize_decimal(item.get("discount_amount")),
			"line_total": normalize_decimal(item.get("line_total")),
			"hsn_sac_code": (item.get("hsn_sac_code") or "").strip() or None,
			"sku": (item.get("sku") or "").strip() or None,
			"item_code": (item.get("item_code") or "").strip() or None,
		}

		# Recalculate line_total if we have qty and unit_price but no total
		if cleaned["quantity"] and cleaned["unit_price"] and not cleaned["line_total"]:
			try:
				qty = Decimal(cleaned["quantity"])
				price = Decimal(cleaned["unit_price"])
				cleaned["line_total"] = str(qty * price)
			except (InvalidOperation, ValueError):
				pass

		normalized.append(cleaned)

	return normalized
