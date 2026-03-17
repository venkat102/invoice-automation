import frappe
from frappe.model.document import Document

from invoice_automation.matching.normalizer import normalize_text


class MappingAlias(Document):
	def before_save(self):
		if not self.normalized_text and self.raw_text:
			self.normalized_text = normalize_text(self.raw_text)

		if not self.composite_key:
			supplier = self.supplier_context or "ANY"
			self.composite_key = f"{supplier}:{self.normalized_text}:{self.source_doctype}"
