"""PDF parser using LlamaParse for document ingestion."""

import frappe

from invoice_automation.extraction.file_handler import FileInfo
from invoice_automation.extraction.parsers.base_parser import ParsedDocument, ParserStrategy
from invoice_automation.utils.exceptions import ParsingError


class PDFParserStrategy(ParserStrategy):
	"""Parses PDF files (native, scanned, hybrid) using LlamaParse."""

	def supports(self, file_info: FileInfo) -> bool:
		return file_info.file_type == "PDF"

	def parse(self, file_info: FileInfo) -> ParsedDocument:
		try:
			api_key = frappe.db.get_single_value("Invoice Automation Settings", "llamaparse_api_key")
			result_type = (
				frappe.db.get_single_value("Invoice Automation Settings", "llamaparse_result_type")
				or "markdown"
			)
		except Exception:
			api_key = None
			result_type = "markdown"

		if not api_key:
			# Fallback: try basic text extraction with PyPDF or similar
			return self._fallback_parse(file_info)

		try:
			from llama_parse import LlamaParse

			parser = LlamaParse(api_key=api_key, result_type=result_type)
			documents = parser.load_data(file_info.file_path)

			if not documents:
				return ParsedDocument(
					text="",
					page_count=0,
					parsing_method="llamaparse",
					warnings=["LlamaParse returned no content"],
				)

			combined_text = "\n\n".join(doc.text for doc in documents)
			return ParsedDocument(
				text=combined_text,
				page_count=len(documents),
				parsing_method="llamaparse",
			)

		except ImportError:
			return self._fallback_parse(file_info)
		except Exception as e:
			raise ParsingError(f"LlamaParse failed: {e}", original=e) from e

	def _fallback_parse(self, file_info: FileInfo) -> ParsedDocument:
		"""Fallback: extract text from PDF without LlamaParse."""
		warnings = []
		text = ""

		try:
			import fitz  # PyMuPDF

			doc = fitz.open(file_info.file_path)
			pages = []
			for page in doc:
				pages.append(page.get_text())
			doc.close()
			text = "\n\n".join(pages)
			page_count = len(pages)

			if not text.strip():
				warnings.append("PDF appears to be scanned (no selectable text). LlamaParse API key required for OCR.")
		except ImportError:
			warnings.append("Neither LlamaParse nor PyMuPDF available for PDF parsing")
			page_count = 0
		except Exception as e:
			raise ParsingError(f"PDF fallback parsing failed: {e}", original=e) from e

		return ParsedDocument(
			text=text,
			page_count=page_count,
			parsing_method="pymupdf_fallback",
			warnings=warnings,
		)
