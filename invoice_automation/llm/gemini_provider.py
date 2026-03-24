"""Google Gemini LLM provider."""

import json

import frappe

from invoice_automation.llm.base import LLMProvider
from invoice_automation.utils.exceptions import LLMProviderError


class GeminiProvider(LLMProvider):
	"""Uses Google Gemini API (gemini-2.0-flash, gemini-2.5-pro, etc.) for text and vision."""

	def __init__(self):
		try:
			from google import genai  # noqa: F401
		except ImportError:
			raise LLMProviderError(
				"Gemini provider requires the 'google-genai' package. "
				"Install with: pip install google-genai"
			)

		self.api_key = frappe.db.get_single_value("Invoice Automation Settings", "gemini_api_key")
		if not self.api_key:
			raise LLMProviderError("Gemini API key not configured in Invoice Automation Settings")

		self.model = (
			frappe.db.get_single_value("Invoice Automation Settings", "gemini_model")
			or "gemini-2.0-flash"
		)

	def _get_client(self):
		from google import genai

		return genai.Client(api_key=self.api_key)

	def generate(self, prompt: str, system: str | None = None) -> str:
		return self.retry_on_transient(self.do_generate, prompt, system)

	def do_generate(self, prompt: str, system: str | None = None) -> str:
		from google.genai import types

		client = self._get_client()
		config = types.GenerateContentConfig(system_instruction=system) if system else None
		response = client.models.generate_content(
			model=self.model,
			contents=prompt,
			config=config,
		)
		return response.text or ""

	def generate_with_image(self, prompt: str, image_base64: str) -> str:
		return self.retry_on_transient(self.dodo_generate_with_image, prompt, image_base64)

	def dodo_generate_with_image(self, prompt: str, image_base64: str) -> str:
		import base64

		from google.genai import types

		image_bytes = base64.b64decode(image_base64)
		image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")

		client = self._get_client()
		response = client.models.generate_content(
			model=self.model,
			contents=[image_part, prompt],
		)
		return response.text or ""

	def generate_json(self, prompt: str, system: str | None = None) -> dict:
		"""Use Gemini's native JSON output mode."""
		from google.genai import types

		client = self._get_client()
		config = types.GenerateContentConfig(
			response_mime_type="application/json",
			system_instruction=system,
		)

		try:
			response = client.models.generate_content(
				model=self.model,
				contents=prompt,
				config=config,
			)
			return json.loads(response.text or "{}")
		except (json.JSONDecodeError, Exception):
			return super().generate_json(prompt, system)

	def health_check(self) -> dict:
		try:
			client = self._get_client()
			# List models to verify the key works
			models = list(client.models.list())
			model_names = [m.name for m in models[:20]]
			return {
				"provider": "Gemini",
				"status": "connected",
				"configured_model": self.model,
				"available_models": model_names,
			}
		except Exception as e:
			return {"provider": "Gemini", "status": "error", "error": str(e)}
