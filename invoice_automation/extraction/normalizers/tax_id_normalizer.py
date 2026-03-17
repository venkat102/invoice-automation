"""Normalize and validate tax IDs (GSTIN, PAN, VAT numbers)."""

import re


def normalize_gstin(raw: str | None) -> str | None:
	"""Strip spaces/hyphens, uppercase, validate 15-char GSTIN format."""
	if not raw:
		return None

	cleaned = re.sub(r"[\s\-]", "", raw).upper()

	if len(cleaned) != 15:
		return cleaned if cleaned else None

	# GSTIN format: 2-digit state + 10-char PAN + 1 entity + 1 Z + 1 check
	if re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z]$", cleaned):
		return cleaned

	return cleaned


def normalize_pan(raw: str | None) -> str | None:
	"""Strip spaces, uppercase, validate 10-char PAN format."""
	if not raw:
		return None

	cleaned = re.sub(r"\s", "", raw).upper()

	if len(cleaned) != 10:
		return cleaned if cleaned else None

	if re.match(r"^[A-Z]{5}\d{4}[A-Z]$", cleaned):
		return cleaned

	return cleaned


def extract_pan_from_gstin(gstin: str | None) -> str | None:
	"""Extract PAN (characters 3-12) from a valid GSTIN."""
	normalized = normalize_gstin(gstin)
	if normalized and len(normalized) >= 12:
		return normalized[2:12]
	return None


def extract_state_code(gstin: str | None) -> str | None:
	"""Extract 2-digit state code from GSTIN."""
	normalized = normalize_gstin(gstin)
	if normalized and len(normalized) >= 2 and normalized[:2].isdigit():
		return normalized[:2]
	return None
