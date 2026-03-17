"""Factory for creating LLM provider instances based on settings."""

import importlib

from invoice_automation.utils.exceptions import LLMProviderError
from invoice_automation.utils.helpers import get_config_value


PROVIDERS = {
	"Ollama": "invoice_automation.llm.ollama_provider.OllamaProvider",
	"OpenAI": "invoice_automation.llm.openai_provider.OpenAIProvider",
	"Anthropic": "invoice_automation.llm.anthropic_provider.AnthropicProvider",
	"Gemini": "invoice_automation.llm.gemini_provider.GeminiProvider",
}


def get_llm_provider(purpose: str = "extraction"):
	"""Return the configured LLM provider for the given purpose.

	Args:
		purpose: "extraction" (file parsing + data extraction) or "matching" (Stage 5 item matching)

	Returns:
		An LLMProvider instance configured from Invoice Automation Settings.
	"""
	if purpose == "extraction":
		provider_name = get_config_value("extraction_llm_provider", "Ollama")
	elif purpose == "matching":
		provider_name = get_config_value("matching_llm_provider", "Anthropic")
	else:
		raise LLMProviderError(f"Unknown LLM purpose: {purpose}. Use 'extraction' or 'matching'.")

	dotted_path = PROVIDERS.get(provider_name)
	if not dotted_path:
		raise LLMProviderError(
			f"Unknown LLM provider: '{provider_name}'. "
			f"Supported providers: {', '.join(PROVIDERS.keys())}"
		)

	module_path, class_name = dotted_path.rsplit(".", 1)
	mod = importlib.import_module(module_path)
	cls = getattr(mod, class_name)
	return cls()
