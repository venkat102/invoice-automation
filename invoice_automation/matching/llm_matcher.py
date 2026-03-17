"""Stage 5: LLM fallback for invoice matching. Provider-agnostic."""

import json

from invoice_automation.matching.confidence import get_config
from invoice_automation.matching.exact_matcher import MatchResult


class LLMMatcher:
	"""LLM-based matching using the configured provider as a final fallback."""

	def match(
		self,
		raw_text: str,
		source_doctype: str,
		supplier: str | None,
		candidates: list,
		corrections_context: list,
	) -> MatchResult:
		"""Use the configured LLM provider to match raw_text against candidates.

		Confidence is capped at 88% — LLM matches should still be reviewed.
		"""
		config = get_config()

		if not config.get("enable_llm_matching", False):
			return MatchResult(
				matched=False, doctype=source_doctype, stage="LLM",
				details={"reason": "LLM matching disabled"},
			)

		if not raw_text or not candidates:
			return MatchResult(
				matched=False, doctype=source_doctype, stage="LLM",
				details={"reason": "Missing raw_text or candidates"},
			)

		try:
			from invoice_automation.llm import get_llm_provider

			provider = get_llm_provider("matching")
			prompt = self._build_prompt(raw_text, supplier, candidates, corrections_context)
			response_text = provider.generate(prompt)

			return self._parse_response(response_text, source_doctype)

		except Exception as e:
			return MatchResult(
				matched=False, doctype=source_doctype, stage="LLM",
				details={"error": str(e)},
			)

	def _build_prompt(self, raw_text, supplier, candidates, corrections_context):
		candidates_numbered = "\n".join(
			f"{i + 1}. {c}" for i, c in enumerate(candidates)
		)

		corrections_str = ""
		if corrections_context:
			lines = []
			for c in corrections_context:
				line = f'  - "{c.get("raw_extracted_text", "")}" was corrected to {c.get("human_selected", "")}'
				if c.get("reviewer_reasoning"):
					line += f'\n    Reviewer note: "{c["reviewer_reasoning"]}"'
				lines.append(line)
			corrections_str = (
				"\n\nHere are relevant past corrections made by reviewers for this supplier:\n"
				+ "\n".join(lines)
			)

		supplier_line = f"\nSupplier: {supplier}" if supplier else ""

		return f"""You are helping match an invoice line item to the correct ERPNext Item master record.
{supplier_line}
Extracted line item: "{raw_text}"

Here are the top candidate items from our system:
{candidates_numbered}
{corrections_str}

Based on the extracted text, candidates, and past correction patterns, which Item is the best match?
If none are a good match, respond with "NO_MATCH".

Respond with ONLY a JSON object (no markdown, no code blocks):
{{"matched_item": "exact candidate name or NO_MATCH", "confidence": 0-100, "reasoning": "brief explanation"}}"""

	def _parse_response(self, response_text: str, source_doctype: str) -> MatchResult:
		try:
			text = response_text.strip()
			if text.startswith("```"):
				lines = text.split("\n")
				text = "\n".join(lines[1:-1])

			result = json.loads(text)
			matched_item = result.get("matched_item")
			raw_confidence = result.get("confidence", 0)
			reasoning = result.get("reasoning", "")

			if not matched_item or matched_item == "NO_MATCH":
				return MatchResult(
					matched=False, doctype=source_doctype, stage="LLM",
					details={"reasoning": reasoning},
				)

			# Cap at 88% — LLM matches should still be reviewed
			confidence = min(float(raw_confidence), 88.0)

			return MatchResult(
				matched=True, doctype=source_doctype, matched_name=matched_item,
				confidence=round(confidence, 1), stage="LLM",
				details={"reasoning": reasoning, "raw_confidence": raw_confidence},
			)

		except (json.JSONDecodeError, KeyError, TypeError) as e:
			return MatchResult(
				matched=False, doctype=source_doctype, stage="LLM",
				details={"error": f"Failed to parse LLM response: {e}"},
			)
