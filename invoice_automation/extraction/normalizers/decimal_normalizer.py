"""Normalize decimal numbers from various formats."""

import re
from decimal import Decimal, InvalidOperation


def normalize_decimal(raw: str | None) -> str | None:
	"""Convert various number formats to a clean decimal string.

	Handles: Indian numbering (1,23,456.78), European (1.234,56), plain (1234.56).
	"""
	if raw is None:
		return None

	cleaned = str(raw).strip()
	if not cleaned:
		return None

	# Remove currency symbols and whitespace
	cleaned = re.sub(r"[₹$€£¥\s]", "", cleaned)

	# Remove parentheses used for negative amounts: (1234.56) → -1234.56
	if cleaned.startswith("(") and cleaned.endswith(")"):
		cleaned = "-" + cleaned[1:-1]

	# Detect European format (comma as decimal separator): 1.234,56
	if re.match(r"^-?\d{1,3}(\.\d{3})+,\d{1,2}$", cleaned):
		cleaned = cleaned.replace(".", "").replace(",", ".")
	# Detect format with comma as thousands: 1,234.56 or 1,23,456.78
	elif "," in cleaned and "." in cleaned:
		if cleaned.rindex(",") < cleaned.rindex("."):
			# Comma before dot: 1,234.56 — just remove commas
			cleaned = cleaned.replace(",", "")
		else:
			# Dot before comma: European 1.234,56
			cleaned = cleaned.replace(".", "").replace(",", ".")
	# Only commas, no dot: could be Indian/US thousands or European decimal
	elif "," in cleaned:
		parts = cleaned.split(",")
		last = parts[-1]
		if len(last) <= 2:
			# Likely European decimal: 1234,56
			cleaned = cleaned.replace(",", ".")
		else:
			# Likely thousands separator: 1,234 or 1,23,456
			cleaned = cleaned.replace(",", "")

	try:
		Decimal(cleaned)
		return cleaned
	except InvalidOperation:
		return None


def normalize_amount(raw: str | None) -> str | None:
	"""Strip currency symbols and whitespace, then normalize as decimal."""
	if raw is None:
		return None

	cleaned = re.sub(r"[₹$€£¥\s]", "", str(raw).strip())
	return normalize_decimal(cleaned)
