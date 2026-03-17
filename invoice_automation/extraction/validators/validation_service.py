"""Orchestrates all extraction validation checks."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from invoice_automation.extraction.schema import ExtractedInvoice, ExtractionWarning
from invoice_automation.utils.decimal_utils import to_decimal, ZERO


@dataclass
class ValidationResult:
	passed: bool
	severity: str  # error, warning, info
	message: str
	field_path: str | None = None


def run_all_checks(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Run all consistency checks on an extracted invoice."""
	results = []
	results.extend(check_date_consistency(invoice))
	results.extend(check_total_consistency(invoice))
	results.extend(check_line_item_totals(invoice))
	results.extend(check_line_item_sum(invoice))
	results.extend(check_negative_amounts(invoice))
	results.extend(check_zero_value(invoice))
	results.extend(check_currency_consistency(invoice))
	results.extend(check_missing_critical_fields(invoice))
	return results


def check_date_consistency(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Due date should not be before invoice date."""
	results = []
	if invoice.invoice_date and invoice.due_date:
		if invoice.due_date < invoice.invoice_date:
			results.append(ValidationResult(
				passed=False, severity="warning",
				message=f"Due date ({invoice.due_date}) is before invoice date ({invoice.invoice_date})",
				field_path="due_date",
			))
	return results


def check_total_consistency(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Check subtotal + tax + shipping - discount + round_off ≈ total_amount."""
	results = []
	if not invoice.total_amount:
		return results

	total = to_decimal(invoice.total_amount)
	subtotal = to_decimal(invoice.subtotal)
	tax = to_decimal(invoice.tax_amount)
	discount = to_decimal(invoice.discount_amount)
	shipping = to_decimal(invoice.shipping_amount)
	round_off = to_decimal(invoice.round_off_amount)

	if subtotal == ZERO:
		return results

	computed = subtotal + tax + shipping - discount + round_off
	diff = abs(computed - total)

	if diff > Decimal("1"):
		results.append(ValidationResult(
			passed=False, severity="warning",
			message=f"Total mismatch: computed {computed} vs extracted {total} (diff: {diff})",
			field_path="total_amount",
		))

	return results


def check_line_item_totals(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Check qty × unit_price ≈ line_total for each line."""
	results = []
	for item in invoice.line_items:
		if item.quantity and item.unit_price and item.line_total:
			try:
				qty = Decimal(item.quantity)
				price = Decimal(item.unit_price)
				total = Decimal(item.line_total)
				computed = qty * price
				diff = abs(computed - total)
				if diff > Decimal("1"):
					results.append(ValidationResult(
						passed=False, severity="warning",
						message=f"Line {item.line_number}: {qty} × {price} = {computed}, but line_total = {total}",
						field_path=f"line_items[{item.line_number}].line_total",
					))
			except (InvalidOperation, TypeError):
				pass
	return results


def check_line_item_sum(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Check sum of line_totals ≈ subtotal."""
	results = []
	if not invoice.subtotal:
		return results

	subtotal = to_decimal(invoice.subtotal)
	line_sum = ZERO

	for item in invoice.line_items:
		if item.line_total:
			try:
				line_sum += Decimal(item.line_total)
			except InvalidOperation:
				pass

	if line_sum == ZERO:
		return results

	diff = abs(line_sum - subtotal)
	if diff > Decimal("1"):
		results.append(ValidationResult(
			passed=False, severity="warning",
			message=f"Line items sum ({line_sum}) doesn't match subtotal ({subtotal})",
			field_path="subtotal",
		))

	return results


def check_negative_amounts(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Flag negative amounts — may be credit notes."""
	results = []
	if invoice.total_amount:
		total = to_decimal(invoice.total_amount)
		if total < ZERO:
			results.append(ValidationResult(
				passed=True, severity="info",
				message=f"Negative total amount ({total}). This may be a credit note.",
				field_path="total_amount",
			))
	return results


def check_zero_value(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Flag zero-total invoices."""
	results = []
	if invoice.total_amount and to_decimal(invoice.total_amount) == ZERO:
		results.append(ValidationResult(
			passed=True, severity="warning",
			message="Invoice total is zero",
			field_path="total_amount",
		))
	return results


def check_currency_consistency(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""All amounts should use the same currency (if detectable)."""
	# This is a basic check — currency is extracted once at invoice level
	results = []
	if not invoice.currency:
		results.append(ValidationResult(
			passed=True, severity="info",
			message="Currency not detected",
			field_path="currency",
		))
	return results


def check_missing_critical_fields(invoice: ExtractedInvoice) -> list[ValidationResult]:
	"""Warn about missing fields that are important but not blocking."""
	results = []
	if not invoice.invoice_number:
		results.append(ValidationResult(
			passed=True, severity="warning",
			message="Invoice number not detected",
			field_path="invoice_number",
		))
	if not invoice.vendor_name:
		results.append(ValidationResult(
			passed=True, severity="warning",
			message="Vendor name not detected",
			field_path="vendor_name",
		))
	if not invoice.total_amount:
		results.append(ValidationResult(
			passed=False, severity="error",
			message="Total amount not detected",
			field_path="total_amount",
		))
	if not invoice.line_items:
		results.append(ValidationResult(
			passed=True, severity="warning",
			message="No line items detected",
			field_path="line_items",
		))
	return results
