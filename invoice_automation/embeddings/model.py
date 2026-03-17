"""Embedding model loader and inference. Lazy-loads only in worker processes."""

import numpy as np
import frappe


_model = None
_model_name = None


def get_model():
	"""Lazy-load the sentence-transformer model. Only call from worker processes."""
	global _model, _model_name

	try:
		model_name = frappe.db.get_single_value("Invoice Automation Settings", "embedding_model_name")
	except Exception:
		model_name = None
	model_name = model_name or "sentence-transformers/all-MiniLM-L6-v2"

	if _model is None or _model_name != model_name:
		from sentence_transformers import SentenceTransformer

		_model = SentenceTransformer(model_name)
		_model_name = model_name

	return _model


def generate_embedding(text: str) -> np.ndarray:
	"""Generate embedding vector for a text string."""
	model = get_model()
	embedding = model.encode(text, normalize_embeddings=True)
	return np.array(embedding, dtype=np.float32)


def generate_embeddings_batch(texts: list[str]) -> np.ndarray:
	"""Generate embeddings for a batch of texts."""
	model = get_model()
	embeddings = model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
	return np.array(embeddings, dtype=np.float32)


def embedding_to_list(embedding: np.ndarray) -> list[float]:
	"""Convert numpy embedding to JSON-serializable list."""
	return embedding.tolist()


def list_to_embedding(lst: list[float]) -> np.ndarray:
	"""Convert JSON list back to numpy array."""
	return np.array(lst, dtype=np.float32)
