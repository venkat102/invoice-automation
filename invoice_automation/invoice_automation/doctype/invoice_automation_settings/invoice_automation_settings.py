import frappe
from frappe.model.document import Document


class InvoiceAutomationSettings(Document):
	def validate(self):
		if self.ollama_timeout_seconds and self.ollama_timeout_seconds < 10:
			frappe.throw("Ollama timeout must be at least 10 seconds")
		if self.max_file_size_mb and self.max_file_size_mb < 1:
			frappe.throw("Max file size must be at least 1 MB")
