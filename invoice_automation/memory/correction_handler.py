"""Processes human corrections: creates aliases, logs corrections, updates embeddings."""

import json

import frappe

from invoice_automation.matching.normalizer import normalize_text
from invoice_automation.memory.alias_manager import AliasManager


def process_correction(queue_name, line_number, corrected_item, source_doctype="Item", reasoning=None):
	"""Process a human correction on a matched line item.

	1. Create/update alias
	2. Log the correction
	3. Update historical embedding index (enqueued)
	4. Check for conflicts
	"""
	queue_doc = frappe.get_doc("Invoice Processing Queue", queue_name)

	# Find the line item
	line_item = None
	for li in queue_doc.line_items:
		if li.line_number == line_number:
			line_item = li
			break

	if not line_item:
		frappe.throw(f"Line item {line_number} not found in {queue_name}")

	raw_text = getattr(line_item, "extracted_description", None) or getattr(line_item, "extracted_text", "") or ""
	system_proposed = line_item.matched_item
	system_confidence = line_item.match_confidence
	system_stage = line_item.match_stage

	# Get supplier from matched data
	supplier = None
	if queue_doc.matched_data:
		matched_data = json.loads(queue_doc.matched_data)
		supplier_match = matched_data.get("supplier_match", {})
		supplier = supplier_match.get("matched_name")

	# 1. Create/Update alias
	alias_mgr = AliasManager()
	alias_mgr.upsert_alias(
		raw_text=raw_text,
		canonical_name=corrected_item,
		source_doctype=source_doctype,
		supplier=supplier,
		from_correction=True,
	)

	# 2. Log the correction
	extracted_data = json.loads(queue_doc.extracted_data) if queue_doc.extracted_data else {}

	# Get item group for the corrected item
	item_group = frappe.db.get_value("Item", corrected_item, "item_group") if corrected_item else None

	correction_log = frappe.new_doc("Mapping Correction Log")
	correction_log.source_doctype = source_doctype
	correction_log.raw_extracted_text = raw_text
	correction_log.system_proposed = system_proposed
	correction_log.system_confidence = system_confidence
	correction_log.system_match_stage = system_stage
	correction_log.human_selected = corrected_item
	correction_log.reviewer = frappe.session.user
	correction_log.reviewer_reasoning = reasoning
	correction_log.supplier = supplier
	correction_log.extracted_hsn = line_item.extracted_hsn
	correction_log.item_group_of_correction = item_group
	correction_log.invoice_context = json.dumps({
		"invoice_number": extracted_data.get("invoice_number"),
		"invoice_date": extracted_data.get("invoice_date"),
		"supplier_name": extracted_data.get("supplier_name"),
		"total_amount": extracted_data.get("total_amount"),
	})
	correction_log.insert(ignore_permissions=True)

	# 3. Update historical embedding index (background job)
	frappe.enqueue(
		"invoice_automation.memory.correction_handler._update_embedding_index",
		raw_text=raw_text,
		corrected_item=corrected_item,
		supplier=supplier,
		correction_log_name=correction_log.name,
		hsn_code=line_item.extracted_hsn,
		item_group=item_group,
		queue="default",
		timeout=120,
	)

	# 4. Check for conflicts
	from invoice_automation.memory.conflict_resolver import check_for_conflicts

	conflict = check_for_conflicts(supplier, normalize_text(raw_text), source_doctype, corrected_item)
	if conflict:
		correction_log.is_conflicting = 1
		correction_log.conflicting_correction = conflict.get("conflicting_log")
		correction_log.save(ignore_permissions=True)

	frappe.db.commit()
	return correction_log.name


def _update_embedding_index(raw_text, corrected_item, supplier, correction_log_name, hsn_code=None, item_group=None):
	"""Background job: embed the raw text and store in the historical index."""
	try:
		from invoice_automation.embeddings.model import generate_embedding, embedding_to_list
		from invoice_automation.embeddings.index_manager import get_index_manager

		embedding = generate_embedding(raw_text)
		embedding_list = embedding_to_list(embedding)

		# Store embedding on the correction log
		frappe.db.set_value(
			"Mapping Correction Log", correction_log_name,
			"raw_text_embedding", json.dumps(embedding_list),
			update_modified=False,
		)

		# Upsert into embedding index
		index_manager = get_index_manager()
		index_manager.upsert(
			source_doctype="Historical Invoice Line",
			source_name=corrected_item,
			embedding=embedding,
			metadata={
				"supplier_context": supplier,
				"is_human_corrected": 1,
				"item_group": item_group,
				"hsn_code": hsn_code,
				"composite_text": raw_text,
			},
		)

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Failed to update embedding index for correction {correction_log_name}: {e}")


def export_corrections(start_date, end_date):
	"""Export correction logs for analysis."""
	return frappe.get_all(
		"Mapping Correction Log",
		filters={
			"creation": ["between", [start_date, end_date]],
		},
		fields=[
			"name", "source_doctype", "raw_extracted_text",
			"system_proposed", "system_confidence", "system_match_stage",
			"human_selected", "reviewer", "reviewer_reasoning",
			"supplier", "extracted_hsn", "item_group_of_correction",
			"is_conflicting", "creation",
		],
		order_by="creation asc",
		limit=0,
	)
