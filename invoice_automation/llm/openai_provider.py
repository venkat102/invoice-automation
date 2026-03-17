"""OpenAI / ChatGPT LLM provider."""

import json

import frappe

from invoice_automation.llm.base import LLMProvider
from invoice_automation.utils.exceptions import LLMProviderError


class OpenAIProvider(LLMProvider):
	"""Uses OpenAI API (GPT-4o, GPT-4o-mini, etc.) for text and vision generation."""

	def __init__(self):
		try:
			import openai  # noqa: F401
		except ImportError:
			raise LLMProviderError(
				"OpenAI provider requires the 'openai' package. Install with: pip install openai"
			)

		self.api_key = frappe.db.get_single_value("Invoice Automation Settings", "openai_api_key")
		if not self.api_key:
			raise LLMProviderError("OpenAI API key not configured in Invoice Automation Settings")

		self.model = (
			frappe.db.get_single_value("Invoice Automation Settings", "openai_model") or "gpt-4o"
		)

	def _get_client(self):
		import openai

		return openai.OpenAI(api_key=self.api_key)

	def generate(self, prompt: str, system: str | None = None) -> str:
		client = self._get_client()
		messages = []
		if system:
			messages.append({"role": "system", "content": system})
		messages.append({"role": "user", "content": prompt})

		response = client.chat.completions.create(
			model=self.model,
			messages=messages,
			max_tokens=4096,
		)
		return response.choices[0].message.content or ""

	def generate_with_image(self, prompt: str, image_base64: str) -> str:
		client = self._get_client()
		messages = [
			{
				"role": "user",
				"content": [
					{"type": "text", "text": prompt},
					{
						"type": "image_url",
						"image_url": {"url": f"data:image/png;base64,{image_base64}"},
					},
				],
			}
		]

		response = client.chat.completions.create(
			model=self.model,
			messages=messages,
			max_tokens=4096,
		)
		return response.choices[0].message.content or ""

	def generate_json(self, prompt: str, system: str | None = None) -> dict:
		"""Use OpenAI's native JSON mode for structured output."""
		client = self._get_client()
		messages = []
		if system:
			messages.append({"role": "system", "content": system})
		messages.append({"role": "user", "content": prompt})

		try:
			response = client.chat.completions.create(
				model=self.model,
				messages=messages,
				max_tokens=4096,
				response_format={"type": "json_object"},
			)
			text = response.choices[0].message.content or ""
			return json.loads(text)
		except (json.JSONDecodeError, Exception):
			# Fall back to base class retry-and-repair logic
			return super().generate_json(prompt, system)

	def health_check(self) -> dict:
		try:
			client = self._get_client()
			client.models.retrieve(self.model)
			return {
				"provider": "OpenAI",
				"status": "connected",
				"configured_model": self.model,
			}
		except Exception as e:
			return {"provider": "OpenAI", "status": "error", "error": str(e)}
