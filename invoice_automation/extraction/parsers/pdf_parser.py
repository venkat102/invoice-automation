"""PDF parser: LlamaParse → PyMuPDF text → LLM vision fallback."""

import base64

import frappe

from invoice_automation.extraction.file_handler import FileInfo
from invoice_automation.extraction.parsers.base_parser import ParsedDocument, ParserStrategy
from invoice_automation.utils.exceptions import ParsingError


class PDFParserStrategy(ParserStrategy):
	"""Parses PDF files (native, scanned, hybrid).

	Strategy chain:
	  1. LlamaParse (if API key configured)
	  2. PyMuPDF text extraction (native PDFs)
	  3. LLM vision — render pages to images and send to the configured LLM (scanned PDFs)
	"""

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

		# Strategy 1: LlamaParse
		if api_key:
			result = self._parse_with_llamaparse(file_info, api_key, result_type)
			if result and result.text.strip():
				return result

		# Strategy 2: PyMuPDF text extraction
		result = self._parse_with_pymupdf(file_info)
		if result and result.text.strip():
			return result

		# Strategy 3: LLM vision (renders PDF pages as images)
		return self._parse_with_vision(file_info)

	def _parse_with_llamaparse(self, file_info: FileInfo, api_key: str, result_type: str) -> ParsedDocument | None:
		"""Parse using LlamaParse cloud API."""
		try:
			from llama_parse import LlamaParse

			parser = LlamaParse(api_key=api_key, result_type=result_type)
			documents = parser.load_data(file_info.file_path)

			if not documents:
				return None

			combined_text = "\n\n".join(doc.text for doc in documents)
			return ParsedDocument(
				text=combined_text,
				page_count=len(documents),
				parsing_method="llamaparse",
			)
		except ImportError:
			return None
		except Exception as e:
			frappe.log_error(f"LlamaParse failed for {file_info.file_name}: {e}")
			return None

	def _parse_with_pymupdf(self, file_info: FileInfo) -> ParsedDocument | None:
		"""Extract selectable text from native PDFs using PyMuPDF."""
		try:
			import fitz  # PyMuPDF

			doc = fitz.open(file_info.file_path)
			pages = []
			for page in doc:
				pages.append(page.get_text())
			doc.close()
			text = "\n\n".join(pages)

			if not text.strip():
				return None

			return ParsedDocument(
				text=text,
				page_count=len(pages),
				parsing_method="pymupdf",
			)
		except ImportError:
			return None
		except Exception as e:
			frappe.log_error(f"PyMuPDF failed for {file_info.file_name}: {e}")
			return None

	def _parse_with_vision(self, file_info: FileInfo) -> ParsedDocument:
		"""Render PDF pages to images and send to the LLM vision model."""
		warnings = []

		try:
			import fitz  # PyMuPDF needed to render pages to images
		except ImportError:
			return ParsedDocument(
				text="",
				page_count=0,
				parsing_method="vision_failed",
				warnings=["PyMuPDF is required to render PDF pages for vision extraction. "
				          "Install with: pip install PyMuPDF"],
			)

		try:
			from invoice_automation.llm import get_llm_provider

			provider = get_llm_provider("extraction")
			doc = fitz.open(file_info.file_path)
			page_count = len(doc)

			all_text = []
			# Process up to 10 pages to avoid excessive API calls
			max_pages = min(page_count, 10)
			if page_count > max_pages:
				warnings.append(f"PDF has {page_count} pages, only first {max_pages} processed via vision")

			for i in range(max_pages):
				page = doc[i]
				# Render at 200 DPI for good OCR quality
				pix = page.get_pixmap(dpi=200)
				image_bytes = pix.tobytes("png")
				image_b64 = base64.b64encode(image_bytes).decode("utf-8")

				prompt = (
					f"Extract ALL text from this invoice image (page {i + 1} of {page_count}). "
					"Preserve the layout, numbers, dates, names, addresses, and line items. "
					"Return only the extracted text, no commentary."
				)

				page_text = provider.generate_with_image(prompt, image_b64)
				if page_text and page_text.strip():
					all_text.append(page_text.strip())

			doc.close()

			text = "\n\n".join(all_text)
			if not text.strip():
				warnings.append("LLM vision could not extract text from PDF pages")

			return ParsedDocument(
				text=text,
				page_count=page_count,
				parsing_method="llm_vision",
				warnings=warnings,
			)

		except Exception as e:
			return ParsedDocument(
				text="",
				page_count=0,
				parsing_method="vision_failed",
				warnings=[f"PDF vision extraction failed: {e}"],
			)
