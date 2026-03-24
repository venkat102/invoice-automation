"""Whitelisted API endpoints for Invoice Automation."""

import json
import time

import frappe
from frappe import _

INVOICE_ROLES = ("Accounts Manager", "Accounts User", "System Manager")
ADMIN_ROLES = ("Accounts Manager", "System Manager")


def check_roles(roles):
	"""Verify the current user has at least one of the specified roles."""
	if not any(role in frappe.get_roles() for role in roles):
		frappe.throw(_("Insufficient permissions"), frappe.PermissionError)


# ── Extraction Endpoints ──


@frappe.whitelist()
def parse_invoice(file_url=None, extracted_json=None):
	"""Parse a single invoice file. Creates queue record, enqueues extraction + matching.

	Accepts either:
	  - file_url: path to an already-uploaded Frappe file
	  - extracted_json: pre-extracted JSON data (skips extraction)
	"""
	check_roles(INVOICE_ROLES)

	if not file_url and not extracted_json:
		frappe.throw(_("Either file_url or extracted_json is required"))

	queue_doc = frappe.new_doc("Invoice Processing Queue")

	if file_url:
		queue_doc.source_file = file_url

		# Validate and get file info
		try:
			from invoice_automation.extraction.file_handler import FileHandler

			handler = FileHandler()
			file_info = handler.process_file(file_url)
			queue_doc.file_name = file_info.file_name
			queue_doc.file_hash = file_info.file_hash
			queue_doc.file_type = file_info.file_type
			queue_doc.file_size_bytes = file_info.file_size_bytes

			# Check for duplicate file hash
			dup = handler.check_duplicate_hash(file_info.file_hash)
			if dup:
				queue_doc.duplicate_flag = 1
				queue_doc.duplicate_details = f"Duplicate file: same hash as {dup}"
		except Exception as e:
			queue_doc.processing_error = str(e)

		queue_doc.extraction_status = "Pending"

	if extracted_json:
		if isinstance(extracted_json, str):
			try:
				extracted_json = json.loads(extracted_json)
			except (json.JSONDecodeError, TypeError) as e:
				frappe.throw(_("Invalid extracted_json: {0}").format(str(e)))
		if not isinstance(extracted_json, dict):
			frappe.throw(_("extracted_json must be a JSON object"))
		queue_doc.extracted_data = json.dumps(extracted_json)
		queue_doc.extraction_status = "Completed"
		queue_doc.extraction_method = "json_direct"

	queue_doc.insert()

	# Enqueue the pipeline
	from invoice_automation.utils.helpers import enqueue_if_scheduler_active
	enqueue_if_scheduler_active(
		"invoice_automation.api.endpoints._run_full_pipeline",
		queue_name=queue_doc.name,
		queue="default",
		timeout=600,
	)

	return {"queue_name": queue_doc.name, "status": "queued"}


@frappe.whitelist()
def parse_invoices_batch(file_urls=None):
	"""Parse multiple invoice files. Returns list of queued and rejected files."""
	check_roles(INVOICE_ROLES)

	if isinstance(file_urls, str):
		file_urls = json.loads(file_urls)

	if not file_urls:
		frappe.throw(_("file_urls is required"))

	try:
		enabled = frappe.db.get_single_value("Invoice Automation Settings", "enable_batch_parse")
	except Exception:
		enabled = True  # Default to enabled if settings not configured
	if not enabled:
		frappe.throw(_("Batch parsing is disabled in settings"))

	queued = []
	rejected = []

	for url in file_urls:
		try:
			result = parse_invoice(file_url=url)
			queued.append(result)
		except Exception as e:
			rejected.append({"file_url": url, "error": str(e)})

	return {"queued": queued, "rejected": rejected, "total": len(file_urls)}


@frappe.whitelist()
def get_extraction_result(queue_name):
	"""Returns extraction status and data for a queue record."""
	check_roles(INVOICE_ROLES)
	doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	return {
		"name": doc.name,
		"extraction_status": doc.extraction_status,
		"extraction_method": doc.extraction_method,
		"document_type_detected": doc.document_type_detected,
		"extraction_confidence": doc.extraction_confidence,
		"extraction_time_ms": doc.extraction_time_ms,
		"extraction_warnings": json.loads(doc.extraction_warnings) if doc.extraction_warnings else [],
		"extracted_data": json.loads(doc.extracted_data) if doc.extracted_data else None,
		"processing_error": doc.processing_error,
	}


# ── Review Endpoints ──


@frappe.whitelist()
def get_review_data(queue_name):
	"""Returns extracted vs matched data side-by-side for the review dialog."""
	check_roles(INVOICE_ROLES)
	doc = frappe.get_doc("Invoice Processing Queue", queue_name)
	extracted_data = json.loads(doc.extracted_data) if doc.extracted_data else {}

	# Header: extracted vs matched
	header = {
		"supplier": {
			"extracted": extracted_data.get("vendor_name", ""),
			"extracted_tax_id": extracted_data.get("vendor_tax_id", ""),
			"matched": doc.matched_supplier or "",
			"confidence": doc.supplier_match_confidence or 0,
			"stage": doc.supplier_match_stage or "",
		},
		"invoice_number": {
			"extracted": extracted_data.get("invoice_number", ""),
			"matched": doc.matched_bill_no or "",
		},
		"invoice_date": {
			"extracted": extracted_data.get("invoice_date", ""),
			"matched": str(doc.matched_bill_date) if doc.matched_bill_date else "",
		},
		"due_date": {
			"extracted": extracted_data.get("due_date", ""),
			"matched": str(doc.matched_due_date) if doc.matched_due_date else "",
		},
		"currency": {
			"extracted": extracted_data.get("currency", ""),
			"matched": doc.matched_currency or "",
		},
		"total_amount": {
			"extracted": extracted_data.get("total_amount", ""),
			"matched": doc.matched_total or 0,
		},
		"tax_template": {
			"matched": doc.matched_tax_template or "",
		},
		"cost_center": {
			"matched": doc.matched_cost_center or "",
		},
	}

	# Line items: extracted vs matched
	extracted_lines = extracted_data.get("line_items", [])
	matched_lines = []
	for li in doc.line_items:
		matched_lines.append({
			"line_number": li.line_number,
			"extracted_description": li.extracted_description or "",
			"extracted_qty": li.extracted_qty,
			"extracted_rate": li.extracted_rate,
			"extracted_amount": li.extracted_amount,
			"extracted_hsn": li.extracted_hsn,
			"extracted_unit": li.extracted_unit,
			"matched_item": li.matched_item or "",
			"match_confidence": li.match_confidence or 0,
			"match_stage": li.match_stage or "",
			"is_corrected": li.is_corrected,
		})

	# If matching hasn't run, build from extracted data
	if not matched_lines and extracted_lines:
		for i, eli in enumerate(extracted_lines):
			matched_lines.append({
				"line_number": i + 1,
				"extracted_description": eli.get("description", ""),
				"extracted_qty": eli.get("quantity") or eli.get("qty"),
				"extracted_rate": eli.get("unit_price") or eli.get("rate"),
				"extracted_amount": eli.get("line_total") or eli.get("amount"),
				"extracted_hsn": eli.get("hsn_sac_code") or eli.get("hsn_code"),
				"extracted_unit": eli.get("unit", ""),
				"matched_item": "",
				"match_confidence": 0,
				"match_stage": "",
				"is_corrected": 0,
			})

	# Validation flags
	validation = {
		"amount_mismatch": doc.amount_mismatch,
		"amount_mismatch_details": doc.amount_mismatch_details,
		"duplicate_flag": doc.duplicate_flag,
		"duplicate_details": doc.duplicate_details,
	}

	# Extraction warnings
	extraction_warnings = []
	if doc.extraction_warnings:
		try:
			extraction_warnings = json.loads(doc.extraction_warnings)
		except (json.JSONDecodeError, TypeError):
			pass

	return {
		"name": doc.name,
		"workflow_state": doc.workflow_state,
		"extraction_status": doc.extraction_status,
		"matching_status": doc.matching_status,
		"overall_confidence": doc.overall_confidence or 0,
		"routing_decision": doc.routing_decision or "",
		"header": header,
		"line_items": matched_lines,
		"validation": validation,
		"extraction_warnings": extraction_warnings,
	}


# ── Matching Endpoints ──


@frappe.whitelist()
def trigger_matching(queue_name):
	"""Manually trigger matching for an already-extracted invoice."""
	check_roles(INVOICE_ROLES)
	doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	if doc.extraction_status != "Completed":
		frappe.throw(_("Extraction not completed yet"))

	from invoice_automation.utils.helpers import enqueue_if_scheduler_active
	enqueue_if_scheduler_active(
		"invoice_automation.api.endpoints._run_matching",
		queue_name=queue_name,
		queue="default",
		timeout=300,
	)

	return {"queue_name": queue_name, "status": "matching_queued"}


@frappe.whitelist()
def get_match_results(queue_name):
	"""Returns matching status and per-field confidence scores."""
	check_roles(INVOICE_ROLES)
	doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	return {
		"name": doc.name,
		"matching_status": doc.matching_status,
		"routing_decision": doc.routing_decision,
		"overall_confidence": doc.overall_confidence,
		"matched_supplier": doc.matched_supplier,
		"supplier_match_confidence": doc.supplier_match_confidence,
		"supplier_match_stage": doc.supplier_match_stage,
		"matched_bill_no": doc.matched_bill_no,
		"matched_bill_date": str(doc.matched_bill_date) if doc.matched_bill_date else None,
		"matched_data": json.loads(doc.matched_data) if doc.matched_data else None,
		"line_items": [
			{
				"line_number": li.line_number,
				"extracted_description": li.extracted_description,
				"matched_item": li.matched_item,
				"match_confidence": li.match_confidence,
				"match_stage": li.match_stage,
				"is_corrected": li.is_corrected,
			}
			for li in doc.line_items
		],
		"duplicate_flag": doc.duplicate_flag,
		"duplicate_details": doc.duplicate_details,
		"processing_error": doc.processing_error,
	}


# ── Review & Correction Endpoints ──


def apply_corrections(queue_doc, corrections=None, header_overrides=None):
	"""Validate and apply corrections + header overrides to a queue doc.

	Processes correction memory (aliases, logs, embeddings) so the system learns.
	Returns the number of corrections applied.
	"""
	from invoice_automation.memory.correction_handler import process_correction

	corrections_applied = 0

	# Apply header overrides (e.g. supplier correction from review dialog)
	if header_overrides:
		if isinstance(header_overrides, str):
			try:
				header_overrides = json.loads(header_overrides)
			except (json.JSONDecodeError, TypeError) as e:
				frappe.throw(_("Invalid header_overrides JSON: {0}").format(str(e)))
		if header_overrides.get("supplier"):
			if not frappe.db.exists("Supplier", header_overrides["supplier"]):
				frappe.throw(_("Supplier '{0}' does not exist").format(header_overrides["supplier"]))
			queue_doc.matched_supplier = header_overrides["supplier"]

	if corrections:
		if isinstance(corrections, str):
			try:
				corrections = json.loads(corrections)
			except (json.JSONDecodeError, TypeError) as e:
				frappe.throw(_("Invalid corrections JSON: {0}").format(str(e)))
		if not isinstance(corrections, list):
			frappe.throw(_("corrections must be a JSON array"))

		for correction in corrections:
			if not correction.get("line_number") or not correction.get("corrected_item"):
				frappe.throw(_("Each correction must have 'line_number' and 'corrected_item'"))
			if not frappe.db.exists("Item", correction["corrected_item"]):
				frappe.throw(_("Item '{0}' does not exist").format(correction["corrected_item"]))

		for correction in corrections:
			if correction.get("line_number"):
				process_correction(
					queue_name=queue_doc.name,
					line_number=correction["line_number"],
					corrected_item=correction["corrected_item"],
					source_doctype="Item",
					reasoning=correction.get("reasoning"),
				)

				for li in queue_doc.line_items:
					if li.line_number == correction["line_number"]:
						li.original_match = li.matched_item
						li.matched_item = correction["corrected_item"]
						li.is_corrected = 1
						li.match_stage = "Manual"
						li.match_confidence = 100
						li.correction_reasoning = correction.get("reasoning")
						corrections_applied += 1
						break

	return corrections_applied


@frappe.whitelist()
def save_corrections(queue_name, corrections=None, header_overrides=None):
	"""Save corrections without creating a Purchase Invoice.

	Teaches the system (aliases, correction logs, embeddings) so future invoices
	benefit from the corrections. Use this when you want to correct mappings but
	defer or skip PI creation — e.g. on rejected invoices or Manual Entry items.
	"""
	check_roles(INVOICE_ROLES)

	queue_doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	corrections_applied = apply_corrections(queue_doc, corrections, header_overrides)

	if corrections_applied or header_overrides:
		queue_doc.save(ignore_permissions=True)
		frappe.db.commit()

	return {
		"status": "corrections_saved",
		"queue_name": queue_name,
		"corrections_applied": corrections_applied,
	}


@frappe.whitelist()
def confirm_mapping(queue_name, corrections=None, header_overrides=None):
	"""Confirms mapping with optional corrections. Creates Purchase Invoice as Draft."""
	check_roles(INVOICE_ROLES)

	from invoice_automation.validation.duplicate_detector import check_duplicate

	queue_doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	apply_corrections(queue_doc, corrections, header_overrides)

	# Check for duplicates
	extracted_data = json.loads(queue_doc.extracted_data) if queue_doc.extracted_data else {}
	supplier = queue_doc.matched_supplier or ""

	dup_result = check_duplicate(
		supplier=supplier,
		bill_no=queue_doc.matched_bill_no or extracted_data.get("invoice_number", ""),
		bill_date=str(queue_doc.matched_bill_date) if queue_doc.matched_bill_date else extracted_data.get("invoice_date", ""),
		grand_total=queue_doc.matched_total or extracted_data.get("total_amount", 0),
	)

	if dup_result.get("is_duplicate"):
		queue_doc.duplicate_flag = 1
		queue_doc.duplicate_details = dup_result.get("details", "")
		if dup_result.get("block"):
			queue_doc.save(ignore_permissions=True)
			frappe.db.commit()
			return {"status": "blocked", "reason": "exact_duplicate", "details": dup_result}

	# Create Purchase Invoice as Draft
	pi = _create_purchase_invoice(queue_doc, extracted_data)

	queue_doc.purchase_invoice = pi.name
	queue_doc.workflow_state = "Invoice Created"
	queue_doc.processed_by = frappe.session.user
	queue_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "success", "purchase_invoice": pi.name}


@frappe.whitelist()
def reject_invoice(queue_name, reason=None):
	"""Marks an invoice as rejected."""
	check_roles(INVOICE_ROLES)
	doc = frappe.get_doc("Invoice Processing Queue", queue_name)
	doc.workflow_state = "Rejected"
	if reason:
		doc.processing_error = reason
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "rejected", "queue_name": queue_name}


# ── Index Management ──


@frappe.whitelist()
def rebuild_index(index_type="all"):
	"""Triggers rebuild of Redis index, embedding index, or both."""
	check_roles(ADMIN_ROLES)

	from invoice_automation.utils.helpers import enqueue_if_scheduler_active
	if index_type in ("redis", "all"):
		enqueue_if_scheduler_active(
			"invoice_automation.utils.redis_index.rebuild_all",
			queue="long", timeout=600,
		)
	if index_type in ("embeddings", "all"):
		enqueue_if_scheduler_active(
			"invoice_automation.embeddings.index_builder.build_full_index",
			queue="long", timeout=1800,
		)
	return {"status": "rebuild_enqueued", "index_type": index_type}


# ── Health & Diagnostics ──


@frappe.whitelist()
def health_check():
	"""Returns system health: Ollama, Redis, embedding model, index sizes."""
	check_roles(ADMIN_ROLES)
	health = {}

	# Extraction LLM
	try:
		from invoice_automation.llm import get_llm_provider
		health["extraction_llm"] = get_llm_provider("extraction").health_check()
	except Exception as e:
		health["extraction_llm"] = {"status": "error", "error": str(e)}

	# Matching LLM
	try:
		from invoice_automation.llm import get_llm_provider as get_provider
		health["matching_llm"] = get_provider("matching").health_check()
	except Exception as e:
		health["matching_llm"] = {"status": "error", "error": str(e)}

	# Redis
	try:
		frappe.cache().set_value("invoice_automation:health", "ok")
		health["redis"] = {"status": "connected"}
	except Exception as e:
		health["redis"] = {"status": "error", "error": str(e)}

	# Embedding index size and rebuild status
	try:
		count = frappe.db.count("Embedding Index")
		settings = frappe.get_cached_doc("Invoice Automation Settings")
		health["embedding_index"] = {
			"status": settings.embedding_index_status or "unknown",
			"count": count,
			"last_rebuild": str(settings.last_embedding_rebuild) if settings.last_embedding_rebuild else None,
		}
		health["redis_index"] = {
			"status": settings.redis_index_status or "unknown",
			"count": settings.redis_index_count or 0,
			"last_rebuild": str(settings.last_redis_rebuild) if settings.last_redis_rebuild else None,
		}
	except Exception:
		health["embedding_index"] = {"status": "unknown"}
		health["redis_index"] = {"status": "unknown"}

	# Queue depths
	try:
		pending = frappe.db.count("Invoice Processing Queue", {"workflow_state": "Pending"})
		processing = frappe.db.count("Invoice Processing Queue", {"workflow_state": ["in", ["Extracting", "Matching"]]})
		health["queue"] = {"pending": pending, "processing": processing}
	except Exception:
		health["queue"] = {"status": "unknown"}

	return health


@frappe.whitelist()
def get_system_stats():
	"""Returns analytics on system performance."""
	check_roles(ADMIN_ROLES)
	total_processed = frappe.db.count("Invoice Processing Queue", {"extraction_status": "Completed"})
	total_corrections = frappe.db.count("Mapping Correction Log")
	total_aliases = frappe.db.count("Mapping Alias", {"is_active": 1})
	auto_created = frappe.db.count("Invoice Processing Queue", {"routing_decision": "Auto Create"})

	auto_rate = (auto_created / total_processed * 100) if total_processed > 0 else 0

	top_items = frappe.db.sql("""
		SELECT human_selected, COUNT(*) as count
		FROM `tabMapping Correction Log`
		WHERE source_doctype = 'Item'
		GROUP BY human_selected ORDER BY count DESC LIMIT 10
	""", as_dict=True)

	top_suppliers = frappe.db.sql("""
		SELECT supplier, COUNT(*) as count
		FROM `tabMapping Correction Log`
		WHERE supplier IS NOT NULL
		GROUP BY supplier ORDER BY count DESC LIMIT 10
	""", as_dict=True)

	return {
		"total_processed": total_processed,
		"total_corrections": total_corrections,
		"total_aliases": total_aliases,
		"auto_created": auto_created,
		"auto_create_rate": round(auto_rate, 1),
		"top_corrected_items": top_items,
		"top_corrected_suppliers": top_suppliers,
	}


@frappe.whitelist()
def get_config():
	"""Returns current settings (non-sensitive fields)."""
	check_roles(ADMIN_ROLES)
	try:
		doc = frappe.get_cached_doc("Invoice Automation Settings")
		return {
			"extraction_llm_provider": doc.extraction_llm_provider or "Ollama",
			"matching_llm_provider": doc.matching_llm_provider or "Anthropic",
			"ollama_base_url": doc.ollama_base_url,
			"ollama_model": doc.ollama_model,
			"auto_create_threshold": doc.auto_create_threshold,
			"review_threshold": doc.review_threshold,
			"enable_llm_matching": doc.enable_llm_matching,
			"enable_auto_create": doc.enable_auto_create,
			"max_file_size_mb": doc.max_file_size_mb,
			"allowed_extensions": doc.allowed_extensions,
		}
	except Exception:
		return {"error": "Settings not configured"}


# ── Internal Pipeline Functions ──


def _run_full_pipeline(queue_name):
	"""Background job: extraction → matching."""
	total_start = time.time()
	doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	try:
		# Step 1: Extraction (if not already done)
		if doc.extraction_status != "Completed":
			_run_extraction(doc)
			doc.reload()

		# Step 2: Matching
		if doc.extraction_status == "Completed":
			_run_matching(queue_name)
			doc.reload()

		doc.total_processing_time_ms = int((time.time() - total_start) * 1000)
		doc.save(ignore_permissions=True)
		frappe.db.commit()

	except Exception as e:
		doc.reload()
		doc.processing_error = str(e)
		doc.workflow_state = "Failed"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.log_error(f"Pipeline failed for {queue_name}: {e}")


def _run_extraction(doc):
	"""Run extraction on an invoice queue record."""
	from invoice_automation.extraction.extraction_service import ExtractionService

	doc.extraction_status = "Processing"
	doc.workflow_state = "Extracting"
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		service = ExtractionService()

		if doc.source_file:
			result = service.extract_from_file(doc.source_file)
		elif doc.extracted_data:
			result = service.extract_from_json(json.loads(doc.extracted_data))
		else:
			doc.extraction_status = "Failed"
			doc.processing_error = "No source file or extracted data"
			doc.save(ignore_permissions=True)
			return

		if result.success and result.extracted_invoice:
			invoice = result.extracted_invoice
			doc.extracted_data = json.dumps(invoice.model_dump(), default=str)
			doc.extraction_status = "Completed"
			doc.workflow_state = "Extracted"
			doc.extraction_method = result.extraction_method
			doc.extraction_time_ms = result.extraction_time_ms
			doc.extraction_confidence = invoice.extraction_confidence
			doc.document_type_detected = invoice.document_type

			if result.parsed_document:
				doc.raw_parsed_text = result.parsed_document.text[:65000]  # Field limit

			if result.validation_results:
				doc.validation_results = json.dumps(
					[{"passed": v.passed, "severity": v.severity, "message": v.message, "field_path": v.field_path}
					 for v in result.validation_results], default=str
				)

			if result.warnings:
				doc.extraction_warnings = json.dumps(
					[w.model_dump() for w in result.warnings], default=str
				)
		else:
			doc.extraction_status = "Failed"
			doc.workflow_state = "Failed"
			# Include warning details in the error message for better diagnostics
			warning_msgs = [w.message for w in result.warnings] if result.warnings else []
			error_detail = result.error or "Extraction produced no result"
			if warning_msgs:
				error_detail += " | Warnings: " + "; ".join(warning_msgs)
			doc.processing_error = error_detail

			if result.warnings:
				doc.extraction_warnings = json.dumps(
					[w.model_dump() for w in result.warnings], default=str
				)

		doc.save(ignore_permissions=True)
		frappe.db.commit()

	except Exception as e:
		doc.extraction_status = "Failed"
		doc.workflow_state = "Failed"
		doc.processing_error = str(e)
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.log_error(f"Extraction failed for {doc.name}: {e}")


def _run_matching(queue_name):
	"""Run the matching pipeline on an extracted invoice."""
	from invoice_automation.matching.pipeline import MatchingPipeline
	from invoice_automation.extraction.schema import ExtractedInvoice

	doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	try:
		doc.matching_status = "Processing"
		doc.workflow_state = "Matching"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		extracted_data = json.loads(doc.extracted_data)
		invoice = ExtractedInvoice(**extracted_data)

		# Build a dict for the pipeline (which accepts both dict and pydantic)
		pipeline_input = {
			"supplier_name": invoice.vendor_name,
			"supplier_tax_id": invoice.vendor_tax_id,
			"invoice_number": invoice.invoice_number,
			"invoice_date": invoice.invoice_date,
			"due_date": invoice.due_date,
			"total_amount": invoice.total_amount,
			"currency": invoice.currency,
			"company_tax_id": invoice.customer_tax_id,
			"line_items": [
				{
					"description": li.description,
					"qty": li.quantity,
					"rate": li.unit_price,
					"amount": li.line_total,
					"hsn_code": li.hsn_sac_code,
				}
				for li in invoice.line_items
			],
			"taxes": [
				{
					"tax_type": td.get("tax_type", ""),
					"rate": td.get("rate", 0),
					"amount": td.get("amount", 0),
				}
				for td in (invoice.tax_details or [])
			],
		}

		pipeline = MatchingPipeline()
		result = pipeline.process(pipeline_input)

		doc.matched_data = json.dumps(result.to_dict(), default=str)
		doc.matching_status = "Completed"
		doc.routing_decision = result.routing_decision
		doc.overall_confidence = result.overall_confidence
		doc.matching_time_ms = result.processing_time_ms

		# Populate matched header fields
		if result.supplier_match.matched:
			doc.matched_supplier = result.supplier_match.matched_name
			doc.supplier_match_confidence = result.supplier_match.confidence
			doc.supplier_match_stage = result.supplier_match.stage

		doc.matched_bill_no = invoice.invoice_number
		doc.matched_bill_date = invoice.invoice_date
		doc.matched_due_date = invoice.due_date
		doc.matched_currency = invoice.currency
		doc.matched_total = float(invoice.total_amount) if invoice.total_amount else None

		# Populate matched tax template from tax matches
		for tm in result.tax_matches:
			if tm.matched and tm.matched_name:
				doc.matched_tax_template = tm.matched_name
				break

		# Run amount validation
		from invoice_automation.validation.amount_validator import validate_amounts

		amount_line_items = []
		for i, li_data in enumerate(invoice.line_items):
			lm = result.line_item_matches[i] if i < len(result.line_item_matches) else None
			amount_line_items.append({
				"qty": li_data.quantity,
				"rate": li_data.unit_price,
				"tax_rate": li_data.tax_rate,
			})

		amount_result = validate_amounts({"total_amount": invoice.total_amount}, amount_line_items)
		if not amount_result["is_valid"]:
			doc.amount_mismatch = 1
			doc.amount_mismatch_details = (
				f"Computed: {amount_result['computed_total']}, "
				f"Extracted: {amount_result['extracted_total']}, "
				f"Difference: {amount_result['difference']}"
			)

		# Set workflow state based on routing decision
		if result.routing_decision == "Review Queue":
			doc.workflow_state = "Under Review"
		else:
			doc.workflow_state = "Routed"

		# Populate line items child table
		doc.line_items = []
		for i, lm in enumerate(result.line_item_matches):
			li_data = invoice.line_items[i] if i < len(invoice.line_items) else None
			doc.append("line_items", {
				"line_number": i + 1,
				"extracted_description": lm.details.get("raw_text", li_data.description if li_data else ""),
				"extracted_qty": str(li_data.quantity) if li_data and li_data.quantity else None,
				"extracted_rate": str(li_data.unit_price) if li_data and li_data.unit_price else None,
				"extracted_amount": str(li_data.line_total) if li_data and li_data.line_total else None,
				"extracted_hsn": li_data.hsn_sac_code if li_data else None,
				"extracted_unit": li_data.unit if li_data else None,
				"extracted_item_code": li_data.item_code if li_data else None,
				"matched_item": lm.matched_name if lm.matched else None,
				"match_confidence": lm.confidence,
				"match_stage": lm.stage,
				"match_details": json.dumps(lm.details),
			})

		doc.save(ignore_permissions=True)
		frappe.db.commit()

	except Exception as e:
		doc.reload()
		doc.matching_status = "Failed"
		doc.processing_error = str(e)
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.log_error(f"Matching failed for {queue_name}: {e}")


def _create_purchase_invoice(queue_doc, extracted_data):
	"""Create a Draft Purchase Invoice from matched or extracted data. Never auto-submit."""
	pi = frappe.new_doc("Purchase Invoice")

	# Header — prefer matched values, fall back to extracted data
	pi.supplier = queue_doc.matched_supplier or _resolve_supplier(extracted_data)
	pi.bill_no = queue_doc.matched_bill_no or extracted_data.get("invoice_number")
	pi.bill_date = queue_doc.matched_bill_date or extracted_data.get("invoice_date")
	pi.due_date = queue_doc.matched_due_date or extracted_data.get("due_date")

	currency = queue_doc.matched_currency or extracted_data.get("currency")
	if currency:
		pi.currency = currency

	if queue_doc.matched_cost_center:
		pi.cost_center = queue_doc.matched_cost_center

	# Line items — use matched line items if available, otherwise fall back to extracted data
	if queue_doc.line_items:
		for li in queue_doc.line_items:
			pi.append("items", {
				"item_code": li.matched_item,
				"qty": float(li.extracted_qty) if li.extracted_qty else 1,
				"rate": float(li.extracted_rate) if li.extracted_rate else 0,
				"description": li.extracted_description,
			})
	else:
		# No matching ran — build items from extracted data
		line_items = extracted_data.get("line_items", [])
		for li in line_items:
			pi.append("items", {
				"qty": float(li.get("quantity") or li.get("qty") or 1),
				"rate": float(li.get("unit_price") or li.get("rate") or 0),
				"description": li.get("description", ""),
			})

	# Apply matched tax template
	if queue_doc.matched_tax_template:
		pi.taxes_and_charges = queue_doc.matched_tax_template
		pi.set_taxes()

	pi.flags.ignore_permissions = True
	pi.set_missing_values()
	pi.insert(ignore_permissions=True)

	return pi


def _resolve_supplier(extracted_data):
	"""Try to find a Supplier from the extracted vendor name. Returns name or None."""
	vendor_name = extracted_data.get("vendor_name")
	if not vendor_name:
		return None

	# Exact match by supplier_name
	supplier = frappe.db.get_value("Supplier", {"supplier_name": vendor_name}, "name")
	if supplier:
		return supplier

	# Try tax ID match
	tax_id = extracted_data.get("vendor_tax_id")
	if tax_id:
		supplier = frappe.db.get_value("Supplier", {"tax_id": tax_id}, "name")
		if supplier:
			return supplier

	return None
