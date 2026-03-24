frappe.ui.form.on("Invoice Automation Settings", {
	refresh: function (frm) {
		// Auto-refresh while rebuilding
		if (frm.doc.redis_index_status === "Rebuilding" || frm.doc.embedding_index_status === "Rebuilding") {
			setTimeout(function () {
				frm.reload_doc();
			}, 5000);
			frm.dashboard.set_headline(
				__("Index rebuild in progress... refreshing automatically.")
			);
		}
	},

	rebuild_redis_index: function (frm) {
		frappe.call({
			method: "invoice_automation.api.endpoints.rebuild_index",
			args: { index_type: "redis" },
			freeze: true,
			freeze_message: __("Triggering Redis index rebuild..."),
			callback: function () {
				frappe.show_alert({ message: __("Redis index rebuild started"), indicator: "blue" });
				frm.reload_doc();
			},
		});
	},

	rebuild_embedding_index: function (frm) {
		frappe.call({
			method: "invoice_automation.api.endpoints.rebuild_index",
			args: { index_type: "embeddings" },
			freeze: true,
			freeze_message: __("Triggering embedding index rebuild..."),
			callback: function () {
				frappe.show_alert({ message: __("Embedding index rebuild started"), indicator: "blue" });
				frm.reload_doc();
			},
		});
	},

	rebuild_all_indexes: function (frm) {
		frappe.call({
			method: "invoice_automation.api.endpoints.rebuild_index",
			args: { index_type: "all" },
			freeze: true,
			freeze_message: __("Triggering full index rebuild..."),
			callback: function () {
				frappe.show_alert({ message: __("Full index rebuild started"), indicator: "blue" });
				frm.reload_doc();
			},
		});
	},
});
