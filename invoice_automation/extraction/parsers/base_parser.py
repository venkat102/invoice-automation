"""Abstract base class for file parser strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from invoice_automation.extraction.file_handler import FileInfo


@dataclass
class ParsedDocument:
	"""Result of parsing a file into text/markdown."""
	text: str
	page_count: int = 1
	parsing_method: str = ""
	warnings: list[str] = field(default_factory=list)


class ParserStrategy(ABC):
	"""Base class for file format parsers. Implement one per format."""

	@abstractmethod
	def parse(self, file_info: FileInfo) -> ParsedDocument:
		"""Parse the file and return extracted text/markdown."""
		...

	@abstractmethod
	def supports(self, file_info: FileInfo) -> bool:
		"""Return True if this parser handles this file type."""
		...


def get_parser(file_info: FileInfo) -> ParserStrategy:
	"""Factory: return the appropriate parser for the file type."""
	from invoice_automation.extraction.parsers.pdf_parser import PDFParserStrategy
	from invoice_automation.extraction.parsers.image_parser import ImageParserStrategy
	from invoice_automation.extraction.parsers.docx_parser import DOCXParserStrategy
	from invoice_automation.extraction.parsers.doc_parser import DOCParserStrategy
	from invoice_automation.extraction.parsers.fallback_parser import FallbackParser

	parsers = [
		PDFParserStrategy(),
		ImageParserStrategy(),
		DOCXParserStrategy(),
		DOCParserStrategy(),
		FallbackParser(),
	]

	for parser in parsers:
		if parser.supports(file_info):
			return parser

	return FallbackParser()
