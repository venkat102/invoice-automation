"""Abstract base class for LLM providers."""

import json
from abc import ABC, abstractmethod

from invoice_automation.utils.exceptions import LLMProviderError


class LLMProvider(ABC):
	"""Common interface for all LLM backends (Ollama, OpenAI, Anthropic, Gemini)."""

	@abstractmethod
	def generate(self, prompt: str, system: str | None = None) -> str:
		"""Send a text prompt and return the response text."""

	@abstractmethod
	def generate_with_image(self, prompt: str, image_base64: str) -> str:
		"""Send a prompt with a base64-encoded image and return the response text."""

	def generate_json(self, prompt: str, system: str | None = None) -> dict:
		"""Generate a JSON response. Retries with repair on malformed output.

		Providers with native JSON mode (OpenAI, Gemini) can override this.
		"""
		from invoice_automation.extraction.json_repair import repair_json
		from invoice_automation.utils.helpers import get_config_value

		retry_count = int(get_config_value("json_retry_count", 3))
		last_error = None

		for attempt in range(retry_count):
			raw = self.generate(prompt, system)

			try:
				return json.loads(raw)
			except json.JSONDecodeError:
				pass

			try:
				repaired = repair_json(raw)
				if repaired is not None:
					return repaired
			except Exception:
				pass

			last_error = f"Attempt {attempt + 1}: malformed JSON"

		raise LLMProviderError(
			f"Failed to get valid JSON after {retry_count} attempts. {last_error}"
		)

	@abstractmethod
	def health_check(self) -> dict:
		"""Check if the provider is reachable and properly configured."""
