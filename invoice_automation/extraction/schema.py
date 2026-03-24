"""Pydantic v2 models for invoice extraction output."""

from pydantic import BaseModel, Field


class ExtractionWarning(BaseModel):
	"""A structured warning from the extraction process."""
	category: str  # ambiguous_date, missing_total, ocr_noise, multiple_invoices, etc.
	message: str
	severity: str = "warning"  # error, warning, info
	field_path: str | None = None  # e.g. "line_items[2].unit_price"
	raw_evidence: str | None = None


class ExtractedLineItem(BaseModel):
	"""A single line item from an invoice."""
	line_number: int | None = None
	description: str | None = None
	quantity: str | None = None  # Decimal as string
	unit: str | None = None
	unit_price: str | None = None  # Decimal as string
	tax_rate: str | None = None
	tax_amount: str | None = None
	discount_amount: str | None = None
	line_total: str | None = None  # Decimal as string
	hsn_sac_code: str | None = None
	sku: str | None = None
	item_code: str | None = None  # Vendor's item code if printed


class ExtractedInvoice(BaseModel):
	"""Complete extraction output. All monetary fields use string representation of Decimal."""

	# Document classification
	document_type: str | None = None  # invoice, credit_note, debit_note, proforma, quotation, delivery_challan, purchase_order, unknown
	document_type_confidence: float | None = None

	# Vendor/Supplier fields
	vendor_name: str | None = None
	vendor_address: str | None = None
	vendor_tax_id: str | None = None  # GSTIN, VAT, TIN
	vendor_pan: str | None = None
	vendor_phone: str | None = None
	vendor_email: str | None = None

	# Customer/Buyer fields
	customer_name: str | None = None
	customer_address: str | None = None
	customer_tax_id: str | None = None
	customer_pan: str | None = None

	# Invoice header
	invoice_number: str | None = None
	invoice_date: str | None = None  # ISO 8601
	due_date: str | None = None
	purchase_order_number: str | None = None
	delivery_note_number: str | None = None

	# Financial summary (Decimal as string)
	currency: str | None = None  # ISO 4217
	subtotal: str | None = None
	tax_amount: str | None = None
	cgst_amount: str | None = None
	sgst_amount: str | None = None
	igst_amount: str | None = None
	cess_amount: str | None = None
	discount_amount: str | None = None
	shipping_amount: str | None = None
	round_off_amount: str | None = None
	total_amount: str | None = None
	amount_paid: str | None = None
	balance_due: str | None = None

	# Tax details
	tax_details: list[dict] | None = Field(default_factory=list)
	is_reverse_charge: bool | None = None
	place_of_supply: str | None = None

	# Payment
	payment_terms: str | None = None
	payment_method: str | None = None
	bank_details: dict | None = None

	# Line items
	line_items: list[ExtractedLineItem] = Field(default_factory=list)

	# Metadata
	notes: str | None = None

	# Confidence and quality
	extraction_confidence: float | None = None  # 0-100
	field_group_confidence: dict | None = None  # {supplier_fields: 85, invoice_header: 92, ...}
	warnings: list[ExtractionWarning] = Field(default_factory=list)
	raw_text_excerpt: str | None = None


# Backward-compatible alias
ExtractedInvoiceData = ExtractedInvoice


# Type map for dynamic Pydantic fields
_PYDANTIC_TYPE_MAP = {
	"String": str | None,
	"Decimal": str | None,
	"Date": str | None,
	"Boolean": bool | None,
}


def build_dynamic_model(custom_fields=None):
	"""Build a Pydantic model that extends ExtractedInvoice with custom fields.

	Args:
		custom_fields: List of dicts from get_custom_extraction_fields().

	Returns:
		A Pydantic model class (ExtractedInvoice or a dynamic subclass).
	"""
	if not custom_fields:
		return ExtractedInvoice

	enabled_fields = [f for f in custom_fields if f.get("enabled", True)]
	if not enabled_fields:
		return ExtractedInvoice

	from pydantic import create_model

	header_fields = {
		f["field_name"]: (_PYDANTIC_TYPE_MAP.get(f.get("field_type", "String"), str | None), None)
		for f in enabled_fields
		if not f.get("is_line_item_field")
	}

	line_item_fields = {
		f["field_name"]: (_PYDANTIC_TYPE_MAP.get(f.get("field_type", "String"), str | None), None)
		for f in enabled_fields
		if f.get("is_line_item_field")
	}

	# Extend line item model if needed
	line_item_model = ExtractedLineItem
	if line_item_fields:
		line_item_model = create_model(
			"DynamicExtractedLineItem",
			__base__=ExtractedLineItem,
			**line_item_fields,
		)

	# Build the dynamic invoice model
	extra_fields = dict(header_fields)
	if line_item_fields:
		# Override line_items field to use the extended line item model
		extra_fields["line_items"] = (list[line_item_model], Field(default_factory=list))

	if not extra_fields:
		return ExtractedInvoice

	return create_model(
		"DynamicExtractedInvoice",
		__base__=ExtractedInvoice,
		**extra_fields,
	)
