"""Parse diverse date formats into ISO 8601 (YYYY-MM-DD)."""

import re
from datetime import datetime

from invoice_automation.extraction.schema import ExtractionWarning

DATE_FORMATS = [
	"%Y-%m-%d",       # 2024-01-15
	"%d/%m/%Y",       # 15/01/2024
	"%d-%m-%Y",       # 15-01-2024
	"%d.%m.%Y",       # 15.01.2024
	"%m/%d/%Y",       # 01/15/2024
	"%d %b %Y",       # 15 Jan 2024
	"%d %B %Y",       # 15 January 2024
	"%d-%b-%Y",       # 15-Jan-2024
	"%d-%B-%Y",       # 15-January-2024
	"%B %d, %Y",      # January 15, 2024
	"%b %d, %Y",      # Jan 15, 2024
	"%Y/%m/%d",       # 2024/01/15
	"%d %b, %Y",      # 15 Jan, 2024
]


def normalize_date(raw: str | None) -> tuple[str | None, ExtractionWarning | None]:
	"""Parse a date string into ISO 8601 format.

	Returns (normalized_date, warning_or_none).
	"""
	if not raw:
		return None, None

	cleaned = raw.strip()
	# Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
	cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned)

	# Try each format
	for fmt in DATE_FORMATS:
		try:
			dt = datetime.strptime(cleaned, fmt)
			return dt.strftime("%Y-%m-%d"), None
		except ValueError:
			continue

	# Check for ambiguous dates like 03/04/2024 (could be Mar 4 or Apr 3)
	match = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", cleaned)
	if match:
		a, b, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
		if a <= 12 and b <= 12 and a != b:
			# Ambiguous — assume DD/MM/YYYY (Indian convention)
			try:
				dt = datetime(year, b, a)
				warning = ExtractionWarning(
					category="ambiguous_date",
					message=f"Date '{raw}' is ambiguous. Interpreted as DD/MM/YYYY → {dt.strftime('%Y-%m-%d')}",
					severity="warning",
					field_path=None,
					raw_evidence=raw,
				)
				return dt.strftime("%Y-%m-%d"), warning
			except ValueError:
				pass

	return raw, ExtractionWarning(
		category="ambiguous_date",
		message=f"Could not parse date: '{raw}'",
		severity="warning",
		raw_evidence=raw,
	)
