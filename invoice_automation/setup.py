"""Install and migrate hooks for Invoice Automation."""


def after_install():
	"""Run on fresh app install: build all Redis indexes and enqueue embedding build."""
	from invoice_automation.utils.redis_index import rebuild_all

	rebuild_all()
	# Embedding build is slow (loads ML model, processes all Items) — run in background
	from invoice_automation.utils.helpers import enqueue_if_scheduler_active
	enqueue_if_scheduler_active(
		"invoice_automation.embeddings.index_builder.build_full_index",
		queue="long",
		timeout=3600,
	)


def after_migrate():
	"""Run after bench migrate: rebuild Redis indexes (Suppliers, Items, Aliases)."""
	from invoice_automation.utils.redis_index import rebuild_all

	rebuild_all()
