"""File type detection, validation, and preprocessing."""

from dataclasses import dataclass
from pathlib import Path

import frappe

from invoice_automation.utils.exceptions import FileValidationError
from invoice_automation.utils.file_utils import compute_sha256, detect_file_type, detect_mime_type


@dataclass
class FileInfo:
	"""Metadata about a processed file."""
	file_path: str
	file_name: str
	file_hash: str
	file_type: str  # PDF, Image, DOCX, DOC, Unknown
	file_size_bytes: int
	extension: str
	mime_type: str


class FileHandler:
	"""Handles file validation, type detection, and preprocessing."""

	def __init__(self):
		self._load_settings()

	def _load_settings(self):
		try:
			self.max_file_size_mb = int(
				frappe.db.get_single_value("Invoice Automation Settings", "max_file_size_mb") or 25
			)
			self.allowed_extensions = (
				frappe.db.get_single_value("Invoice Automation Settings", "allowed_extensions")
				or "pdf,png,jpg,jpeg,tiff,webp,docx,doc"
			)
		except Exception:
			self.max_file_size_mb = 25
			self.allowed_extensions = "pdf,png,jpg,jpeg,tiff,webp,docx,doc"

	def process_file(self, file_url: str) -> FileInfo:
		"""Download from Frappe file URL, validate, and return FileInfo."""
		# Resolve the file path from Frappe's file system
		file_path = self._resolve_file_path(file_url)
		return self.process_local_file(file_path)

	def process_local_file(self, file_path: str) -> FileInfo:
		"""Validate a local file and return FileInfo."""
		path = Path(file_path)

		if not path.exists():
			raise FileValidationError(f"File not found: {file_path}")

		file_size = path.stat().st_size
		if file_size == 0:
			raise FileValidationError("File is empty (zero bytes)")

		if file_size > self.max_file_size_mb * 1024 * 1024:
			raise FileValidationError(
				f"File size ({file_size / 1024 / 1024:.1f} MB) exceeds limit ({self.max_file_size_mb} MB)"
			)

		ext = path.suffix.lower().lstrip(".")
		allowed = [e.strip().lower() for e in self.allowed_extensions.split(",")]
		if ext not in allowed:
			raise FileValidationError(
				f"File extension '.{ext}' not allowed. Allowed: {self.allowed_extensions}"
			)

		return FileInfo(
			file_path=str(path),
			file_name=path.name,
			file_hash=compute_sha256(str(path)),
			file_type=detect_file_type(str(path)),
			file_size_bytes=file_size,
			extension=ext,
			mime_type=detect_mime_type(str(path)),
		)

	def _resolve_file_path(self, file_url: str) -> str:
		"""Resolve a Frappe file URL to a local file path."""
		if file_url.startswith("/files/") or file_url.startswith("/private/files/"):
			site_path = frappe.get_site_path()
			if file_url.startswith("/private/"):
				return str(Path(site_path) / file_url.lstrip("/"))
			return str(Path(site_path) / "public" / file_url.lstrip("/"))

		# Could be a full path already
		if Path(file_url).exists():
			return file_url

		raise FileValidationError(f"Cannot resolve file path: {file_url}")

	def check_duplicate_hash(self, file_hash: str) -> str | None:
		"""Check if a file with this hash already exists in the queue. Returns queue name or None."""
		existing = frappe.db.get_value(
			"Invoice Processing Queue",
			{"file_hash": file_hash, "workflow_state": ["!=", "Rejected"]},
			"name",
		)
		return existing
