"""Auto-repair malformed JSON output from LLMs."""

import json
import re


def repair_json(raw: str) -> dict | None:
	"""Attempt to repair common JSON issues from LLM output.

	Returns parsed dict on success, None if unrecoverable.
	"""
	if not raw or not raw.strip():
		return None

	text = raw.strip()

	# Strip markdown code fences
	text = _strip_markdown_fences(text)

	# Try direct parse first
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		pass

	# Apply repairs in sequence
	repairs = [
		_fix_trailing_commas,
		_fix_single_quotes,
		_fix_unquoted_keys,
		_fix_truncated_json,
		_extract_json_object,
	]

	for repair_fn in repairs:
		try:
			fixed = repair_fn(text)
			if fixed and fixed != text:
				result = json.loads(fixed)
				return result
		except (json.JSONDecodeError, Exception):
			continue

	return None


def _strip_markdown_fences(text: str) -> str:
	"""Remove ```json ... ``` wrappers."""
	if text.startswith("```"):
		lines = text.split("\n")
		# Remove first line (```json) and last line (```)
		start = 1
		end = len(lines)
		if lines[-1].strip() == "```":
			end = -1
		text = "\n".join(lines[start:end])
	return text.strip()


def _fix_trailing_commas(text: str) -> str:
	"""Remove trailing commas before } or ]."""
	return re.sub(r",\s*([}\]])", r"\1", text)


def _fix_single_quotes(text: str) -> str:
	"""Replace single quotes with double quotes (naive)."""
	return text.replace("'", '"')


def _fix_unquoted_keys(text: str) -> str:
	"""Quote unquoted JSON keys."""
	return re.sub(r'(?<={|,)\s*(\w+)\s*:', r' "\1":', text)


def _fix_truncated_json(text: str) -> str:
	"""Try to close unclosed braces/brackets."""
	open_braces = text.count("{") - text.count("}")
	open_brackets = text.count("[") - text.count("]")

	if open_braces <= 0 and open_brackets <= 0:
		return text

	# Remove trailing incomplete key-value pair
	text = re.sub(r',\s*"[^"]*"\s*:\s*$', "", text)
	text = re.sub(r',\s*$', "", text)

	# Close remaining open structures
	text += "]" * max(0, open_brackets)
	text += "}" * max(0, open_braces)

	return text


def _extract_json_object(text: str) -> str:
	"""Extract the first complete JSON object from text."""
	# Find the first { and try to find its matching }
	start = text.find("{")
	if start == -1:
		return text

	depth = 0
	in_string = False
	escape = False

	for i in range(start, len(text)):
		c = text[i]
		if escape:
			escape = False
			continue
		if c == "\\":
			escape = True
			continue
		if c == '"' and not escape:
			in_string = not in_string
			continue
		if in_string:
			continue
		if c == "{":
			depth += 1
		elif c == "}":
			depth -= 1
			if depth == 0:
				return text[start:i + 1]

	# If we didn't find a complete object, return with closing braces
	return text[start:] + "}" * depth
