"""Anthropic / Claude LLM provider."""

import frappe

from invoice_automation.llm.base import LLMProvider
from invoice_automation.utils.exceptions import LLMProviderError


class AnthropicProvider(LLMProvider):
	"""Uses Anthropic API (Claude Sonnet, Opus, Haiku) for text and vision generation."""

	def __init__(self):
		try:
			import anthropic  # noqa: F401
		except ImportError:
			raise LLMProviderError(
				"Anthropic provider requires the 'anthropic' package. Install with: pip install anthropic"
			)

		self.api_key = frappe.db.get_single_value("Invoice Automation Settings", "anthropic_api_key")
		if not self.api_key:
			raise LLMProviderError("Anthropic API key not configured in Invoice Automation Settings")

		self.model = (
			frappe.db.get_single_value("Invoice Automation Settings", "anthropic_model")
			or "claude-sonnet-4-20250514"
		)

	def _get_client(self):
		import anthropic

		return anthropic.Anthropic(api_key=self.api_key)

	def generate(self, prompt: str, system: str | None = None) -> str:
		return self.retry_on_transient(self.do_generate, prompt, system)

	def do_generate(self, prompt: str, system: str | None = None) -> str:
		client = self._get_client()
		kwargs = {
			"model": self.model,
			"max_tokens": 4096,
			"messages": [{"role": "user", "content": prompt}],
		}
		if system:
			kwargs["system"] = system

		response = client.messages.create(**kwargs)
		return response.content[0].text

	def generate_with_image(self, prompt: str, image_base64: str) -> str:
		return self.retry_on_transient(self.dodo_generate_with_image, prompt, image_base64)

	def dodo_generate_with_image(self, prompt: str, image_base64: str) -> str:
		client = self._get_client()
		response = client.messages.create(
			model=self.model,
			max_tokens=4096,
			messages=[
				{
					"role": "user",
					"content": [
						{
							"type": "image",
							"source": {
								"type": "base64",
								"media_type": "image/png",
								"data": image_base64,
							},
						},
						{"type": "text", "text": prompt},
					],
				}
			],
		)
		return response.content[0].text

	def health_check(self) -> dict:
		try:
			client = self._get_client()
			# Minimal API call to verify the key works
			client.messages.create(
				model=self.model,
				max_tokens=10,
				messages=[{"role": "user", "content": "ping"}],
			)
			return {
				"provider": "Anthropic",
				"status": "connected",
				"configured_model": self.model,
			}
		except Exception as e:
			return {"provider": "Anthropic", "status": "error", "error": str(e)}
