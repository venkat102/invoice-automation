import frappe
from frappe.model.document import Document


class VendorSKUMapping(Document):
	pass


def upsert_sku_mapping(supplier, vendor_item_code, item, rate=None):
	"""Create or update a vendor SKU to Item mapping."""
	if not supplier or not vendor_item_code or not item:
		return

	existing = frappe.db.get_value(
		"Vendor SKU Mapping",
		{"supplier": supplier, "vendor_item_code": vendor_item_code},
		["name", "occurrence_count"],
		as_dict=True,
	)

	if existing:
		updates = {
			"item": item,
			"occurrence_count": (existing.occurrence_count or 0) + 1,
		}
		if rate:
			updates["last_seen_rate"] = float(rate)
		frappe.db.set_value("Vendor SKU Mapping", existing.name, updates, update_modified=True)
	else:
		doc = frappe.new_doc("Vendor SKU Mapping")
		doc.supplier = supplier
		doc.vendor_item_code = vendor_item_code
		doc.item = item
		doc.occurrence_count = 1
		if rate:
			doc.last_seen_rate = float(rate)
		doc.insert(ignore_permissions=True)
