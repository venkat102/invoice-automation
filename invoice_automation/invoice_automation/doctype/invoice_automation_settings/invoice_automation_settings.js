frappe.ui.form.on("Invoice Automation Settings", {
	rebuild_redis_index: function () {
		frappe.call({
			method: "invoice_automation.api.endpoints.rebuild_index",
			args: { index_type: "redis" },
			callback: function () {
				frappe.msgprint(__("Redis index rebuild has been triggered."));
			},
		});
	},

	rebuild_embedding_index: function () {
		frappe.call({
			method: "invoice_automation.api.endpoints.rebuild_index",
			args: { index_type: "embeddings" },
			callback: function () {
				frappe.msgprint(__("Embedding index rebuild has been triggered."));
			},
		});
	},

	rebuild_all_indexes: function () {
		frappe.call({
			method: "invoice_automation.api.endpoints.rebuild_index",
			args: { index_type: "all" },
			callback: function () {
				frappe.msgprint(__("All indexes rebuild has been triggered."));
			},
		});
	},
});
