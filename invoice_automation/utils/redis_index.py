import frappe

from invoice_automation.matching.normalizer import (
	extract_pan_from_gstin,
	is_valid_gstin,
	normalize_gstin,
	normalize_tax_id,
	normalize_text,
)


KEY_PREFIX = "invoice_automation"


def _get_redis():
	"""Return Frappe's Redis connection."""
	return frappe.cache()


def _make_key(doctype, normalized_value):
	return f"{KEY_PREFIX}:{doctype}:lookup:{normalized_value}"


def _set_lookup(doctype, normalized_value, canonical_name):
	if not normalized_value:
		return
	_get_redis().set_value(_make_key(doctype, normalized_value), canonical_name)


def _get_lookup(doctype, normalized_value):
	if not normalized_value:
		return None
	return _get_redis().get_value(_make_key(doctype, normalized_value))


def _delete_lookup(doctype, normalized_value):
	if not normalized_value:
		return
	_get_redis().delete_value(_make_key(doctype, normalized_value))


def rebuild_all():
	"""Clear all invoice_automation:* keys and rebuild supplier + item + alias indexes."""
	update_rebuild_status("redis_index_status", "Rebuilding")

	try:
		r = _get_redis()
		# Delete all existing keys with our prefix
		for key in r.get_keys(f"{KEY_PREFIX}:*"):
			r.delete_value(key)

		_build_supplier_index()
		_build_item_index()
		_build_alias_cache()

		# Count entries and stamp completion
		entry_count = len(list(r.get_keys(f"{KEY_PREFIX}:*")))
		update_rebuild_status(
			"redis_index_status", "Ready",
			last_rebuild_field="last_redis_rebuild",
			count_field="redis_index_count",
			count_value=entry_count,
		)
		frappe.logger().info(f"invoice_automation: Redis index rebuild complete ({entry_count} entries)")
	except Exception as e:
		update_rebuild_status("redis_index_status", "Failed")
		frappe.log_error(f"Redis index rebuild failed: {e}", "Invoice Redis Rebuild Error")


def _build_supplier_index():
	"""Index all active suppliers by name, tax ID, and (if applicable) GSTIN/PAN."""
	# Fetch tax_id (standard field). The gstin field only exists when
	# India-specific apps (e.g. India Compliance) are installed.
	fields = ["name", "supplier_name", "tax_id"]
	gstin_field_exists = _has_field("Supplier", "gstin")
	if gstin_field_exists:
		fields.append("gstin")

	suppliers = frappe.get_all(
		"Supplier",
		filters={"disabled": 0},
		fields=fields,
	)
	for sup in suppliers:
		_index_supplier(
			sup.name,
			sup.supplier_name,
			sup.tax_id,
			sup.get("gstin") if gstin_field_exists else None,
		)


def _has_field(doctype, fieldname):
	"""Check if a field exists on a doctype (cached)."""
	try:
		meta = frappe.get_meta(doctype)
		return meta.has_field(fieldname)
	except Exception:
		return False


def _index_supplier(name, supplier_name, tax_id, gstin_field=None):
	doctype = "Supplier"
	_set_lookup(doctype, normalize_text(supplier_name), name)
	if name != supplier_name:
		_set_lookup(doctype, normalize_text(name), name)

	# Collect all raw tax identifiers (tax_id is the generic field,
	# gstin is India-specific and may not exist on every install)
	raw_ids = list({v for v in [tax_id, gstin_field] if v})

	for raw_id in raw_ids:
		# Always index the generic normalized form so any tax ID format is searchable
		generic = normalize_tax_id(raw_id)
		if generic:
			_set_lookup(doctype, generic, name)

		# If it looks like an Indian GSTIN, also index the PAN component
		if is_valid_gstin(raw_id):
			gstin = normalize_gstin(raw_id)
			if gstin:
				pan = extract_pan_from_gstin(gstin)
				if pan:
					_set_lookup(doctype, pan, name)


def update_supplier_index(doc, method=None):
	_index_supplier(doc.name, doc.supplier_name, doc.tax_id, getattr(doc, "gstin", None))


def remove_supplier_index(doc, method=None):
	doctype = "Supplier"
	_delete_lookup(doctype, normalize_text(doc.supplier_name))
	if doc.name != doc.supplier_name:
		_delete_lookup(doctype, normalize_text(doc.name))
	for raw_id in [doc.tax_id, getattr(doc, "gstin", None)]:
		if not raw_id:
			continue
		generic = normalize_tax_id(raw_id)
		if generic:
			_delete_lookup(doctype, generic)
		if is_valid_gstin(raw_id):
			gstin = normalize_gstin(raw_id)
			if gstin:
				pan = extract_pan_from_gstin(gstin)
				if pan:
					_delete_lookup(doctype, pan)


def _build_alias_cache():
	"""Load all active Mapping Aliases into Redis for Stage 2 lookups."""
	try:
		aliases = frappe.get_all(
			"Mapping Alias",
			filters={"is_active": 1},
			fields=["composite_key", "canonical_name"],
			limit=0,
		)
	except Exception:
		return

	r = _get_redis()
	for alias in aliases:
		if alias.composite_key and alias.canonical_name:
			r.set_value(f"{KEY_PREFIX}:alias:{alias.composite_key}", alias.canonical_name)


def _build_item_index():
	"""Index all enabled items by code, name, barcodes, and MPN."""
	items = frappe.get_all(
		"Item",
		filters={"disabled": 0},
		fields=["name", "item_name", "default_manufacturer_part_no"],
	)

	# Batch-load all barcodes in one query instead of N+1 per-item queries
	item_names = [item.name for item in items]
	barcodes_by_item = {}
	if item_names:
		all_barcodes = frappe.get_all(
			"Item Barcode",
			filters={"parent": ["in", item_names]},
			fields=["parent", "barcode"],
		)
		for b in all_barcodes:
			if b.barcode:
				barcodes_by_item.setdefault(b.parent, []).append(b.barcode)

	for item in items:
		barcode_list = barcodes_by_item.get(item.name, [])
		_index_item(item.name, item.item_name, barcode_list, item.default_manufacturer_part_no)


def _index_item(name, item_name, barcodes=None, default_manufacturer_part_no=None):
	doctype = "Item"
	_set_lookup(doctype, normalize_text(name), name)
	if item_name and item_name != name:
		_set_lookup(doctype, normalize_text(item_name), name)
	for barcode in (barcodes or []):
		_set_lookup(doctype, normalize_text(barcode), name)
	if default_manufacturer_part_no:
		_set_lookup(doctype, normalize_text(default_manufacturer_part_no), name)


def update_item_index(doc, method=None):
	barcodes = [b.barcode for b in (doc.barcodes or []) if b.barcode]
	_index_item(doc.name, doc.item_name, barcodes, doc.default_manufacturer_part_no)


def remove_item_index(doc, method=None):
	doctype = "Item"
	_delete_lookup(doctype, normalize_text(doc.name))
	if doc.item_name and doc.item_name != doc.name:
		_delete_lookup(doctype, normalize_text(doc.item_name))
	for b in (doc.barcodes or []):
		if b.barcode:
			_delete_lookup(doctype, normalize_text(b.barcode))
	if doc.default_manufacturer_part_no:
		_delete_lookup(doctype, normalize_text(doc.default_manufacturer_part_no))


def update_rebuild_status(status_field, status_value, last_rebuild_field=None, count_field=None, count_value=None):
	"""Update rebuild status fields on Invoice Automation Settings."""
	try:
		updates = {status_field: status_value}
		if last_rebuild_field:
			updates[last_rebuild_field] = frappe.utils.now_datetime()
		if count_field and count_value is not None:
			updates[count_field] = count_value
		frappe.db.set_single_value("Invoice Automation Settings", updates, update_modified=False)
		frappe.db.commit()
	except Exception:
		pass  # Don't fail the rebuild if status update fails
