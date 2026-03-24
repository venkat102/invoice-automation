frappe.listview_settings["Invoice Processing Queue"] = {
	get_indicator: function (doc) {
		var status_map = {
			"Pending": [__("Pending"), "grey", "workflow_state,=,Pending"],
			"Extracting": [__("Extracting"), "blue", "workflow_state,=,Extracting"],
			"Extracted": [__("Extracted"), "blue", "workflow_state,=,Extracted"],
			"Matching": [__("Matching"), "blue", "workflow_state,=,Matching"],
			"Matched": [__("Matched"), "blue", "workflow_state,=,Matched"],
			"Routed": [__("Routed"), "purple", "workflow_state,=,Routed"],
			"Under Review": [__("Under Review"), "orange", "workflow_state,=,Under Review"],
			"Invoice Created": [__("Invoice Created"), "green", "workflow_state,=,Invoice Created"],
			"Rejected": [__("Rejected"), "red", "workflow_state,=,Rejected"],
			"Failed": [__("Failed"), "red", "workflow_state,=,Failed"],
		};
		return status_map[doc.workflow_state] || [__(doc.workflow_state), "grey", ""];
	},
};
