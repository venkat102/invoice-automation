"""File handling utilities: hashing, MIME detection, validation."""

import hashlib
import mimetypes
from pathlib import Path

from invoice_automation.utils.exceptions import FileValidationError


EXTENSION_TO_FILE_TYPE = {
	".pdf": "PDF",
	".png": "Image",
	".jpg": "Image",
	".jpeg": "Image",
	".tiff": "Image",
	".tif": "Image",
	".webp": "Image",
	".docx": "DOCX",
	".doc": "DOC",
}


def compute_sha256(file_path: str) -> str:
	"""Compute SHA-256 hash of a file."""
	h = hashlib.sha256()
	with open(file_path, "rb") as f:
		for chunk in iter(lambda: f.read(8192), b""):
			h.update(chunk)
	return h.hexdigest()


def detect_mime_type(file_path: str) -> str:
	"""Detect MIME type using mimetypes module."""
	mime, _ = mimetypes.guess_type(file_path)
	return mime or "application/octet-stream"


def detect_file_type(file_path: str) -> str:
	"""Map file extension to a file type category."""
	ext = Path(file_path).suffix.lower()
	return EXTENSION_TO_FILE_TYPE.get(ext, "Unknown")


def get_file_extension(file_path: str) -> str:
	"""Get lowercase file extension."""
	return Path(file_path).suffix.lower()


def validate_file(file_path: str, max_size_mb: int = 25, allowed_extensions: str = "") -> dict:
	"""Validate file size and extension.

	Returns dict with file_name, file_hash, file_type, file_size_bytes, extension.
	Raises FileValidationError on failure.
	"""
	path = Path(file_path)

	if not path.exists():
		raise FileValidationError(f"File not found: {file_path}")

	file_size = path.stat().st_size

	if file_size == 0:
		raise FileValidationError("File is empty (zero bytes)")

	if max_size_mb and file_size > max_size_mb * 1024 * 1024:
		raise FileValidationError(
			f"File size ({file_size / 1024 / 1024:.1f} MB) exceeds limit ({max_size_mb} MB)"
		)

	ext = path.suffix.lower().lstrip(".")
	if allowed_extensions:
		allowed = [e.strip().lower() for e in allowed_extensions.split(",")]
		if ext not in allowed:
			raise FileValidationError(
				f"File extension '.{ext}' not allowed. Allowed: {allowed_extensions}"
			)

	return {
		"file_name": path.name,
		"file_hash": compute_sha256(file_path),
		"file_type": detect_file_type(file_path),
		"file_size_bytes": file_size,
		"extension": ext,
		"mime_type": detect_mime_type(file_path),
	}
