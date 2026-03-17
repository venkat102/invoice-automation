app_name = "invoice_automation"
app_title = "Invoice Automation"
app_publisher = "venkatsh@aerele.in"
app_description = "Invoice Automation"
app_email = "venkatsh@aerele.in"
app_license = "mit"

required_apps = ["frappe", "erpnext"]

after_install = "invoice_automation.utils.redis_index.rebuild_all"
after_migrate = "invoice_automation.utils.redis_index.rebuild_all"

# Document Events
doc_events = {
	"Supplier": {
		"on_update": "invoice_automation.utils.redis_index.update_supplier_index",
		"after_insert": "invoice_automation.utils.redis_index.update_supplier_index",
		"on_trash": "invoice_automation.utils.redis_index.remove_supplier_index",
	},
	"Item": {
		"on_update": [
			"invoice_automation.utils.redis_index.update_item_index",
			"invoice_automation.embeddings.index_builder.update_item_embedding",
		],
		"after_insert": [
			"invoice_automation.utils.redis_index.update_item_index",
			"invoice_automation.embeddings.index_builder.update_item_embedding",
		],
		"on_trash": [
			"invoice_automation.utils.redis_index.remove_item_index",
			"invoice_automation.embeddings.index_builder.remove_item_embedding",
		],
	},
}

# Scheduled Tasks
scheduler_events = {
	"daily": [
		"invoice_automation.utils.redis_index.rebuild_all",
		"invoice_automation.embeddings.index_builder.sync_missing",
	],
	"weekly": [
		"invoice_automation.memory.conflict_resolver.resolve_stale_conflicts",
	],
}
