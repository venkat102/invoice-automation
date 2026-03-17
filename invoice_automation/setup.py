"""Install and migrate hooks for Invoice Automation."""

import frappe


def after_install():
	"""Run on fresh app install: build all Redis indexes and enqueue embedding build."""
	from invoice_automation.utils.redis_index import rebuild_all

	rebuild_all()
	# Embedding build is slow (loads ML model, processes all Items) — run in background
	frappe.enqueue(
		"invoice_automation.embeddings.index_builder.build_full_index",
		queue="long",
		timeout=3600,
	)
	frappe.logger().info("invoice_automation: Enqueued embedding index build (background)")


def after_migrate():
	"""Run after bench migrate: rebuild Redis indexes (Suppliers, Items, Aliases)."""
	from invoice_automation.utils.redis_index import rebuild_all

	rebuild_all()
