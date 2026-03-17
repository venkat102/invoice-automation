import frappe

from invoice_automation.utils.helpers import get_config_value


def check_duplicate(supplier, bill_no, bill_date, grand_total):
	"""Check for duplicate invoices in existing Purchase Invoices.

	Returns:
		dict with is_duplicate, and if duplicate: duplicate_type, existing_invoice, block, details.
	"""
	if not supplier:
		return {"is_duplicate": False}

	# Exact duplicate: same supplier + bill_no + bill_date
	exact_filters = {"supplier": supplier, "bill_no": bill_no, "docstatus": ["!=", 2]}
	if bill_date:
		exact_filters["bill_date"] = bill_date

	exact_match = frappe.db.get_value("Purchase Invoice", filters=exact_filters, fieldname="name")

	if exact_match:
		return {
			"is_duplicate": True,
			"duplicate_type": "exact",
			"existing_invoice": exact_match,
			"block": True,
			"details": f"Exact duplicate of Purchase Invoice {exact_match} "
			           f"(same supplier, bill_no, bill_date)",
		}

	# Near duplicate: same supplier + amount within tolerance + date within range
	amount_tolerance_pct = float(get_config_value("duplicate_check_amount_tolerance_pct", 5))
	date_range_days = int(get_config_value("duplicate_check_date_range_days", 7))

	grand_total = float(grand_total or 0)
	if not grand_total or not bill_date:
		return {"is_duplicate": False}

	amount_lower = grand_total * (1 - amount_tolerance_pct / 100.0)
	amount_upper = grand_total * (1 + amount_tolerance_pct / 100.0)

	near_match = frappe.db.sql(
		"""
		SELECT name, bill_no, bill_date, grand_total
		FROM `tabPurchase Invoice`
		WHERE supplier = %(supplier)s
			AND docstatus != 2
			AND grand_total BETWEEN %(amount_lower)s AND %(amount_upper)s
			AND bill_date BETWEEN DATE_SUB(%(bill_date)s, INTERVAL %(days)s DAY)
			                   AND DATE_ADD(%(bill_date)s, INTERVAL %(days)s DAY)
		LIMIT 1
		""",
		{
			"supplier": supplier,
			"amount_lower": amount_lower,
			"amount_upper": amount_upper,
			"bill_date": bill_date,
			"days": date_range_days,
		},
		as_dict=True,
	)

	if near_match:
		match = near_match[0]
		return {
			"is_duplicate": True,
			"duplicate_type": "near",
			"existing_invoice": match.name,
			"block": False,
			"details": (
				f"Near duplicate of Purchase Invoice {match.name} "
				f"(bill_no={match.bill_no}, bill_date={match.bill_date}, "
				f"grand_total={match.grand_total})"
			),
		}

	return {"is_duplicate": False}
