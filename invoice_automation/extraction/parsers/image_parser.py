"""Image parser: sends image to the configured LLM vision model."""

import base64

from invoice_automation.extraction.file_handler import FileInfo
from invoice_automation.extraction.parsers.base_parser import ParsedDocument, ParserStrategy
from invoice_automation.utils.exceptions import ParsingError


class ImageParserStrategy(ParserStrategy):
	"""Sends image files to the configured LLM provider's vision model for text extraction."""

	def supports(self, file_info: FileInfo) -> bool:
		return file_info.file_type == "Image"

	def parse(self, file_info: FileInfo) -> ParsedDocument:
		try:
			from invoice_automation.llm import get_llm_provider

			provider = get_llm_provider("extraction")

			# Read and base64-encode the image
			with open(file_info.file_path, "rb") as f:
				image_data = base64.b64encode(f.read()).decode("utf-8")

			prompt = (
				"Extract all text visible in this invoice image. "
				"Preserve the layout and structure as much as possible. "
				"Include all numbers, dates, names, addresses, and line items."
			)

			text = provider.generate_with_image(prompt, image_data)

			warnings = []
			if len(text.strip()) < 50:
				warnings.append("Very little text extracted from image — may be low quality or non-invoice")

			return ParsedDocument(
				text=text,
				page_count=1,
				parsing_method="llm_vision",
				warnings=warnings,
			)

		except Exception as e:
			raise ParsingError(f"Image parsing via LLM failed: {e}", original=e) from e
