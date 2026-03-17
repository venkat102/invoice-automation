"""Decimal helpers. Never use float for currency/amounts."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ZERO = Decimal("0")
CURRENCY_PRECISION = Decimal("0.01")


def to_decimal(value) -> Decimal:
	"""Convert any value to Decimal. Returns ZERO for None or empty."""
	if value is None or value == "":
		return ZERO
	if isinstance(value, Decimal):
		return value
	try:
		# Handle Indian/international numbering: remove commas
		if isinstance(value, str):
			value = value.strip().replace(",", "")
		return Decimal(str(value))
	except (InvalidOperation, ValueError, TypeError):
		return ZERO


def decimal_to_str(value) -> str:
	"""Convert Decimal to string, preserving precision."""
	if value is None:
		return "0"
	return str(to_decimal(value))


def safe_multiply(a, b) -> Decimal:
	"""Multiply two values as Decimals."""
	return to_decimal(a) * to_decimal(b)


def safe_divide(a, b) -> Decimal:
	"""Divide two values as Decimals. Returns ZERO on divide-by-zero."""
	divisor = to_decimal(b)
	if divisor == ZERO:
		return ZERO
	return to_decimal(a) / divisor


def round_decimal(value, places: int = 2) -> Decimal:
	"""Round a Decimal to the given number of places."""
	quantize_str = "0." + "0" * places
	return to_decimal(value).quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
