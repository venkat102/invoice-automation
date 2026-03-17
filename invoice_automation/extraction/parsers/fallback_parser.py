"""Fallback parser for unsupported file types."""

from invoice_automation.extraction.file_handler import FileInfo
from invoice_automation.extraction.parsers.base_parser import ParsedDocument, ParserStrategy
from invoice_automation.utils.exceptions import FileValidationError


class FallbackParser(ParserStrategy):
	"""Returns a structured error for unsupported file types."""

	def supports(self, file_info: FileInfo) -> bool:
		return True  # Always matches as last resort

	def parse(self, file_info: FileInfo) -> ParsedDocument:
		raise FileValidationError(
			f"Unsupported file type: {file_info.file_type} ({file_info.extension}). "
			f"Supported formats: PDF, PNG, JPG, JPEG, TIFF, WEBP, DOCX, DOC"
		)
