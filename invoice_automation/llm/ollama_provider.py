"""Ollama LLM provider — local open-source models via HTTP API."""

import frappe
import httpx

from invoice_automation.llm.base import LLMProvider
from invoice_automation.utils.exceptions import LLMConnectionError, LLMProviderError


class OllamaProvider(LLMProvider):
	"""Connects to a local Ollama instance for text and vision generation."""

	def __init__(self):
		try:
			self.base_url = (
				frappe.db.get_single_value("Invoice Automation Settings", "ollama_base_url")
				or "http://localhost:11434"
			)
			self.model = (
				frappe.db.get_single_value("Invoice Automation Settings", "ollama_model")
				or "qwen2.5vl:7b"
			)
			self.timeout = int(
				frappe.db.get_single_value("Invoice Automation Settings", "ollama_timeout_seconds") or 120
			)
		except Exception:
			self.base_url = "http://localhost:11434"
			self.model = "qwen2.5vl:7b"
			self.timeout = 120

	def generate(self, prompt: str, system: str | None = None) -> str:
		payload = {
			"model": self.model,
			"prompt": prompt,
			"stream": False,
		}
		if system:
			payload["system"] = system
		return self._retry_on_transient(self._call_api, "/api/generate", payload)

	def generate_with_image(self, prompt: str, image_base64: str) -> str:
		payload = {
			"model": self.model,
			"prompt": prompt,
			"images": [image_base64],
			"stream": False,
		}
		return self._retry_on_transient(self._call_api, "/api/generate", payload)

	def health_check(self) -> dict:
		try:
			with httpx.Client(timeout=10) as client:
				resp = client.get(f"{self.base_url.rstrip('/')}/api/tags")
				resp.raise_for_status()
				models = resp.json().get("models", [])
				model_names = [m.get("name", "") for m in models]
				return {
					"provider": "Ollama",
					"status": "connected",
					"base_url": self.base_url,
					"configured_model": self.model,
					"model_available": self.model in model_names,
					"available_models": model_names,
				}
		except Exception as e:
			return {"provider": "Ollama", "status": "unreachable", "base_url": self.base_url, "error": str(e)}

	def _call_api(self, endpoint: str, payload: dict) -> str:
		url = f"{self.base_url.rstrip('/')}{endpoint}"
		try:
			with httpx.Client(timeout=self.timeout) as client:
				response = client.post(url, json=payload)
				response.raise_for_status()
				data = response.json()
				return data.get("response", "")
		except httpx.ConnectError as e:
			raise LLMConnectionError(
				f"Cannot connect to Ollama at {self.base_url}. Is it running?", original=e
			) from e
		except httpx.TimeoutException as e:
			raise LLMProviderError(
				f"Ollama request timed out after {self.timeout}s", original=e
			) from e
		except httpx.HTTPStatusError as e:
			raise LLMProviderError(
				f"Ollama returned HTTP {e.response.status_code}: {e.response.text[:200]}", original=e
			) from e
		except Exception as e:
			raise LLMProviderError(f"Ollama API error: {e}", original=e) from e
