"""General utility functions."""

import json

import frappe


def get_config_value(fieldname, default=None):
	"""Read a value from Invoice Automation Settings."""
	try:
		value = frappe.db.get_single_value("Invoice Automation Settings", fieldname)
		if value is not None:
			return value
	except Exception:
		pass
	return default


def safe_json_loads(text, default=None):
	"""Parse a JSON string, returning default on any failure."""
	if not text:
		return default
	try:
		return json.loads(text)
	except (json.JSONDecodeError, TypeError, ValueError):
		return default


def format_currency(amount, currency="INR"):
	"""Format amount for display with a currency symbol."""
	symbols = {"INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}
	symbol = symbols.get(currency, currency + " ")

	try:
		amount = float(amount)
	except (TypeError, ValueError):
		amount = 0.0

	return f"{symbol}{amount:,.2f}"
