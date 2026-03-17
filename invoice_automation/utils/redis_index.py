import frappe

from invoice_automation.matching.normalizer import normalize_gstin, normalize_text, extract_pan_from_gstin


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
	"""Clear all invoice_automation:* keys and rebuild supplier + item indexes."""
	r = _get_redis()
	# Delete all existing keys with our prefix
	for key in r.get_keys(f"{KEY_PREFIX}:*"):
		r.delete_value(key)

	_build_supplier_index()
	_build_item_index()
	frappe.logger().info("invoice_automation: Redis index rebuild complete")


def _build_supplier_index():
	"""Index all active suppliers by name, GSTIN, and PAN."""
	suppliers = frappe.get_all(
		"Supplier",
		filters={"disabled": 0},
		fields=["name", "supplier_name", "tax_id", "gstin"],
	)
	for sup in suppliers:
		_index_supplier(sup.name, sup.supplier_name, sup.tax_id, sup.gstin)


def _index_supplier(name, supplier_name, tax_id, gstin_field=None):
	doctype = "Supplier"
	_set_lookup(doctype, normalize_text(supplier_name), name)
	if name != supplier_name:
		_set_lookup(doctype, normalize_text(name), name)

	# Index both tax_id and gstin fields
	for raw_gstin in [tax_id, gstin_field]:
		if raw_gstin:
			gstin = normalize_gstin(raw_gstin)
			if gstin:
				_set_lookup(doctype, gstin, name)
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
	for raw_gstin in [doc.tax_id, getattr(doc, "gstin", None)]:
		if not raw_gstin:
			continue
		gstin = normalize_gstin(raw_gstin)
		if gstin:
			_delete_lookup(doctype, gstin)
			pan = extract_pan_from_gstin(gstin)
			if pan:
				_delete_lookup(doctype, pan)


def _build_item_index():
	"""Index all enabled items by code, name, barcodes, and MPN."""
	items = frappe.get_all(
		"Item",
		filters={"disabled": 0},
		fields=["name", "item_name", "default_manufacturer_part_no"],
	)
	for item in items:
		barcodes = frappe.get_all(
			"Item Barcode",
			filters={"parent": item.name},
			fields=["barcode"],
		)
		barcode_list = [b.barcode for b in barcodes if b.barcode]
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
