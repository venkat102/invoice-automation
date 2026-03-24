app_name = "invoice_automation"
app_title = "Invoice Automation"
app_publisher = "venkatsh@aerele.in"
app_description = "Invoice Automation"
app_email = "venkatsh@aerele.in"
app_license = "mit"

required_apps = ["frappe", "erpnext"]

app_include_css = "/assets/invoice_automation/css/invoice_review.css"

after_install = "invoice_automation.setup.after_install"
after_migrate = "invoice_automation.setup.after_migrate"

# Document Events
doc_events = {
	"Purchase Invoice": {
		"on_submit": [
			"invoice_automation.invoice_automation.doctype.supplier_item_catalog.supplier_item_catalog.update_catalog_from_purchase_invoice",
		],
	},
	"Supplier": {
		"on_update": [
			"invoice_automation.utils.redis_index.update_supplier_index",
			"invoice_automation.matching.fuzzy_matcher.clear_master_cache",
		],
		"after_insert": [
			"invoice_automation.utils.redis_index.update_supplier_index",
			"invoice_automation.matching.fuzzy_matcher.clear_master_cache",
		],
		"on_trash": [
			"invoice_automation.utils.redis_index.remove_supplier_index",
			"invoice_automation.matching.fuzzy_matcher.clear_master_cache",
		],
	},
	"Item": {
		"on_update": [
			"invoice_automation.utils.redis_index.update_item_index",
			"invoice_automation.embeddings.index_builder.update_item_embedding",
			"invoice_automation.matching.fuzzy_matcher.clear_master_cache",
		],
		"after_insert": [
			"invoice_automation.utils.redis_index.update_item_index",
			"invoice_automation.embeddings.index_builder.update_item_embedding",
			"invoice_automation.matching.fuzzy_matcher.clear_master_cache",
		],
		"on_trash": [
			"invoice_automation.utils.redis_index.remove_item_index",
			"invoice_automation.embeddings.index_builder.remove_item_embedding",
			"invoice_automation.matching.fuzzy_matcher.clear_master_cache",
		],
	},
}

# Scheduled Tasks
scheduler_events = {
	"daily": [
		"invoice_automation.utils.redis_index.rebuild_all",
		"invoice_automation.embeddings.index_builder.sync_missing",
		"invoice_automation.memory.alias_manager.apply_decay_weights",
	],
	"weekly": [
		"invoice_automation.memory.conflict_resolver.resolve_stale_conflicts",
	],
}
