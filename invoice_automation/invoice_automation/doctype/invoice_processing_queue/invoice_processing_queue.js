frappe.ui.form.on("Invoice Processing Queue", {
	refresh: function (frm) {
		if (frm.doc.source_file) {
			frm.set_df_property("source_file", "description", frm.doc.file_name || "");
		}

		// Retry extraction
		if (frm.doc.extraction_status === "Failed" && frm.doc.source_file) {
			frm.add_custom_button(__("Retry Extraction"), function () {
				frappe.call({
					method: "invoice_automation.api.endpoints.parse_invoice",
					args: { file_url: frm.doc.source_file },
					freeze: true,
					freeze_message: __("Re-queuing extraction..."),
					callback: function (r) {
						if (r.message) {
							frappe.msgprint(
								__("New queue record created: {0}", [r.message.queue_name])
							);
							frappe.set_route("Form", "Invoice Processing Queue", r.message.queue_name);
						}
					},
				});
			}, __("Actions"));
		}

		// Trigger matching
		if (
			frm.doc.extraction_status === "Completed" &&
			["Pending", "Failed"].includes(frm.doc.matching_status)
		) {
			frm.add_custom_button(__("Trigger Matching"), function () {
				frappe.call({
					method: "invoice_automation.api.endpoints.trigger_matching",
					args: { queue_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Triggering matching..."),
					callback: function () {
						frm.reload_doc();
						frappe.show_alert({ message: __("Matching queued"), indicator: "blue" });
					},
				});
			}, __("Actions"));
		}

		// Review & Create Purchase Invoice
		if (
			frm.doc.extraction_status === "Completed" &&
			!frm.doc.purchase_invoice &&
			frm.doc.workflow_state !== "Rejected"
		) {
			frm.add_custom_button(__("Review & Create Invoice"), function () {
				show_review_dialog(frm);
			}).addClass("btn-primary");
		}

		// Reject
		if (
			["Routed", "Under Review", "Matched", "Extracted"].includes(frm.doc.workflow_state) &&
			!frm.doc.purchase_invoice
		) {
			frm.add_custom_button(__("Reject"), function () {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					function (values) {
						frappe.call({
							method: "invoice_automation.api.endpoints.reject_invoice",
							args: { queue_name: frm.doc.name, reason: values.reason },
							callback: function () {
								frm.reload_doc();
								frappe.show_alert({ message: __("Invoice rejected"), indicator: "red" });
							},
						});
					},
					__("Reject Invoice")
				);
			}, __("Actions"));
		}

		// View linked Purchase Invoice
		if (frm.doc.purchase_invoice) {
			frm.add_custom_button(__("View Purchase Invoice"), function () {
				frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice);
			});
		}
	},
});


function show_review_dialog(frm) {
	frappe.call({
		method: "invoice_automation.api.endpoints.get_review_data",
		args: { queue_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading review data..."),
		callback: function (r) {
			if (!r.message) {
				frappe.msgprint(__("Could not load review data"));
				return;
			}
			render_review_dialog(frm, r.message);
		},
	});
}


function confidence_indicator(confidence) {
	if (confidence >= 90) return '<span style="color: var(--green-500);">' + confidence.toFixed(0) + "%</span>";
	if (confidence >= 60) return '<span style="color: var(--orange-500);">' + confidence.toFixed(0) + "%</span>";
	if (confidence > 0) return '<span style="color: var(--red-500);">' + confidence.toFixed(0) + "%</span>";
	return '<span style="color: var(--text-muted);">-</span>';
}


function render_review_dialog(frm, data) {
	var h = data.header;

	// Build header review HTML
	var header_html = `
		<div style="margin-bottom: 16px;">
			<h5 style="margin-bottom: 8px;">Overall Confidence: ${confidence_indicator(data.overall_confidence)}
			${data.routing_decision ? ' &mdash; <span class="text-muted">' + data.routing_decision + '</span>' : ''}
			</h5>
		</div>
		<table class="table table-bordered" style="font-size: 13px;">
			<thead><tr>
				<th style="width:25%;">Field</th>
				<th style="width:35%;">Extracted</th>
				<th style="width:30%;">Matched</th>
				<th style="width:10%;">Confidence</th>
			</tr></thead>
			<tbody>
				<tr>
					<td><strong>Supplier</strong></td>
					<td>${frappe.utils.escape_html(h.supplier.extracted || "-")}
						${h.supplier.extracted_tax_id ? '<br><small class="text-muted">' + frappe.utils.escape_html(h.supplier.extracted_tax_id) + '</small>' : ''}
					</td>
					<td>${h.supplier.matched ? frappe.utils.escape_html(h.supplier.matched) : '<span class="text-muted">Not matched</span>'}
						${h.supplier.stage ? '<br><small class="text-muted">Stage: ' + h.supplier.stage + '</small>' : ''}
					</td>
					<td>${confidence_indicator(h.supplier.confidence)}</td>
				</tr>
				<tr>
					<td><strong>Invoice No.</strong></td>
					<td>${frappe.utils.escape_html(h.invoice_number.extracted || "-")}</td>
					<td>${frappe.utils.escape_html(h.invoice_number.matched || h.invoice_number.extracted || "-")}</td>
					<td>-</td>
				</tr>
				<tr>
					<td><strong>Invoice Date</strong></td>
					<td>${frappe.utils.escape_html(h.invoice_date.extracted || "-")}</td>
					<td>${frappe.utils.escape_html(h.invoice_date.matched || h.invoice_date.extracted || "-")}</td>
					<td>-</td>
				</tr>
				<tr>
					<td><strong>Due Date</strong></td>
					<td>${frappe.utils.escape_html(h.due_date.extracted || "-")}</td>
					<td>${frappe.utils.escape_html(h.due_date.matched || h.due_date.extracted || "-")}</td>
					<td>-</td>
				</tr>
				<tr>
					<td><strong>Currency</strong></td>
					<td>${frappe.utils.escape_html(h.currency.extracted || "-")}</td>
					<td>${frappe.utils.escape_html(h.currency.matched || h.currency.extracted || "-")}</td>
					<td>-</td>
				</tr>
				<tr>
					<td><strong>Total Amount</strong></td>
					<td>${frappe.utils.escape_html(String(h.total_amount.extracted || "-"))}</td>
					<td>${h.total_amount.matched || h.total_amount.extracted || "-"}</td>
					<td>-</td>
				</tr>
				${h.tax_template.matched ? '<tr><td><strong>Tax Template</strong></td><td>-</td><td>' + frappe.utils.escape_html(h.tax_template.matched) + '</td><td>-</td></tr>' : ''}
			</tbody>
		</table>
	`;

	// Validation warnings
	var warnings_html = "";
	if (data.validation.amount_mismatch) {
		warnings_html += `<div class="alert alert-warning" style="font-size: 13px;">
			<strong>Amount Mismatch:</strong> ${frappe.utils.escape_html(data.validation.amount_mismatch_details || "")}
		</div>`;
	}
	if (data.validation.duplicate_flag) {
		warnings_html += `<div class="alert alert-danger" style="font-size: 13px;">
			<strong>Duplicate Warning:</strong> ${frappe.utils.escape_html(data.validation.duplicate_details || "")}
		</div>`;
	}

	// Line items table
	var lines_html = "";
	if (data.line_items && data.line_items.length) {
		lines_html = `
			<h6 style="margin-top: 16px;">Line Items</h6>
			<table class="table table-bordered" style="font-size: 12px;">
				<thead><tr>
					<th style="width:5%;">#</th>
					<th style="width:30%;">Extracted Description</th>
					<th style="width:8%;">Qty</th>
					<th style="width:10%;">Rate</th>
					<th style="width:10%;">Amount</th>
					<th style="width:22%;">Matched Item</th>
					<th style="width:8%;">Conf.</th>
					<th style="width:7%;">Stage</th>
				</tr></thead>
				<tbody>`;

		data.line_items.forEach(function (li) {
			var conf = confidence_indicator(li.match_confidence);
			var item_display = li.matched_item
				? frappe.utils.escape_html(li.matched_item)
				: '<span class="text-muted">Not matched</span>';

			lines_html += `<tr data-line="${li.line_number}">
				<td>${li.line_number}</td>
				<td>${frappe.utils.escape_html(li.extracted_description || "-")}</td>
				<td>${frappe.utils.escape_html(li.extracted_qty || "-")}</td>
				<td>${frappe.utils.escape_html(li.extracted_rate || "-")}</td>
				<td>${frappe.utils.escape_html(li.extracted_amount || "-")}</td>
				<td>${item_display}</td>
				<td>${conf}</td>
				<td>${frappe.utils.escape_html(li.match_stage || "-")}</td>
			</tr>`;
		});
		lines_html += "</tbody></table>";
	}

	// Build dialog fields
	var fields = [
		{
			fieldtype: "HTML",
			fieldname: "review_html",
			options: warnings_html + header_html + lines_html,
		},
		{ fieldtype: "Section Break", label: __("Supplier Override") },
		{
			fieldtype: "Link",
			fieldname: "override_supplier",
			label: __("Supplier"),
			options: "Supplier",
			default: h.supplier.matched || "",
			description: __("Change if the matched supplier is wrong"),
		},
		{ fieldtype: "Section Break", label: __("Line Item Corrections") },
		{
			fieldtype: "HTML",
			fieldname: "corrections_help",
			options: '<p class="text-muted" style="font-size: 12px;">' +
				__("Correct items that were matched incorrectly. Your corrections teach the system for future invoices.") +
				"</p>",
		},
	];

	// Add correction fields for each line item
	if (data.line_items && data.line_items.length) {
		data.line_items.forEach(function (li) {
			fields.push({
				fieldtype: "Column Break",
			});
			fields.push({
				fieldtype: "HTML",
				fieldname: "line_label_" + li.line_number,
				options:
					'<div style="font-size: 12px; margin-bottom: 4px;"><strong>Line ' +
					li.line_number + ':</strong> ' +
					frappe.utils.escape_html(li.extracted_description || "") +
					" " + confidence_indicator(li.match_confidence) +
					"</div>",
			});
			fields.push({
				fieldtype: "Link",
				fieldname: "corrected_item_" + li.line_number,
				label: __("Item for Line {0}", [li.line_number]),
				options: "Item",
				default: li.matched_item || "",
			});
			fields.push({
				fieldtype: "Small Text",
				fieldname: "reasoning_" + li.line_number,
				label: __("Reasoning (Line {0})", [li.line_number]),
				description: __("Why this correction? Helps the system learn."),
			});
			fields.push({
				fieldtype: "Section Break",
			});
		});
	}

	var d = new frappe.ui.Dialog({
		title: __("Review Invoice: {0}", [frm.doc.name]),
		size: "extra-large",
		fields: fields,
		primary_action_label: __("Confirm & Create Invoice"),
		primary_action: function (values) {
			// Build corrections list from changed items
			var corrections = [];
			if (data.line_items) {
				data.line_items.forEach(function (li) {
					var corrected = values["corrected_item_" + li.line_number];
					var reasoning = values["reasoning_" + li.line_number];

					// Only include if the item was changed from the original match
					if (corrected && corrected !== li.matched_item) {
						corrections.push({
							line_number: li.line_number,
							corrected_item: corrected,
							reasoning: reasoning || "",
						});
					}
				});
			}

			// Build header overrides
			var header_overrides = {};
			if (values.override_supplier && values.override_supplier !== h.supplier.matched) {
				header_overrides.supplier = values.override_supplier;
			}

			d.hide();

			frappe.call({
				method: "invoice_automation.api.endpoints.confirm_mapping",
				args: {
					queue_name: frm.doc.name,
					corrections: corrections.length ? JSON.stringify(corrections) : null,
					header_overrides: Object.keys(header_overrides).length
						? JSON.stringify(header_overrides)
						: null,
				},
				freeze: true,
				freeze_message: __("Creating Purchase Invoice..."),
				callback: function (r) {
					frm.reload_doc();
					if (r.message && r.message.purchase_invoice) {
						frappe.show_alert({
							message: __("Purchase Invoice {0} created", [r.message.purchase_invoice]),
							indicator: "green",
						});
					} else if (r.message && r.message.status === "blocked") {
						frappe.msgprint({
							title: __("Blocked"),
							message: r.message.details
								? r.message.details.details || r.message.reason
								: r.message.reason,
							indicator: "orange",
						});
					}
				},
			});
		},
		secondary_action_label: __("Cancel"),
	});

	d.show();
	d.$wrapper.find(".modal-dialog").css("max-width", "960px");
}
