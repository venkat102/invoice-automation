"""Main extraction orchestrator: file → parse → extract → normalize → validate."""

import json
import time
from dataclasses import dataclass, field

import frappe

from invoice_automation.extraction.file_handler import FileHandler, FileInfo
from invoice_automation.extraction.parsers.base_parser import get_parser, ParsedDocument
from invoice_automation.extraction.prompt_templates import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_PROMPT
from invoice_automation.extraction.schema import ExtractedInvoice, ExtractionWarning
from invoice_automation.extraction.normalizers.currency_normalizer import normalize_currency
from invoice_automation.extraction.normalizers.date_normalizer import normalize_date
from invoice_automation.extraction.normalizers.line_item_normalizer import normalize_line_items
from invoice_automation.extraction.normalizers.text_normalizer import normalize_text
from invoice_automation.extraction.validators.validation_service import run_all_checks
from invoice_automation.utils.exceptions import ExtractionError


@dataclass
class ExtractionResult:
	"""Full result of the extraction pipeline."""
	extracted_invoice: ExtractedInvoice | None = None
	file_info: FileInfo | None = None
	parsed_document: ParsedDocument | None = None
	extraction_method: str = ""
	extraction_time_ms: int = 0
	warnings: list[ExtractionWarning] = field(default_factory=list)
	validation_results: list = field(default_factory=list)
	success: bool = False
	error: str | None = None


class ExtractionService:
	"""Orchestrates the full extraction pipeline."""

	def extract_from_file(self, file_url: str) -> ExtractionResult:
		"""Full pipeline: file handling → parser → LLM extraction → normalization → validation."""
		start = time.time()
		result = ExtractionResult()

		try:
			# Step 1: File handling
			handler = FileHandler()
			file_info = handler.process_file(file_url)
			result.file_info = file_info

			# Step 2: Parse file to text
			parser = get_parser(file_info)
			parsed = parser.parse(file_info)
			result.parsed_document = parsed
			result.extraction_method = parsed.parsing_method

			for w in parsed.warnings:
				result.warnings.append(ExtractionWarning(
					category="parsing", message=w, severity="warning",
				))

			if not parsed.text.strip():
				result.warnings.append(ExtractionWarning(
					category="no_text",
					message="No text extracted from file",
					severity="error",
				))
				result.extraction_time_ms = int((time.time() - start) * 1000)
				return result

			# Step 3: LLM extraction
			invoice = self._extract_with_llm(parsed.text)
			result.extracted_invoice = invoice

			# Step 4: Normalize fields
			self._normalize(invoice)

			# Step 5: Validate
			validation_results = run_all_checks(invoice)
			result.validation_results = validation_results

			# Merge warnings
			result.warnings.extend(invoice.warnings)

			result.success = True

		except ExtractionError as e:
			result.error = str(e)
			result.warnings.append(ExtractionWarning(
				category="extraction_error", message=str(e), severity="error",
			))
		except Exception as e:
			result.error = str(e)
			result.warnings.append(ExtractionWarning(
				category="unexpected_error", message=str(e), severity="error",
			))
			frappe.log_error(f"Extraction failed: {e}", "Invoice Extraction Error")

		result.extraction_time_ms = int((time.time() - start) * 1000)
		return result

	def extract_from_json(self, data: dict) -> ExtractionResult:
		"""Parse pre-extracted JSON data (skip file parsing and LLM)."""
		start = time.time()
		result = ExtractionResult()

		try:
			invoice = ExtractedInvoice(**data)
			self._normalize(invoice)
			validation_results = run_all_checks(invoice)

			result.extracted_invoice = invoice
			result.extraction_method = "json_direct"
			result.validation_results = validation_results
			result.warnings = list(invoice.warnings)
			result.success = True

		except (ValueError, TypeError) as e:
			result.error = f"Invalid extraction data: {e}"
		except Exception as e:
			result.error = str(e)
			frappe.log_error(f"JSON extraction failed: {e}", "Invoice Extraction Error")

		result.extraction_time_ms = int((time.time() - start) * 1000)
		return result

	def _extract_with_llm(self, document_text: str) -> ExtractedInvoice:
		"""Send text to the configured LLM provider and parse the structured JSON response."""
		from invoice_automation.extraction.prompt_templates import (
			build_dynamic_prompt,
			get_custom_extraction_fields,
		)
		from invoice_automation.extraction.schema import build_dynamic_model
		from invoice_automation.llm import get_llm_provider

		provider = get_llm_provider("extraction")

		# Load custom extraction fields and build dynamic prompt/schema
		custom_fields = get_custom_extraction_fields()
		extraction_prompt = build_dynamic_prompt(custom_fields)
		model_class = build_dynamic_model(custom_fields)

		prompt = extraction_prompt.format(
			document_text=document_text[:8000],  # Limit to avoid token overflow
		)

		data = provider.generate_json(prompt, system=EXTRACTION_SYSTEM_PROMPT)

		# Parse line items separately if they came as raw dicts
		if "line_items" in data and isinstance(data["line_items"], list):
			data["line_items"] = normalize_line_items(data["line_items"])

		# Parse warnings
		if "warnings" in data and isinstance(data["warnings"], list):
			cleaned_warnings = []
			for w in data["warnings"]:
				if isinstance(w, dict):
					cleaned_warnings.append(w)
				elif isinstance(w, str):
					cleaned_warnings.append({"category": "llm_warning", "message": w, "severity": "info"})
			data["warnings"] = cleaned_warnings

		return model_class(**data)

	def _normalize(self, invoice: ExtractedInvoice):
		"""Apply all normalizers to the extracted invoice in-place."""
		# Currency
		if invoice.currency:
			invoice.currency = normalize_currency(invoice.currency) or invoice.currency

		# Dates
		warnings = []
		if invoice.invoice_date:
			normalized, warning = normalize_date(invoice.invoice_date)
			invoice.invoice_date = normalized
			if warning:
				warnings.append(warning)

		if invoice.due_date:
			normalized, warning = normalize_date(invoice.due_date)
			invoice.due_date = normalized
			if warning:
				warnings.append(warning)

		# Text fields
		if invoice.vendor_name:
			invoice.vendor_name = normalize_text(invoice.vendor_name) or invoice.vendor_name
		if invoice.customer_name:
			invoice.customer_name = normalize_text(invoice.customer_name) or invoice.customer_name

		# Add normalization warnings
		invoice.warnings.extend(warnings)

		# Apply normalizers to custom extraction fields
		from invoice_automation.extraction.prompt_templates import get_custom_extraction_fields

		custom_fields = get_custom_extraction_fields()
		for cf in custom_fields:
			if not cf.get("enabled") or cf.get("normalizer", "None") == "None":
				continue
			field_name = cf["field_name"]
			value = getattr(invoice, field_name, None)
			if not value:
				continue
			normalizer_type = cf["normalizer"]
			if normalizer_type == "Text":
				setattr(invoice, field_name, normalize_text(value) or value)
			elif normalizer_type == "Date":
				normalized, warning = normalize_date(value)
				setattr(invoice, field_name, normalized)
				if warning:
					warnings.append(warning)
			elif normalizer_type == "Currency":
				setattr(invoice, field_name, normalize_currency(value) or value)

		# Excerpt for debugging
		if not invoice.raw_text_excerpt and invoice.vendor_name:
			invoice.raw_text_excerpt = f"Vendor: {invoice.vendor_name}, Invoice: {invoice.invoice_number}"
