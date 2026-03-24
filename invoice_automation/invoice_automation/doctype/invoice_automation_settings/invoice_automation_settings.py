import frappe
from frappe import _
from frappe.model.document import Document


class InvoiceAutomationSettings(Document):
	def validate(self):
		if self.ollama_timeout_seconds and self.ollama_timeout_seconds < 10:
			frappe.throw(_("Ollama timeout must be at least 10 seconds"))
		if self.max_file_size_mb and self.max_file_size_mb < 1:
			frappe.throw(_("Max file size must be at least 1 MB"))

		self._validate_thresholds()
		self._validate_api_keys()

	def _validate_thresholds(self):
		"""Validate that confidence thresholds are in valid ranges and logically consistent."""
		threshold_fields = {
			"auto_create_threshold": "Auto Create Threshold",
			"review_threshold": "Review Threshold",
			"fuzzy_match_threshold": "Fuzzy Match Threshold",
		}
		for field, label in threshold_fields.items():
			value = getattr(self, field, None)
			if value is not None and (value < 0 or value > 100):
				frappe.throw(_("{0} must be between 0 and 100").format(label))

		# Embedding thresholds are 0-1
		for field, label in {
			"embedding_similarity_threshold": "Embedding Similarity Threshold",
			"embedding_review_threshold": "Embedding Review Threshold",
		}.items():
			value = getattr(self, field, None)
			if value is not None and (value < 0 or value > 1):
				frappe.throw(_("{0} must be between 0 and 1").format(label))

		if (
			self.auto_create_threshold
			and self.review_threshold
			and self.auto_create_threshold < self.review_threshold
		):
			frappe.throw(_("Auto Create Threshold must be greater than or equal to Review Threshold"))

	def _validate_api_keys(self):
		"""Warn if a provider is selected but its API key is missing."""
		provider_key_map = {
			"OpenAI": "openai_api_key",
			"Anthropic": "anthropic_api_key",
			"Gemini": "gemini_api_key",
		}
		selected_providers = set()
		if self.extraction_llm_provider:
			selected_providers.add(self.extraction_llm_provider)
		if self.matching_llm_provider:
			selected_providers.add(self.matching_llm_provider)

		for provider in selected_providers:
			key_field = provider_key_map.get(provider)
			if key_field and not getattr(self, key_field, None):
				frappe.throw(
					_("{0} is selected as a provider but its API key is not configured").format(provider)
				)
