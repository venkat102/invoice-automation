import frappe
from frappe.model.document import Document


class SupplierItemCatalog(Document):
	pass


def upsert_catalog_entry(supplier, item, rate=None, hsn_code=None, invoice_date=None):
	"""Create or update a supplier-item catalog entry with rate statistics."""
	if not supplier or not item:
		return

	item_group = frappe.db.get_value("Item", item, "item_group")

	existing = frappe.db.get_value(
		"Supplier Item Catalog",
		{"supplier": supplier, "item": item},
		["name", "avg_rate", "min_rate", "max_rate", "occurrence_count"],
		as_dict=True,
	)

	rate = float(rate) if rate else 0

	if existing:
		count = (existing.occurrence_count or 0) + 1
		updates = {
			"occurrence_count": count,
			"item_group": item_group,
		}

		if rate > 0:
			old_avg = float(existing.avg_rate or 0)
			old_count = existing.occurrence_count or 1
			updates["avg_rate"] = ((old_avg * old_count) + rate) / count
			updates["last_rate"] = rate
			updates["min_rate"] = min(float(existing.min_rate or rate), rate)
			updates["max_rate"] = max(float(existing.max_rate or 0), rate)

		if invoice_date:
			updates["last_invoice_date"] = invoice_date
		if hsn_code:
			updates["hsn_code"] = hsn_code

		frappe.db.set_value("Supplier Item Catalog", existing.name, updates, update_modified=True)
	else:
		doc = frappe.new_doc("Supplier Item Catalog")
		doc.supplier = supplier
		doc.item = item
		doc.item_group = item_group
		doc.occurrence_count = 1
		if rate > 0:
			doc.avg_rate = rate
			doc.last_rate = rate
			doc.min_rate = rate
			doc.max_rate = rate
		if invoice_date:
			doc.last_invoice_date = invoice_date
		if hsn_code:
			doc.hsn_code = hsn_code
		doc.insert(ignore_permissions=True)


def update_catalog_from_purchase_invoice(doc, method=None):
	"""Doc event handler: update catalog when a Purchase Invoice is submitted."""
	for item_row in doc.items:
		upsert_catalog_entry(
			supplier=doc.supplier,
			item=item_row.item_code,
			rate=item_row.rate,
			hsn_code=getattr(item_row, "gst_hsn_code", None),
			invoice_date=doc.posting_date,
		)
	frappe.db.commit()


def backfill_catalog():
	"""One-time job: populate catalog from all existing submitted Purchase Invoices."""
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={"docstatus": 1},
		fields=["name", "supplier", "posting_date"],
		order_by="posting_date asc",
	)

	for inv in invoices:
		items = frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": inv.name},
			fields=["item_code", "rate", "gst_hsn_code"],
		)
		for item_row in items:
			if item_row.item_code:
				upsert_catalog_entry(
					supplier=inv.supplier,
					item=item_row.item_code,
					rate=item_row.rate,
					hsn_code=item_row.get("gst_hsn_code"),
					invoice_date=inv.posting_date,
				)

	frappe.db.commit()
