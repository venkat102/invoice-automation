"""Handles contradictory corrections in the mapping memory system."""

import frappe

from invoice_automation.matching.normalizer import normalize_text


def check_for_conflicts(supplier, normalized_text, source_doctype, new_selection):
	"""Check if a new correction contradicts an existing one.

	Returns conflict info dict or None.
	"""
	if not normalized_text or not new_selection:
		return None

	# Find existing corrections for same supplier + normalized_text + doctype
	# but different human_selected
	filters = {
		"source_doctype": source_doctype,
		"human_selected": ["!=", new_selection],
	}
	if supplier:
		filters["supplier"] = supplier

	existing = frappe.get_all(
		"Mapping Correction Log",
		filters=filters,
		fields=["name", "human_selected", "raw_extracted_text", "creation"],
		order_by="creation desc",
		limit=10,
	)

	# Filter to those with matching normalized text
	for correction in existing:
		if normalize_text(correction.raw_extracted_text) == normalized_text:
			# Check if alias has high correction_count (authoritative)
			supplier_key = supplier or "ANY"
			composite_key = f"{supplier_key}:{normalized_text}:{source_doctype}"
			alias_count = frappe.db.get_value(
				"Mapping Alias",
				{"composite_key": composite_key},
				"correction_count",
			) or 0

			if alias_count > 1:
				# New correction is authoritative (has been confirmed multiple times)
				return None

			# Flag as conflicting
			frappe.db.set_value(
				"Mapping Correction Log", correction.name,
				"is_conflicting", 1,
				update_modified=False,
			)

			return {
				"conflicting_log": correction.name,
				"previous_selection": correction.human_selected,
				"new_selection": new_selection,
			}

	return None


def resolve_stale_conflicts():
	"""Weekly scheduled job: auto-resolve old conflicts by frequency.

	Picks the most frequent correction (highest correction_count on the alias).
	"""
	stale_conflicts = frappe.get_all(
		"Mapping Correction Log",
		filters={
			"is_conflicting": 1,
			"creation": ["<", frappe.utils.add_days(frappe.utils.nowdate(), -30)],
		},
		fields=["name", "source_doctype", "raw_extracted_text", "supplier", "human_selected"],
		limit=100,
	)

	resolved = 0
	for conflict in stale_conflicts:
		normalized = normalize_text(conflict.raw_extracted_text)
		supplier_key = conflict.supplier or "ANY"
		composite_key = f"{supplier_key}:{normalized}:{conflict.source_doctype}"

		# Get the current active alias
		alias = frappe.db.get_value(
			"Mapping Alias",
			{"composite_key": composite_key, "is_active": 1},
			["canonical_name", "correction_count"],
			as_dict=True,
		)

		if alias and alias.correction_count and alias.correction_count > 1:
			# The alias has been confirmed multiple times, resolve in its favor
			frappe.db.set_value(
				"Mapping Correction Log", conflict.name,
				"is_conflicting", 0,
				update_modified=False,
			)
			resolved += 1

	if resolved:
		frappe.db.commit()
		frappe.logger().info(f"invoice_automation: Resolved {resolved} stale conflicts")
