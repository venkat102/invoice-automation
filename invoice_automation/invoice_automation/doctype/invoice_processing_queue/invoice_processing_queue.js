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
				show_review_dialog(frm, "create");
			}).addClass("btn-primary");
		}

		// Correct Mappings
		if (
			frm.doc.matching_status === "Completed" &&
			!frm.doc.purchase_invoice
		) {
			frm.add_custom_button(__("Correct Mappings"), function () {
				show_review_dialog(frm, "correct_only");
			}, __("Actions"));
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


// ── Helpers ──

function show_review_dialog(frm, mode) {
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
			render_review_dialog(frm, r.message, mode);
		},
	});
}

function confidence_class(confidence) {
	if (confidence >= 90) return "high";
	if (confidence >= 60) return "medium";
	if (confidence > 0) return "low";
	return "none";
}

function confidence_badge(confidence) {
	var cls = confidence_class(confidence);
	var icon = cls === "high" ? "&#10003;" : cls === "medium" ? "&#9888;" : cls === "low" ? "&#10007;" : "&ndash;";
	return '<span class="confidence-badge ' + cls + '">' + icon + " " + (confidence > 0 ? confidence.toFixed(0) + "%" : "-") + "</span>";
}

function esc(val) {
	return frappe.utils.escape_html(val || "") || "-";
}

function sort_line_items(items) {
	// Low confidence first, then by line number
	return items.slice().sort(function (a, b) {
		var a_needs = (a.match_confidence || 0) < 90 ? 0 : 1;
		var b_needs = (b.match_confidence || 0) < 90 ? 0 : 1;
		if (a_needs !== b_needs) return a_needs - b_needs;
		return (a.line_number || 0) - (b.line_number || 0);
	});
}


// ── Main Dialog Renderer ──

function render_review_dialog(frm, data, mode) {
	var h = data.header;
	var is_create = mode === "create";
	var sorted_items = sort_line_items(data.line_items || []);
	var needs_attention_count = sorted_items.filter(function (li) { return (li.match_confidence || 0) < 90; }).length;

	// ── Build PDF panel ──
	var file_url = data.source_file || "";
	var file_type = (data.file_type || "").toLowerCase();
	var is_image = ["image", "png", "jpg", "jpeg", "tiff", "webp"].some(function (t) { return file_type.indexOf(t) >= 0; });
	var preview_html = "";
	if (file_url) {
		if (is_image) {
			preview_html = '<img src="' + file_url + '" alt="Invoice preview">';
		} else {
			preview_html = '<iframe src="' + file_url + '"></iframe>';
		}
	} else {
		preview_html = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">No preview available</div>';
	}

	var pdf_panel = `
		<div class="review-pdf-panel" id="review-pdf-panel">
			<div class="pdf-header">
				<span class="pdf-title">${__("Invoice Preview")}</span>
				<button class="btn-toggle-pdf" id="btn-toggle-pdf">${__("Hide")}</button>
			</div>
			${preview_html}
		</div>`;

	// ── Build warnings ──
	var warnings_html = "";
	var warning_items = [];
	if (data.extraction_warnings && data.extraction_warnings.length) {
		data.extraction_warnings.forEach(function (w) {
			warning_items.push('<div class="review-warning-item ' + (w.severity === "error" ? "error" : "info") + '">' + esc(w.message || w) + "</div>");
		});
	}
	if (data.validation.amount_mismatch) {
		warning_items.push('<div class="review-warning-item warning">' + __("Amount Mismatch") + ": " + esc(data.validation.amount_mismatch_details) + "</div>");
	}
	if (data.validation.duplicate_flag) {
		warning_items.push('<div class="review-warning-item error">' + __("Duplicate Warning") + ": " + esc(data.validation.duplicate_details) + "</div>");
	}
	if (warning_items.length) {
		warnings_html = '<div class="review-warnings">' + warning_items.join("") + "</div>";
	}

	// ── Build header card ──
	var header_fields_html = "";
	var header_rows = [
		{ label: __("Supplier"), value: h.supplier.matched || h.supplier.extracted, extra: h.supplier.extracted_tax_id, conf: h.supplier.confidence, editable: "supplier" },
		{ label: __("Invoice #"), value: h.invoice_number.matched || h.invoice_number.extracted },
		{ label: __("Date"), value: h.invoice_date.matched || h.invoice_date.extracted },
		{ label: __("Due Date"), value: h.due_date.matched || h.due_date.extracted },
		{ label: __("Currency"), value: h.currency.matched || h.currency.extracted },
		{ label: __("Total"), value: h.total_amount.matched || h.total_amount.extracted },
		{ label: __("Tax Template"), value: h.tax_template.matched, editable: "tax_template" },
		{ label: __("Cost Center"), value: (h.cost_center && h.cost_center.matched) || "", editable: "cost_center" },
	];

	header_rows.forEach(function (row) {
		var conf_html = row.conf ? " " + confidence_badge(row.conf) : "";
		var edit_btn = row.editable ? ' <span class="edit-btn" data-edit="' + row.editable + '">&#9998;</span>' : "";
		var extra_html = row.extra ? '<br><span style="font-size:10px;color:var(--text-muted);">' + esc(row.extra) + "</span>" : "";
		header_fields_html += `
			<div class="review-header-field" data-header-field="${row.editable || ""}">
				<span class="field-label">${row.label}</span>
				<span class="field-value">${esc(row.value)}${extra_html}${conf_html}${edit_btn}</span>
				<div class="field-edit" data-edit-target="${row.editable || ""}"></div>
			</div>`;
	});

	// Header override area (hidden by default, revealed when edit is clicked)
	var header_override_html = `
		<div class="header-override-area" id="header-override-area">
			<div class="header-override-grid">
				<div data-header-ctrl="supplier"></div>
				<div data-header-ctrl="supplier_reasoning"></div>
				<div data-header-ctrl="tax_template"></div>
				<div data-header-ctrl="tax_template_reasoning"></div>
				<div data-header-ctrl="cost_center"></div>
				<div data-header-ctrl="cost_center_reasoning"></div>
			</div>
		</div>`;

	var header_html = `
		<div class="review-header-card">
			<div class="header-title">
				<span>${__("Invoice Details")}</span>
				<span>${confidence_badge(data.overall_confidence)} <span style="font-size:var(--text-xs);color:var(--text-muted);margin-left:4px;">${esc(data.routing_decision)}</span></span>
			</div>
			<div class="review-header-grid">${header_fields_html}</div>
			${header_override_html}
		</div>`;

	// ── Build line items ──
	var lines_html = "";
	sorted_items.forEach(function (li) {
		var conf = li.match_confidence || 0;
		var needs = conf < 90;
		var unmatched = !li.matched_item;
		var card_cls = unmatched ? "unmatched" : needs ? "needs-attention" : "";
		var auto_expand = needs || unmatched;

		// Summary row (always visible)
		var amounts_html = "";
		if (li.extracted_qty) amounts_html += '<span>Qty: ' + esc(li.extracted_qty) + "</span>";
		if (li.extracted_rate) amounts_html += '<span>Rate: ' + esc(li.extracted_rate) + "</span>";
		if (li.extracted_amount) amounts_html += '<span>Amt: ' + esc(li.extracted_amount) + "</span>";

		var match_display = li.matched_item
			? esc(li.matched_item)
			: '<span style="color:var(--red-500);">' + __("Unmatched") + "</span>";

		// Detail grid (all extracted fields)
		var detail_fields = [];
		if (li.extracted_description) detail_fields.push({ l: __("Description"), v: li.extracted_description });
		if (li.extracted_qty) detail_fields.push({ l: __("Quantity"), v: li.extracted_qty });
		if (li.extracted_rate) detail_fields.push({ l: __("Unit Price"), v: li.extracted_rate });
		if (li.extracted_amount) detail_fields.push({ l: __("Amount"), v: li.extracted_amount });
		if (li.extracted_unit) detail_fields.push({ l: __("UOM"), v: li.extracted_unit });
		if (li.extracted_hsn) detail_fields.push({ l: __("HSN/SAC"), v: li.extracted_hsn });
		if (li.extracted_item_code) detail_fields.push({ l: __("Item Code"), v: li.extracted_item_code });
		if (li.extracted_sku) detail_fields.push({ l: __("SKU"), v: li.extracted_sku });
		if (li.extracted_tax_rate) detail_fields.push({ l: __("Tax Rate"), v: li.extracted_tax_rate + "%" });
		if (li.extracted_tax_amount) detail_fields.push({ l: __("Tax Amount"), v: li.extracted_tax_amount });
		if (li.extracted_discount) detail_fields.push({ l: __("Discount"), v: li.extracted_discount });

		var detail_grid = detail_fields.map(function (f) {
			return '<div class="line-detail-field"><span class="detail-label">' + f.l + '</span><span class="detail-value">' + esc(f.v) + "</span></div>";
		}).join("");

		lines_html += `
			<div class="review-line-item ${card_cls} ${auto_expand ? "expanded" : ""}" data-line="${li.line_number}">
				<div class="review-line-summary">
					<span class="line-num">#${li.line_number}</span>
					<span class="line-desc" title="${esc(li.extracted_description)}">${esc(li.extracted_description)}</span>
					<span class="line-amounts">${amounts_html}</span>
					<span class="line-match">${match_display}</span>
					${confidence_badge(conf)}
					<span class="stage-pill">${esc(li.match_stage)}</span>
					<span class="expand-icon">&#9654;</span>
				</div>
				<div class="review-line-detail">
					<div class="line-detail-grid">${detail_grid}</div>
					<div class="line-matched-row">
						<span class="matched-label">${__("Matched")} &rarr;</span>
						<span class="matched-value">${match_display}</span>
						${confidence_badge(conf)}
						<span class="stage-pill">${esc(li.match_stage)}</span>
					</div>
					<div class="line-correction-area">
						<div class="correction-title">${__("Correct this match")}</div>
						<div class="correction-fields">
							<div data-line-ctrl="corrected_item_${li.line_number}"></div>
							<div data-line-ctrl="reasoning_${li.line_number}"></div>
						</div>
					</div>
				</div>
			</div>`;
	});

	var attention_badge = needs_attention_count > 0
		? '<span class="attention-count">' + needs_attention_count + " " + __("need attention") + "</span>"
		: "";

	var lines_section = `
		<div class="review-lines-section">
			<div class="lines-title">${__("Line Items")} ${attention_badge}</div>
			${lines_html}
		</div>`;

	// ── Build data panel ──
	var data_panel = `
		<div class="review-data-panel">
			${warnings_html}
			${header_html}
			${lines_section}
		</div>`;

	// ── Build summary bar ──
	var summary_bar = `
		<div class="review-summary-bar" id="review-summary-bar">
			<div class="summary-info">
				<span class="summary-item ${needs_attention_count > 0 ? "has-attention" : ""}" id="summary-attention">
					${needs_attention_count > 0 ? "&#9888; " + needs_attention_count + " " + __("need review") : "&#10003; " + __("All items matched")}
				</span>
				<span class="summary-item" id="summary-changes">0 ${__("changes")}</span>
			</div>
			<div class="summary-actions" id="summary-actions"></div>
		</div>`;

	// ── Assemble full layout ──
	var layout_html = `
		<div class="review-container">${pdf_panel}${data_panel}</div>
		${summary_bar}`;

	// ── Create dialog ──
	var d = new frappe.ui.Dialog({
		title: is_create
			? __("Review Invoice: {0}", [frm.doc.name])
			: __("Correct Mappings: {0}", [frm.doc.name]),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "review_layout", options: layout_html }],
		primary_action_label: is_create ? __("Confirm & Create Invoice") : __("Save Corrections"),
		primary_action: function () {
			var args = collect_corrections_v2(data, controls, header_controls);
			d.hide();
			submit_corrections(frm, args, is_create);
		},
		secondary_action_label: __("Cancel"),
	});

	// Remove default modal body padding for edge-to-edge layout
	d.$wrapper.find(".modal-body").css({ padding: 0, overflow: "hidden" });
	d.$wrapper.find(".modal-dialog").css({ "max-width": "95vw", width: "95vw" });

	d.show();

	// ── Attach Frappe controls for line item corrections ──
	var controls = {};
	sorted_items.forEach(function (li) {
		var $item_wrapper = d.$wrapper.find('[data-line-ctrl="corrected_item_' + li.line_number + '"]');
		if ($item_wrapper.length) {
			var item_ctrl = frappe.ui.form.make_control({
				df: {
					fieldtype: "Link",
					fieldname: "corrected_item_" + li.line_number,
					options: "Item",
					label: __("Correct Item"),
					placeholder: __("Select correct item..."),
				},
				parent: $item_wrapper,
				render_input: true,
			});
			item_ctrl.set_value(li.matched_item || "");
			controls["corrected_item_" + li.line_number] = item_ctrl;

			item_ctrl.$input && item_ctrl.$input.on("change awesomplete-selectcomplete", function () {
				update_summary(d, data, controls, header_controls);
				mark_modified(d, li.line_number, item_ctrl.get_value(), li.matched_item);
			});
		}

		var $reason_wrapper = d.$wrapper.find('[data-line-ctrl="reasoning_' + li.line_number + '"]');
		if ($reason_wrapper.length) {
			var reason_ctrl = frappe.ui.form.make_control({
				df: {
					fieldtype: "Small Text",
					fieldname: "reasoning_" + li.line_number,
					label: __("Reasoning"),
					placeholder: __("Why this correction? Helps the system learn."),
				},
				parent: $reason_wrapper,
				render_input: true,
			});
			controls["reasoning_" + li.line_number] = reason_ctrl;
		}
	});

	// ── Attach Frappe controls for header overrides ──
	var header_controls = {};
	var header_defs = [
		{ name: "supplier", type: "Link", options: "Supplier", label: __("Supplier"), default_val: h.supplier.matched || "" },
		{ name: "supplier_reasoning", type: "Small Text", label: __("Supplier Reasoning"), placeholder: __("Why?") },
		{ name: "tax_template", type: "Link", options: "Purchase Taxes and Charges Template", label: __("Tax Template"), default_val: (h.tax_template && h.tax_template.matched) || "" },
		{ name: "tax_template_reasoning", type: "Small Text", label: __("Tax Template Reasoning"), placeholder: __("Why?") },
		{ name: "cost_center", type: "Link", options: "Cost Center", label: __("Cost Center"), default_val: (h.cost_center && h.cost_center.matched) || "" },
		{ name: "cost_center_reasoning", type: "Small Text", label: __("Cost Center Reasoning"), placeholder: __("Why?") },
	];

	header_defs.forEach(function (hd) {
		var $wrapper = d.$wrapper.find('[data-header-ctrl="' + hd.name + '"]');
		if ($wrapper.length) {
			var ctrl = frappe.ui.form.make_control({
				df: {
					fieldtype: hd.type,
					fieldname: "override_" + hd.name,
					options: hd.options || "",
					label: hd.label,
					placeholder: hd.placeholder || "",
				},
				parent: $wrapper,
				render_input: true,
			});
			if (hd.default_val) ctrl.set_value(hd.default_val);
			header_controls[hd.name] = ctrl;

			if (hd.type === "Link") {
				ctrl.$input && ctrl.$input.on("change awesomplete-selectcomplete", function () {
					update_summary(d, data, controls, header_controls);
				});
			}
		}
	});

	// ── Event: toggle PDF panel ──
	d.$wrapper.find("#btn-toggle-pdf").on("click", function () {
		var $panel = d.$wrapper.find("#review-pdf-panel");
		$panel.toggleClass("hidden");
		$(this).text($panel.hasClass("hidden") ? __("Show Preview") : __("Hide"));
	});

	// ── Event: expand/collapse line items ──
	d.$wrapper.find(".review-line-summary").on("click", function () {
		$(this).closest(".review-line-item").toggleClass("expanded");
	});

	// ── Event: header edit buttons ──
	d.$wrapper.find(".edit-btn").on("click", function (e) {
		e.stopPropagation();
		var $area = d.$wrapper.find("#header-override-area");
		$area.toggleClass("visible");
		// Scroll to it
		if ($area.hasClass("visible")) {
			$area[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
		}
	});

	// ── Save Corrections Only button (in create mode) ──
	if (is_create) {
		d.add_custom_action(
			__("Save Corrections Only"),
			function () {
				var args = collect_corrections_v2(data, controls, header_controls);
				if (!args.corrections && !args.header_overrides) {
					frappe.msgprint(__("No corrections to save."));
					return;
				}
				d.hide();
				submit_save_only(frm, args);
			},
			"btn-default"
		);
	}

	// Initial summary update
	update_summary(d, data, controls, header_controls);
}


// ── Collect corrections from controls ──

function collect_corrections_v2(data, controls, header_controls) {
	var corrections = [];
	if (data.line_items) {
		data.line_items.forEach(function (li) {
			var item_ctrl = controls["corrected_item_" + li.line_number];
			var reason_ctrl = controls["reasoning_" + li.line_number];
			var corrected = item_ctrl ? item_ctrl.get_value() : "";
			var reasoning = reason_ctrl ? reason_ctrl.get_value() : "";
			if (corrected && corrected !== li.matched_item) {
				corrections.push({
					line_number: li.line_number,
					corrected_item: corrected,
					reasoning: reasoning || "",
				});
			}
		});
	}

	var h = data.header;
	var header_overrides = {};
	var supplier_ctrl = header_controls.supplier;
	if (supplier_ctrl) {
		var supplier_val = supplier_ctrl.get_value();
		if (supplier_val && supplier_val !== h.supplier.matched) {
			header_overrides.supplier = supplier_val;
			var sr = header_controls.supplier_reasoning;
			if (sr && sr.get_value()) header_overrides.supplier_reasoning = sr.get_value();
		}
	}
	var tax_ctrl = header_controls.tax_template;
	if (tax_ctrl) {
		var tax_val = tax_ctrl.get_value();
		if (tax_val && tax_val !== (h.tax_template && h.tax_template.matched)) {
			header_overrides.tax_template = tax_val;
			var tr = header_controls.tax_template_reasoning;
			if (tr && tr.get_value()) header_overrides.tax_template_reasoning = tr.get_value();
		}
	}
	var cc_ctrl = header_controls.cost_center;
	if (cc_ctrl) {
		var cc_val = cc_ctrl.get_value();
		if (cc_val && cc_val !== (h.cost_center && h.cost_center.matched)) {
			header_overrides.cost_center = cc_val;
			var cr = header_controls.cost_center_reasoning;
			if (cr && cr.get_value()) header_overrides.cost_center_reasoning = cr.get_value();
		}
	}

	return {
		corrections: corrections.length ? JSON.stringify(corrections) : null,
		header_overrides: Object.keys(header_overrides).length ? JSON.stringify(header_overrides) : null,
	};
}


// ── Update summary bar ──

function update_summary(d, data, controls, header_controls) {
	var change_count = 0;

	// Count line item changes
	if (data.line_items) {
		data.line_items.forEach(function (li) {
			var ctrl = controls["corrected_item_" + li.line_number];
			if (ctrl) {
				var val = ctrl.get_value();
				if (val && val !== li.matched_item) change_count++;
			}
		});
	}

	// Count header changes
	var h = data.header;
	var sc = header_controls.supplier;
	if (sc && sc.get_value() && sc.get_value() !== h.supplier.matched) change_count++;
	var tc = header_controls.tax_template;
	if (tc && tc.get_value() && tc.get_value() !== (h.tax_template && h.tax_template.matched)) change_count++;
	var cc = header_controls.cost_center;
	if (cc && cc.get_value() && cc.get_value() !== (h.cost_center && h.cost_center.matched)) change_count++;

	var $changes = d.$wrapper.find("#summary-changes");
	$changes.text(change_count + " " + __("changes"));
	$changes.toggleClass("has-changes", change_count > 0);
}


// ── Mark line item as modified ──

function mark_modified(d, line_number, new_val, original_val) {
	var $card = d.$wrapper.find('.review-line-item[data-line="' + line_number + '"]');
	if (new_val && new_val !== original_val) {
		$card.addClass("modified");
	} else {
		$card.removeClass("modified");
	}
}


// ── Submit helpers ──

function submit_corrections(frm, args, is_create) {
	if (is_create) {
		frappe.call({
			method: "invoice_automation.api.endpoints.confirm_mapping",
			args: {
				queue_name: frm.doc.name,
				corrections: args.corrections,
				header_overrides: args.header_overrides,
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
	} else {
		submit_save_only(frm, args);
	}
}

function submit_save_only(frm, args) {
	frappe.call({
		method: "invoice_automation.api.endpoints.save_corrections",
		args: {
			queue_name: frm.doc.name,
			corrections: args.corrections,
			header_overrides: args.header_overrides,
		},
		freeze: true,
		freeze_message: __("Saving corrections..."),
		callback: function (r) {
			frm.reload_doc();
			if (r.message) {
				frappe.show_alert({
					message: __("{0} corrections saved. The system will use these for future invoices.", [r.message.corrections_applied]),
					indicator: "green",
				});
			}
		},
	});
}
