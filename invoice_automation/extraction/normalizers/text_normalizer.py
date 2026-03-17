"""Text normalization: whitespace, unicode, control characters."""

import re
import unicodedata


def normalize_text(raw: str | None) -> str | None:
	"""Collapse whitespace, strip control characters, normalize unicode."""
	if not raw:
		return None

	# Normalize unicode
	text = unicodedata.normalize("NFKC", raw)

	# Remove control characters (except newlines and tabs)
	text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

	# Collapse multiple whitespace into single space
	text = re.sub(r"[ \t]+", " ", text)

	# Collapse multiple newlines into double newline
	text = re.sub(r"\n{3,}", "\n\n", text)

	return text.strip() or None
