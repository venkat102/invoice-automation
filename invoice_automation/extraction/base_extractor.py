from abc import ABC, abstractmethod

from .schema import ExtractedInvoiceData


class InvoiceExtractor(ABC):
	"""Abstract base class for invoice extraction implementations."""

	@abstractmethod
	def extract(self, file_path: str) -> ExtractedInvoiceData:
		"""Extract invoice data from a file."""
		...

	@abstractmethod
	def supports_file_type(self, file_path: str) -> bool:
		"""Check if this extractor supports the given file type."""
		...
