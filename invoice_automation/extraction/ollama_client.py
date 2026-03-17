"""Ollama API client for LLM extraction. Configurable, swappable."""

import json

import frappe
import httpx

from invoice_automation.utils.exceptions import OllamaConnectionError, OllamaExtractionError


class OllamaClient:
	"""Connects to Ollama via HTTP API. Reads config from Invoice Automation Settings."""

	def __init__(self):
		self._load_settings()

	def _load_settings(self):
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
		"""Send a text prompt to Ollama and return the response text."""
		payload = {
			"model": self.model,
			"prompt": prompt,
			"stream": False,
		}
		if system:
			payload["system"] = system

		return self._call_api("/api/generate", payload)

	def generate_with_image(self, prompt: str, image_base64: str) -> str:
		"""Send a prompt with an image to the Ollama vision model."""
		payload = {
			"model": self.model,
			"prompt": prompt,
			"images": [image_base64],
			"stream": False,
		}

		return self._call_api("/api/generate", payload)

	def generate_json(self, prompt: str, system: str | None = None) -> dict:
		"""Send a prompt and request JSON output. Retries on malformed JSON."""
		from invoice_automation.extraction.json_repair import repair_json

		retry_count = 3
		try:
			retry_count = int(
				frappe.db.get_single_value("Invoice Automation Settings", "json_retry_count") or 3
			)
		except Exception:
			pass

		last_error = None
		for attempt in range(retry_count):
			raw = self.generate(prompt, system)

			# Try direct parse
			try:
				return json.loads(raw)
			except json.JSONDecodeError:
				pass

			# Try repair
			try:
				repaired = repair_json(raw)
				if repaired is not None:
					return repaired
			except Exception:
				pass

			last_error = f"Attempt {attempt + 1}: malformed JSON from Ollama"

		raise OllamaExtractionError(
			f"Failed to get valid JSON after {retry_count} attempts. Last error: {last_error}"
		)

	def _call_api(self, endpoint: str, payload: dict) -> str:
		"""Make an HTTP call to Ollama API."""
		url = f"{self.base_url.rstrip('/')}{endpoint}"

		try:
			with httpx.Client(timeout=self.timeout) as client:
				response = client.post(url, json=payload)
				response.raise_for_status()
				data = response.json()
				return data.get("response", "")

		except httpx.ConnectError as e:
			raise OllamaConnectionError(
				f"Cannot connect to Ollama at {self.base_url}. Is it running?", original=e
			) from e
		except httpx.TimeoutException as e:
			raise OllamaExtractionError(
				f"Ollama request timed out after {self.timeout}s", original=e
			) from e
		except httpx.HTTPStatusError as e:
			raise OllamaExtractionError(
				f"Ollama returned HTTP {e.response.status_code}: {e.response.text[:200]}", original=e
			) from e
		except Exception as e:
			raise OllamaExtractionError(f"Ollama API error: {e}", original=e) from e

	def health_check(self) -> dict:
		"""Check if Ollama is reachable and the model is available."""
		try:
			with httpx.Client(timeout=10) as client:
				resp = client.get(f"{self.base_url.rstrip('/')}/api/tags")
				resp.raise_for_status()
				models = resp.json().get("models", [])
				model_names = [m.get("name", "") for m in models]
				return {
					"status": "connected",
					"base_url": self.base_url,
					"configured_model": self.model,
					"model_available": self.model in model_names,
					"available_models": model_names,
				}
		except Exception as e:
			return {"status": "unreachable", "base_url": self.base_url, "error": str(e)}
