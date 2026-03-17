"""DOC parser: attempts LibreOffice conversion to DOCX/PDF."""

import subprocess
import tempfile
from pathlib import Path

from invoice_automation.extraction.file_handler import FileInfo
from invoice_automation.extraction.parsers.base_parser import ParsedDocument, ParserStrategy
from invoice_automation.utils.exceptions import ParsingError


class DOCParserStrategy(ParserStrategy):
	"""Converts .doc files via LibreOffice, then processes the result."""

	def supports(self, file_info: FileInfo) -> bool:
		return file_info.file_type == "DOC"

	def parse(self, file_info: FileInfo) -> ParsedDocument:
		with tempfile.TemporaryDirectory() as tmpdir:
			try:
				result = subprocess.run(
					[
						"libreoffice", "--headless", "--convert-to", "docx",
						"--outdir", tmpdir, file_info.file_path,
					],
					capture_output=True, text=True, timeout=60,
				)

				if result.returncode != 0:
					raise ParsingError(
						f"LibreOffice conversion failed: {result.stderr}. "
						"Please save the file as DOCX or PDF and re-upload."
					)

				# Find the converted file
				converted = list(Path(tmpdir).glob("*.docx"))
				if not converted:
					raise ParsingError(
						"LibreOffice conversion produced no output. "
						"Please save the file as DOCX or PDF and re-upload."
					)

				# Parse the converted DOCX
				from invoice_automation.extraction.parsers.docx_parser import DOCXParserStrategy

				docx_info = FileInfo(
					file_path=str(converted[0]),
					file_name=converted[0].name,
					file_hash=file_info.file_hash,
					file_type="DOCX",
					file_size_bytes=converted[0].stat().st_size,
					extension="docx",
					mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
				)

				doc = DOCXParserStrategy().parse(docx_info)
				doc.parsing_method = "libreoffice_to_docx"
				doc.warnings.append("Converted from DOC via LibreOffice")
				return doc

			except subprocess.TimeoutExpired as e:
				raise ParsingError("LibreOffice conversion timed out", original=e) from e
			except FileNotFoundError as e:
				raise ParsingError(
					"LibreOffice not installed. Please convert the file to DOCX or PDF manually.",
					original=e,
				) from e
