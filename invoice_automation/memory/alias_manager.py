"""CRUD for Mapping Alias with Redis sync."""

import frappe

from invoice_automation.matching.normalizer import normalize_text


class AliasManager:
	"""Manages the Mapping Alias doctype with Redis cache synchronization."""

	def upsert_alias(self, raw_text, canonical_name, source_doctype, supplier=None, from_correction=False):
		"""Create or update a mapping alias.

		Builds composite key: {supplier or "ANY"}:{normalized_text}:{source_doctype}
		"""
		normalized = normalize_text(raw_text)
		if not normalized:
			return

		supplier_key = supplier or "ANY"
		composite_key = f"{supplier_key}:{normalized}:{source_doctype}"

		existing = frappe.db.get_value(
			"Mapping Alias",
			{"composite_key": composite_key},
			["name", "correction_count", "canonical_name"],
			as_dict=True,
		)

		if existing:
			updates = {
				"canonical_name": canonical_name,
				"correction_count": (existing.correction_count or 0) + 1,
				"last_used": frappe.utils.now_datetime(),
			}
			if from_correction:
				updates["created_from_correction"] = 1
				updates["last_correction_date"] = frappe.utils.now_datetime()
				updates["decay_weight"] = 1.0

			# If canonical_name changed, mark old one as superseded
			if existing.canonical_name != canonical_name:
				updates["correction_count"] = 1  # Reset count for new mapping

			frappe.db.set_value("Mapping Alias", existing.name, updates, update_modified=True)
			alias_name = existing.name
		else:
			alias_doc = frappe.new_doc("Mapping Alias")
			alias_doc.source_doctype = source_doctype
			alias_doc.raw_text = raw_text
			alias_doc.normalized_text = normalized
			alias_doc.canonical_name = canonical_name
			alias_doc.supplier_context = supplier
			alias_doc.composite_key = composite_key
			alias_doc.created_from_correction = 1 if from_correction else 0
			alias_doc.correction_count = 1
			alias_doc.last_used = frappe.utils.now_datetime()
			alias_doc.is_active = 1
			alias_doc.decay_weight = 1.0
			if from_correction:
				alias_doc.last_correction_date = frappe.utils.now_datetime()
			alias_doc.insert(ignore_permissions=True)
			alias_name = alias_doc.name

		# Sync to Redis immediately
		self._sync_to_redis(composite_key, canonical_name)

		return alias_name

	def lookup_alias(self, raw_text, source_doctype, supplier=None):
		"""Look up alias. Try supplier-specific first, then ANY."""
		normalized = normalize_text(raw_text)
		if not normalized:
			return None

		# Supplier-specific
		if supplier:
			key = f"{supplier}:{normalized}:{source_doctype}"
			result = self._redis_lookup(key)
			if result:
				return result

		# Supplier-agnostic
		key = f"ANY:{normalized}:{source_doctype}"
		return self._redis_lookup(key)

	def deactivate_alias(self, alias_name):
		"""Deactivate an alias without deletion."""
		frappe.db.set_value("Mapping Alias", alias_name, "is_active", 0)
		# Remove from Redis
		alias = frappe.get_doc("Mapping Alias", alias_name)
		if alias.composite_key:
			redis_key = f"invoice_automation:alias:{alias.composite_key}"
			try:
				frappe.cache().delete_value(redis_key)
			except Exception:
				pass

	def _sync_to_redis(self, composite_key, canonical_name):
		"""Push alias to Redis cache."""
		redis_key = f"invoice_automation:alias:{composite_key}"
		try:
			frappe.cache().set_value(redis_key, canonical_name)
		except Exception:
			pass

	def _redis_lookup(self, composite_key):
		"""Look up from Redis, fallback to DB."""
		redis_key = f"invoice_automation:alias:{composite_key}"
		try:
			result = frappe.cache().get_value(redis_key)
			if result:
				return result
		except Exception:
			pass

		# Fallback to DB
		canonical = frappe.db.get_value(
			"Mapping Alias",
			{"composite_key": composite_key, "is_active": 1},
			"canonical_name",
		)
		if canonical:
			self._sync_to_redis(composite_key, canonical)
		return canonical


def apply_decay_weights():
	"""Daily scheduled job: decay alias weights based on time since last correction.

	decay_weight = max(0.5, 1.0 - 0.005 * days_since_last_correction)
	Aliases unused for 100+ days decay to minimum 0.5 weight.
	"""
	from frappe.utils import now_datetime, date_diff

	aliases = frappe.get_all(
		"Mapping Alias",
		filters={"is_active": 1, "last_correction_date": ["is", "set"]},
		fields=["name", "last_correction_date"],
	)

	now = now_datetime()
	for alias in aliases:
		days = date_diff(now, alias.last_correction_date)
		weight = max(0.5, 1.0 - 0.005 * days)
		frappe.db.set_value(
			"Mapping Alias", alias.name, "decay_weight", weight, update_modified=False
		)

	frappe.db.commit()
