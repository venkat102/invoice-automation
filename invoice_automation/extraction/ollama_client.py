"""Backward-compatible shim. Use invoice_automation.llm.get_llm_provider('extraction') instead."""

from invoice_automation.llm.ollama_provider import OllamaProvider as OllamaClient  # noqa: F401
