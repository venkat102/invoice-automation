"""Fetches relevant past corrections + reasoning for LLM context."""

import json

import frappe


class ReasoningRetriever:
	"""Retrieves past corrections most relevant to a new matching decision."""

	def get_relevant_corrections(self, raw_text, supplier, source_doctype="Item", top_k=5):
		"""Get the most relevant past corrections for LLM context.

		First tries embedding similarity, falls back to recent corrections for the supplier.

		Returns list of dicts with: raw_extracted_text, system_proposed, human_selected,
		reviewer_reasoning, similarity_score.
		"""
		if not raw_text:
			return []

		# Try embedding-based similarity search
		try:
			result = self._get_by_embedding_similarity(raw_text, supplier, source_doctype, top_k)
			if result:
				return result
		except Exception:
			pass

		# Fallback: recent corrections for this supplier with reasoning
		return self._get_recent_corrections(supplier, source_doctype, top_k)

	def _get_by_embedding_similarity(self, raw_text, supplier, source_doctype, top_k):
		"""Find similar corrections using embedding distance."""
		from invoice_automation.embeddings.model import generate_embedding, list_to_embedding
		import numpy as np

		query_embedding = generate_embedding(raw_text)

		# Get corrections with embeddings
		filters = {
			"source_doctype": source_doctype,
			"reviewer_reasoning": ["is", "set"],
			"raw_text_embedding": ["is", "set"],
		}
		if supplier:
			filters["supplier"] = supplier

		corrections = frappe.get_all(
			"Mapping Correction Log",
			filters=filters,
			fields=[
				"name", "raw_extracted_text", "system_proposed",
				"human_selected", "reviewer_reasoning", "raw_text_embedding",
			],
			order_by="creation desc",
			limit=50,
		)

		if not corrections:
			return []

		# Compute cosine similarity
		scored = []
		for c in corrections:
			try:
				stored_embedding = list_to_embedding(json.loads(c.raw_text_embedding))
				similarity = float(np.dot(query_embedding, stored_embedding))
				scored.append({
					"raw_extracted_text": c.raw_extracted_text,
					"system_proposed": c.system_proposed,
					"human_selected": c.human_selected,
					"reviewer_reasoning": c.reviewer_reasoning,
					"similarity_score": round(similarity, 4),
				})
			except Exception:
				continue

		# Sort by similarity descending, return top_k
		scored.sort(key=lambda x: x["similarity_score"], reverse=True)
		return scored[:top_k]

	def _get_recent_corrections(self, supplier, source_doctype, top_k):
		"""Fallback: return recent corrections for the supplier."""
		filters = {
			"source_doctype": source_doctype,
			"reviewer_reasoning": ["is", "set"],
		}
		if supplier:
			filters["supplier"] = supplier

		corrections = frappe.get_all(
			"Mapping Correction Log",
			filters=filters,
			fields=[
				"raw_extracted_text", "system_proposed",
				"human_selected", "reviewer_reasoning",
			],
			order_by="creation desc",
			limit=top_k,
		)

		return [
			{
				"raw_extracted_text": c.raw_extracted_text,
				"system_proposed": c.system_proposed,
				"human_selected": c.human_selected,
				"reviewer_reasoning": c.reviewer_reasoning,
				"similarity_score": 0,
			}
			for c in corrections
		]
