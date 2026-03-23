"""Whitelisted API endpoints for Invoice Automation."""

import json
import time

import frappe
from frappe import _


# ── Extraction Endpoints ──


@frappe.whitelist()
def parse_invoice(file_url=None, extracted_json=None):
	"""Parse a single invoice file. Creates queue record, enqueues extraction + matching.

	Accepts either:
	  - file_url: path to an already-uploaded Frappe file
	  - extracted_json: pre-extracted JSON data (skips extraction)
	"""
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
			extracted_json = json.loads(extracted_json)
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
	if isinstance(file_urls, str):
		file_urls = json.loads(file_urls)

	if not file_urls:
		frappe.throw(_("file_urls is required"))

	try:
		enabled = frappe.db.get_single_value("Invoice Automation Settings", "enable_batch_parse")
		if not enabled:
			frappe.throw(_("Batch parsing is disabled in settings"))
	except Exception:
		pass

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


# ── Matching Endpoints ──


@frappe.whitelist()
def trigger_matching(queue_name):
	"""Manually trigger matching for an already-extracted invoice."""
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


@frappe.whitelist()
def confirm_mapping(queue_name, corrections=None):
	"""Confirms mapping with optional corrections. Creates Purchase Invoice as Draft."""
	from invoice_automation.memory.correction_handler import process_correction
	from invoice_automation.validation.duplicate_detector import check_duplicate

	queue_doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	if corrections:
		if isinstance(corrections, str):
			corrections = json.loads(corrections)

		for correction in corrections:
			if correction.get("line_number"):
				process_correction(
					queue_name=queue_name,
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
						break

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


@frappe.whitelist(allow_guest=True)
def health_check():
	"""Returns system health: Ollama, Redis, embedding model, index sizes."""
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

	# Embedding index size
	try:
		count = frappe.db.count("Embedding Index")
		health["embedding_index"] = {"status": "ok", "count": count}
	except Exception:
		health["embedding_index"] = {"status": "unknown"}

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

			if result.warnings:
				doc.extraction_warnings = json.dumps(
					[w.model_dump() for w in result.warnings], default=str
				)
		else:
			doc.extraction_status = "Failed"
			doc.workflow_state = "Failed"
			doc.processing_error = result.error or "Extraction produced no result"

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
		doc.workflow_state = "Routed"

		# Populate matched header fields
		if result.supplier_match.matched:
			doc.matched_supplier = result.supplier_match.matched_name
			doc.supplier_match_confidence = result.supplier_match.confidence
			doc.supplier_match_stage = result.supplier_match.stage

		doc.matched_bill_no = invoice.invoice_number
		doc.matched_bill_date = invoice.invoice_date
		doc.matched_due_date = invoice.due_date

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
	"""Create a Draft Purchase Invoice. Never auto-submit."""
	pi = frappe.new_doc("Purchase Invoice")
	pi.supplier = queue_doc.matched_supplier
	pi.bill_no = queue_doc.matched_bill_no or extracted_data.get("invoice_number")
	pi.bill_date = queue_doc.matched_bill_date or extracted_data.get("invoice_date")
	pi.due_date = queue_doc.matched_due_date or extracted_data.get("due_date")

	for li in queue_doc.line_items:
		pi.append("items", {
			"item_code": li.matched_item,
			"qty": float(li.extracted_qty) if li.extracted_qty else 1,
			"rate": float(li.extracted_rate) if li.extracted_rate else 0,
		})

	pi.flags.ignore_permissions = True
	pi.set_missing_values()
	pi.insert(ignore_permissions=True)

	return pi
