"""Custom exception hierarchy for Invoice Automation."""


class InvoiceAutomationError(Exception):
	"""Base exception for all invoice automation errors."""

	def __init__(self, message: str, code: str = "UNKNOWN", original: Exception | None = None):
		self.message = message
		self.code = code
		self.original = original
		super().__init__(message)


# ── Extraction Errors ──


class ExtractionError(InvoiceAutomationError):
	"""Base for all extraction-related errors."""

	def __init__(self, message: str, code: str = "EXTRACTION_ERROR", original: Exception | None = None):
		super().__init__(message, code, original)


class FileValidationError(ExtractionError):
	"""Bad file type, too large, corrupt, or password-protected."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "FILE_VALIDATION_ERROR", original)


class ParsingError(ExtractionError):
	"""LlamaParse failure, LibreOffice conversion failure, etc."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "PARSING_ERROR", original)


class OllamaConnectionError(ExtractionError):
	"""Cannot reach the Ollama server."""

	def __init__(self, message: str = "Cannot connect to Ollama server", original: Exception | None = None):
		super().__init__(message, "OLLAMA_CONNECTION_ERROR", original)


class OllamaExtractionError(ExtractionError):
	"""Ollama returned unusable output after all retries."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "OLLAMA_EXTRACTION_ERROR", original)


class SchemaValidationError(ExtractionError):
	"""Extracted data doesn't match the Pydantic schema."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "SCHEMA_VALIDATION_ERROR", original)


# ── Matching Errors ──


class MatchingError(InvoiceAutomationError):
	"""Base for all matching-related errors."""

	def __init__(self, message: str, code: str = "MATCHING_ERROR", original: Exception | None = None):
		super().__init__(message, code, original)


class IndexNotReadyError(MatchingError):
	"""Redis or embedding index not built yet."""

	def __init__(self, message: str = "Index not ready", original: Exception | None = None):
		super().__init__(message, "INDEX_NOT_READY", original)


class LLMMatchingError(MatchingError):
	"""Claude API failure during Stage 5 matching."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "LLM_MATCHING_ERROR", original)


class InvoiceCreationError(MatchingError):
	"""Failed to create Purchase Invoice from matched data."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "INVOICE_CREATION_ERROR", original)


# ── Memory Errors ──


class MemoryError(InvoiceAutomationError):
	"""Base for correction memory errors."""

	def __init__(self, message: str, code: str = "MEMORY_ERROR", original: Exception | None = None):
		super().__init__(message, code, original)


class AliasConflictError(MemoryError):
	"""Contradictory alias corrections detected."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "ALIAS_CONFLICT_ERROR", original)


class EmbeddingUpdateError(MemoryError):
	"""Failed to update the embedding index."""

	def __init__(self, message: str, original: Exception | None = None):
		super().__init__(message, "EMBEDDING_UPDATE_ERROR", original)
