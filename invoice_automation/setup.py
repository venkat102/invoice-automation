"""Install and migrate hooks for Invoice Automation."""


def after_install():
	"""Run on fresh app install: build all Redis indexes and enqueue embedding build."""
	from invoice_automation.utils.redis_index import rebuild_all

	rebuild_all()
	seed_matching_strategies()
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
	seed_matching_strategies()


def seed_matching_strategies():
	"""Seed default matching strategies if they don't exist."""
	import frappe

	default_strategies = [
		{
			"strategy_name": "Exact",
			"strategy_class": "invoice_automation.matching.exact_matcher.ExactMatcherStrategy",
			"enabled": 1,
			"priority": 10,
			"applies_to": "Both",
			"max_confidence": 100,
		},
		{
			"strategy_name": "Vendor SKU",
			"strategy_class": "invoice_automation.matching.vendor_sku_matcher.VendorSKUMatcher",
			"enabled": 1,
			"priority": 15,
			"applies_to": "Item",
			"max_confidence": 97,
		},
		{
			"strategy_name": "Alias",
			"strategy_class": "invoice_automation.matching.alias_matcher.AliasMatcherStrategy",
			"enabled": 1,
			"priority": 20,
			"applies_to": "Both",
			"max_confidence": 99,
		},
		{
			"strategy_name": "Purchase History",
			"strategy_class": "invoice_automation.matching.purchase_history_matcher.PurchaseHistoryMatcher",
			"enabled": 0,
			"priority": 25,
			"applies_to": "Item",
			"max_confidence": 85,
		},
		{
			"strategy_name": "Fuzzy",
			"strategy_class": "invoice_automation.matching.fuzzy_matcher.FuzzyMatcherStrategy",
			"enabled": 1,
			"priority": 30,
			"applies_to": "Both",
			"max_confidence": 89,
		},
		{
			"strategy_name": "HSN Filter",
			"strategy_class": "invoice_automation.matching.hsn_filter.HSNFilteredMatcher",
			"enabled": 0,
			"priority": 35,
			"applies_to": "Item",
			"max_confidence": 89,
		},
		{
			"strategy_name": "Embedding",
			"strategy_class": "invoice_automation.matching.embedding_matcher.EmbeddingMatcherStrategy",
			"enabled": 1,
			"priority": 40,
			"applies_to": "Both",
			"max_confidence": 92,
		},
		{
			"strategy_name": "LLM",
			"strategy_class": "invoice_automation.matching.llm_matcher.LLMMatcherStrategy",
			"enabled": 1,
			"priority": 50,
			"applies_to": "Both",
			"max_confidence": 88,
		},
	]

	for strategy in default_strategies:
		if not frappe.db.exists("Matching Strategy", strategy["strategy_name"]):
			doc = frappe.new_doc("Matching Strategy")
			doc.update(strategy)
			doc.insert(ignore_permissions=True)

	frappe.db.commit()
