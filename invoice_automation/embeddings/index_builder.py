"""Bench commands for building and rebuilding embedding indexes."""

import json

import frappe


def build_full_index():
	"""Build both item master and historical invoice embeddings."""
	rebuild_item_embeddings()
	_build_historical_embeddings()
	frappe.logger().info("invoice_automation: Full embedding index build complete")


def rebuild_item_embeddings():
	"""Rebuild only item embeddings. Deletes existing Item entries first."""
	from invoice_automation.embeddings.model import generate_embeddings_batch, embedding_to_list

	# Delete existing Item-type entries
	frappe.db.delete("Embedding Index", {"source_doctype": "Item"})
	frappe.db.commit()

	# Get all items
	items = frappe.get_all(
		"Item",
		filters={"disabled": 0},
		fields=["name", "item_name", "description", "brand", "default_manufacturer_part_no", "item_group"],
	)

	if not items:
		return

	# Get HSN codes
	hsn_map = {}
	hsn_records = frappe.get_all(
		"Item",
		filters={"disabled": 0, "gst_hsn_code": ["is", "set"]},
		fields=["name", "gst_hsn_code"],
	)
	for rec in hsn_records:
		hsn_map[rec.name] = rec.gst_hsn_code

	# Build composite texts
	texts = []
	valid_items = []
	for item in items:
		parts = [item.item_name or item.name]
		if item.description:
			parts.append(item.description)
		if item.brand:
			parts.append(item.brand)
		if item.default_manufacturer_part_no:
			parts.append(item.default_manufacturer_part_no)
		hsn = hsn_map.get(item.name)
		if hsn:
			parts.append(f"HSN {hsn}")

		composite_text = " | ".join(parts)
		texts.append(composite_text)
		valid_items.append((item, composite_text, hsn))

	# Generate embeddings in batch
	batch_size = 256
	for start in range(0, len(texts), batch_size):
		batch_texts = texts[start:start + batch_size]
		batch_items = valid_items[start:start + batch_size]

		embeddings = generate_embeddings_batch(batch_texts)

		for i, (item, composite_text, hsn) in enumerate(batch_items):
			embedding_list = embedding_to_list(embeddings[i])

			doc = frappe.new_doc("Embedding Index")
			doc.source_doctype = "Item"
			doc.source_name = item.name
			doc.composite_text = composite_text
			doc.embedding_vector = json.dumps(embedding_list)
			doc.item_group = item.item_group
			doc.hsn_code = hsn
			doc.is_human_corrected = 0
			doc.last_updated = frappe.utils.now_datetime()
			doc.insert(ignore_permissions=True)

		frappe.db.commit()
		frappe.publish_progress(
			min(start + batch_size, len(texts)) * 100 / len(texts),
			title="Building Item Embeddings",
			description=f"Processed {min(start + batch_size, len(texts))} of {len(texts)} items",
		)

	frappe.logger().info(f"invoice_automation: Built embeddings for {len(valid_items)} items")


def _build_historical_embeddings():
	"""Build embeddings for historical correction logs that don't have them yet."""
	from invoice_automation.embeddings.model import generate_embedding, embedding_to_list

	corrections = frappe.get_all(
		"Mapping Correction Log",
		filters={
			"source_doctype": "Item",
			"raw_text_embedding": ["is", "not set"],
		},
		fields=["name", "raw_extracted_text", "human_selected", "supplier",
		        "extracted_hsn", "item_group_of_correction"],
		limit=0,
	)

	for correction in corrections:
		if not correction.raw_extracted_text:
			continue

		try:
			embedding = generate_embedding(correction.raw_extracted_text)
			embedding_list = embedding_to_list(embedding)

			# Store on the correction log
			frappe.db.set_value(
				"Mapping Correction Log", correction.name,
				"raw_text_embedding", json.dumps(embedding_list),
				update_modified=False,
			)

			# Add to embedding index
			existing = frappe.db.get_value(
				"Embedding Index",
				{
					"source_doctype": "Historical Invoice Line",
					"source_name": correction.human_selected,
					"supplier_context": correction.supplier,
				},
				"name",
			)

			if not existing:
				doc = frappe.new_doc("Embedding Index")
				doc.source_doctype = "Historical Invoice Line"
				doc.source_name = correction.human_selected
				doc.composite_text = correction.raw_extracted_text
				doc.embedding_vector = json.dumps(embedding_list)
				doc.supplier_context = correction.supplier
				doc.is_human_corrected = 1
				doc.item_group = correction.item_group_of_correction
				doc.hsn_code = correction.extracted_hsn
				doc.last_updated = frappe.utils.now_datetime()
				doc.insert(ignore_permissions=True)

		except Exception as e:
			frappe.log_error(f"Failed to build embedding for correction {correction.name}: {e}")

	frappe.db.commit()


def sync_missing():
	"""Daily scheduled job: add Items missing from the embedding index."""
	from invoice_automation.embeddings.model import generate_embedding, embedding_to_list

	# Find items not in embedding index
	indexed_items = set(
		frappe.get_all(
			"Embedding Index",
			filters={"source_doctype": "Item"},
			pluck="source_name",
			limit=0,
		)
	)

	all_items = frappe.get_all(
		"Item",
		filters={"disabled": 0},
		fields=["name", "item_name", "description", "brand", "default_manufacturer_part_no", "item_group"],
	)

	missing = [item for item in all_items if item.name not in indexed_items]

	if not missing:
		return

	# Get HSN codes
	hsn_map = {}
	hsn_records = frappe.get_all(
		"Item",
		filters={"disabled": 0, "gst_hsn_code": ["is", "set"]},
		fields=["name", "gst_hsn_code"],
	)
	for rec in hsn_records:
		hsn_map[rec.name] = rec.gst_hsn_code

	for item in missing:
		try:
			parts = [item.item_name or item.name]
			if item.description:
				parts.append(item.description)
			if item.brand:
				parts.append(item.brand)
			if item.default_manufacturer_part_no:
				parts.append(item.default_manufacturer_part_no)
			hsn = hsn_map.get(item.name)
			if hsn:
				parts.append(f"HSN {hsn}")

			composite_text = " | ".join(parts)
			embedding = generate_embedding(composite_text)
			embedding_list = embedding_to_list(embedding)

			doc = frappe.new_doc("Embedding Index")
			doc.source_doctype = "Item"
			doc.source_name = item.name
			doc.composite_text = composite_text
			doc.embedding_vector = json.dumps(embedding_list)
			doc.item_group = item.item_group
			doc.hsn_code = hsn
			doc.is_human_corrected = 0
			doc.last_updated = frappe.utils.now_datetime()
			doc.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Failed to sync embedding for {item.name}: {e}")

	frappe.db.commit()
	frappe.logger().info(f"invoice_automation: Synced {len(missing)} missing item embeddings")


def update_item_embedding(doc, method=None):
	"""Doc event handler: update embedding for a single item on save."""
	from invoice_automation.utils.helpers import enqueue_if_scheduler_active
	enqueue_if_scheduler_active(
		"invoice_automation.embeddings.index_builder._update_single_item",
		item_name=doc.name,
		queue="default",
		timeout=60,
	)


def _update_single_item(item_name):
	"""Background: generate and upsert embedding for one item."""
	from invoice_automation.embeddings.model import generate_embedding, embedding_to_list

	item = frappe.get_doc("Item", item_name)

	parts = [item.item_name or item.name]
	if item.description:
		parts.append(item.description)
	if item.brand:
		parts.append(item.brand)
	if item.default_manufacturer_part_no:
		parts.append(item.default_manufacturer_part_no)
	hsn = getattr(item, "gst_hsn_code", None)
	if hsn:
		parts.append(f"HSN {hsn}")

	composite_text = " | ".join(parts)

	try:
		embedding = generate_embedding(composite_text)
		embedding_list = embedding_to_list(embedding)

		existing = frappe.db.get_value(
			"Embedding Index",
			{"source_doctype": "Item", "source_name": item_name},
			"name",
		)

		if existing:
			frappe.db.set_value("Embedding Index", existing, {
				"composite_text": composite_text,
				"embedding_vector": json.dumps(embedding_list),
				"item_group": item.item_group,
				"hsn_code": hsn,
				"last_updated": frappe.utils.now_datetime(),
			})
		else:
			doc = frappe.new_doc("Embedding Index")
			doc.source_doctype = "Item"
			doc.source_name = item_name
			doc.composite_text = composite_text
			doc.embedding_vector = json.dumps(embedding_list)
			doc.item_group = item.item_group
			doc.hsn_code = hsn
			doc.is_human_corrected = 0
			doc.last_updated = frappe.utils.now_datetime()
			doc.insert(ignore_permissions=True)

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Failed to update embedding for item {item_name}: {e}")


def remove_item_embedding(doc, method=None):
	"""Doc event handler: remove embedding for an item on trash."""
	existing = frappe.db.get_value(
		"Embedding Index",
		{"source_doctype": "Item", "source_name": doc.name},
		"name",
	)
	if existing:
		frappe.delete_doc("Embedding Index", existing, ignore_permissions=True)
