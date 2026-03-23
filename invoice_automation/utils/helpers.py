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


def enqueue_if_scheduler_active(method, **kwargs):
	"""Enqueue a background job if scheduler is active, otherwise run synchronously.

	Accepts the same keyword arguments as frappe.enqueue (queue, timeout, etc.).
	Non-enqueue kwargs are passed through to the target method.
	"""
	import importlib

	enqueue_kwargs = {}
	method_kwargs = {}
	enqueue_keys = {"queue", "timeout", "event", "is_async", "now", "enqueue_after_commit",
	                "at_front", "job_id", "deduplicate", "queue_name_suffix"}

	for key, value in kwargs.items():
		if key in enqueue_keys:
			enqueue_kwargs[key] = value
		else:
			method_kwargs[key] = value

	if frappe.utils.scheduler.is_scheduler_inactive():
		frappe.log_error(
			title="Invoice Automation: Scheduler Inactive",
			message=f"Scheduler is not active — running {method} synchronously",
		)
		if isinstance(method, str):
			module_path, func_name = method.rsplit(".", 1)
			module = importlib.import_module(module_path)
			func = getattr(module, func_name)
			func(**method_kwargs)
		else:
			method(**method_kwargs)
	else:
		frappe.enqueue(method, **enqueue_kwargs, **method_kwargs)
