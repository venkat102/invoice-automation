import json

from .base_extractor import InvoiceExtractor
from .schema import ExtractedInvoiceData


class JSONExtractor(InvoiceExtractor):
	"""Accepts pre-extracted JSON data and validates it against the schema."""

	def extract(self, file_path: str) -> ExtractedInvoiceData:
		with open(file_path) as f:
			data = json.load(f)
		return ExtractedInvoiceData(**data)

	def supports_file_type(self, file_path: str) -> bool:
		return file_path.lower().endswith(".json")

	@classmethod
	def from_dict(cls, data: dict) -> ExtractedInvoiceData:
		return ExtractedInvoiceData(**data)

	@classmethod
	def from_json_string(cls, json_string: str) -> ExtractedInvoiceData:
		data = json.loads(json_string)
		return ExtractedInvoiceData(**data)
