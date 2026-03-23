import frappe
from frappe.model.document import Document


class InvoiceProcessingQueue(Document):
	def after_insert(self):
		"""Auto-trigger the processing pipeline when a new record is created with a file."""
		if not self.source_file:
			return

		# Populate file metadata using db.set_value to avoid re-triggering hooks
		if not self.file_name:
			try:
				from invoice_automation.extraction.file_handler import FileHandler

				handler = FileHandler()
				file_info = handler.process_file(self.source_file)

				updates = {
					"file_name": file_info.file_name,
					"file_hash": file_info.file_hash,
					"file_type": file_info.file_type,
					"file_size_bytes": file_info.file_size_bytes,
				}

				# Check for duplicate file hash
				dup = handler.check_duplicate_hash(file_info.file_hash)
				if dup and dup != self.name:
					updates["duplicate_flag"] = 1
					updates["duplicate_details"] = f"Duplicate file: same hash as {dup}"

				frappe.db.set_value("Invoice Processing Queue", self.name, updates)
			except Exception as e:
				frappe.db.set_value("Invoice Processing Queue", self.name, "processing_error", str(e))
				frappe.log_error(f"File processing failed for {self.name}: {e}")

		# Enqueue the full pipeline — must run after commit so the worker can find the doc
		frappe.enqueue(
			"invoice_automation.api.endpoints._run_full_pipeline",
			queue_name=self.name,
			queue="default",
			timeout=600,
			enqueue_after_commit=True,
		)
