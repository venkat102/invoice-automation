"""Normalize currency symbols/names to ISO 4217 codes."""

import re

CURRENCY_MAP = {
	"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "rupees": "INR", "rupee": "INR",
	"$": "USD", "usd": "USD", "us$": "USD", "dollars": "USD", "dollar": "USD",
	"€": "EUR", "eur": "EUR", "euros": "EUR", "euro": "EUR",
	"£": "GBP", "gbp": "GBP", "pounds": "GBP", "pound": "GBP",
	"¥": "JPY", "jpy": "JPY", "yen": "JPY",
	"aed": "AED", "sgd": "SGD", "aud": "AUD", "cad": "CAD",
}


def normalize_currency(raw: str | None) -> str | None:
	"""Convert currency symbol/name to ISO 4217 code."""
	if not raw:
		return None

	cleaned = raw.strip().lower()

	# Direct lookup
	if cleaned in CURRENCY_MAP:
		return CURRENCY_MAP[cleaned]

	# Already a valid 3-letter code
	if re.match(r"^[A-Z]{3}$", raw.strip()):
		return raw.strip().upper()

	# Search within the string
	for symbol, code in CURRENCY_MAP.items():
		if symbol in cleaned:
			return code

	return raw.strip().upper() if len(raw.strip()) == 3 else None
