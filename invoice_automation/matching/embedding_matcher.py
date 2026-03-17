"""Stage 4: Semantic embedding search for invoice matching."""

import frappe

from invoice_automation.matching.confidence import get_config
from invoice_automation.matching.exact_matcher import MatchResult


class EmbeddingMatcher:
	"""Semantic embedding-based matching using vector similarity search."""

	def match(
		self,
		raw_text: str,
		source_doctype: str,
		supplier: str | None = None,
	) -> MatchResult:
		"""Match raw_text using embedding similarity search.

		Confidence is on 0-100 percentage scale:
		  similarity >= threshold → 80-92%
		  similarity >= review_threshold → 65-79%
		  below → no match
		"""
		if not raw_text:
			return MatchResult(matched=False, doctype=source_doctype, stage="Embedding")

		config = get_config()
		similarity_threshold = config.get("embedding_similarity_threshold", 0.85)
		review_threshold = config.get("embedding_review_threshold", 0.65)
		agreement_boost = config.get("agreement_confidence_boost", 10)
		correction_weight = config.get("human_correction_weight_boost", 1.1)

		try:
			from invoice_automation.embeddings.model import generate_embedding
			from invoice_automation.embeddings.index_manager import get_index_manager

			index_manager = get_index_manager()
		except Exception as e:
			return MatchResult(
				matched=False, doctype=source_doctype, stage="Embedding",
				details={"error": f"Could not load embedding system: {e}"},
			)

		try:
			query_embedding = generate_embedding(raw_text)

			# Search 1: Historical invoice index (supplier-filtered first, then broad)
			historical_results = []
			if supplier:
				historical_results = index_manager.search(
					query_embedding,
					filters={"source_doctype": "Historical Invoice Line", "supplier_context": supplier},
					top_k=1,
				)
			if not historical_results:
				historical_results = index_manager.search(
					query_embedding,
					filters={"source_doctype": "Historical Invoice Line"},
					top_k=1,
				)

			hist_score = historical_results[0].score if historical_results else 0.0
			hist_match = historical_results[0].source_name if historical_results else None
			hist_corrected = (
				historical_results[0].metadata.get("is_human_corrected", False)
				if historical_results
				else False
			)

			# Search 2: Item master index
			master_results = index_manager.search(
				query_embedding,
				filters={"source_doctype": "Item"},
				top_k=1,
			)

			master_score = master_results[0].score if master_results else 0.0
			master_match = master_results[0].source_name if master_results else None

			# Pick best
			if hist_score >= master_score:
				best_score = hist_score
				best_match = hist_match
			else:
				best_score = master_score
				best_match = master_match

			# Apply human correction weight boost
			if hist_corrected and hist_match == best_match:
				best_score = min(best_score * correction_weight, 1.0)

			# Agreement boost: both indexes point to same item
			agreement = hist_match and master_match and hist_match == master_match
			bonus = 0.0
			if agreement:
				bonus = agreement_boost  # Will be added to confidence, not similarity

			# Map similarity to confidence percentage
			if best_score >= similarity_threshold:
				# 0.85-1.0 → confidence 80-92
				confidence = 80 + (best_score - similarity_threshold) / (1.0 - similarity_threshold) * 12
				confidence += bonus
				confidence = min(confidence, 92)
				return MatchResult(
					matched=True, doctype=source_doctype, matched_name=best_match,
					confidence=round(confidence, 1), stage="Embedding",
					details={
						"similarity": round(best_score, 4),
						"historical_score": round(hist_score, 4),
						"master_score": round(master_score, 4),
						"agreement": agreement,
						"human_corrected": hist_corrected,
						"raw_text": raw_text,
					},
				)
			elif best_score >= review_threshold:
				# 0.65-0.84 → confidence 65-79
				confidence = 65 + (best_score - review_threshold) / (similarity_threshold - review_threshold) * 14
				confidence += bonus
				confidence = min(confidence, 79)
				return MatchResult(
					matched=True, doctype=source_doctype, matched_name=best_match,
					confidence=round(confidence, 1), stage="Embedding",
					details={
						"similarity": round(best_score, 4),
						"agreement": agreement,
						"raw_text": raw_text,
					},
				)
			else:
				return MatchResult(
					matched=False, doctype=source_doctype, stage="Embedding",
					details={"best_similarity": round(best_score, 4), "raw_text": raw_text},
				)

		except Exception as e:
			return MatchResult(
				matched=False, doctype=source_doctype, stage="Embedding",
				details={"error": str(e)},
			)
