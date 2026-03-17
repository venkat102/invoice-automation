"""Abstract vector index interface + NumPy implementation."""

import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import frappe


@dataclass
class SearchResult:
	source_doctype: str
	source_name: str
	score: float
	metadata: dict = field(default_factory=dict)


class VectorIndexBase(ABC):
	"""Abstract interface for vector search. Swap to Qdrant later."""

	@abstractmethod
	def search(self, query_embedding, filters=None, top_k=10) -> list[SearchResult]:
		...

	@abstractmethod
	def upsert(self, source_doctype, source_name, embedding, metadata=None):
		...

	@abstractmethod
	def remove(self, source_doctype, source_name):
		...

	@abstractmethod
	def rebuild(self):
		...


class NumpyVectorIndex(VectorIndexBase):
	"""In-memory NumPy-based vector index backed by the Embedding Index doctype."""

	def __init__(self):
		self._embeddings = None  # np.ndarray (N, D)
		self._metadata = []  # list of dicts
		self._lock = threading.Lock()
		self._loaded = False

	def _ensure_loaded(self):
		if not self._loaded:
			self._load_index()

	def _load_index(self):
		"""Load all embeddings from the Embedding Index doctype into memory."""
		with self._lock:
			records = frappe.get_all(
				"Embedding Index",
				fields=[
					"name", "source_doctype", "source_name", "composite_text",
					"embedding_vector", "supplier_context", "is_human_corrected",
					"item_group", "hsn_code",
				],
				limit=0,
			)

			if not records:
				self._embeddings = np.zeros((0, 384), dtype=np.float32)
				self._metadata = []
				self._loaded = True
				return

			embeddings_list = []
			metadata_list = []

			for rec in records:
				try:
					vec = json.loads(rec.embedding_vector)
					embeddings_list.append(np.array(vec, dtype=np.float32))
					metadata_list.append({
						"name": rec.name,
						"source_doctype": rec.source_doctype,
						"source_name": rec.source_name,
						"composite_text": rec.composite_text,
						"supplier_context": rec.supplier_context,
						"is_human_corrected": rec.is_human_corrected,
						"item_group": rec.item_group,
						"hsn_code": rec.hsn_code,
					})
				except (json.JSONDecodeError, TypeError):
					continue

			if embeddings_list:
				self._embeddings = np.vstack(embeddings_list)
			else:
				self._embeddings = np.zeros((0, 384), dtype=np.float32)

			self._metadata = metadata_list
			self._loaded = True

	def search(self, query_embedding, filters=None, top_k=10) -> list[SearchResult]:
		"""Cosine similarity search. Embeddings are assumed normalized."""
		self._ensure_loaded()

		if self._embeddings.shape[0] == 0:
			return []

		query = np.array(query_embedding, dtype=np.float32)
		if query.ndim == 1:
			query = query.reshape(1, -1)

		# Cosine similarity (dot product since embeddings are normalized)
		similarities = (self._embeddings @ query.T).flatten()

		# Apply filters
		mask = np.ones(len(self._metadata), dtype=bool)
		if filters:
			for key, value in filters.items():
				for i, meta in enumerate(self._metadata):
					if meta.get(key) != value:
						mask[i] = False

		# Zero out filtered entries
		similarities = similarities * mask

		# Get top_k indices
		top_indices = np.argsort(similarities)[::-1][:top_k]

		results = []
		for idx in top_indices:
			if similarities[idx] <= 0:
				break
			meta = self._metadata[idx]
			results.append(SearchResult(
				source_doctype=meta["source_doctype"],
				source_name=meta["source_name"],
				score=float(similarities[idx]),
				metadata=meta,
			))

		return results

	def upsert(self, source_doctype, source_name, embedding, metadata=None):
		"""Update both the Embedding Index doctype and the in-memory matrix."""
		from invoice_automation.embeddings.model import embedding_to_list

		metadata = metadata or {}
		embedding_list = embedding_to_list(embedding)

		# Upsert in database
		existing = frappe.db.get_value(
			"Embedding Index",
			{"source_doctype": source_doctype, "source_name": source_name},
			"name",
		)

		if existing:
			frappe.db.set_value("Embedding Index", existing, {
				"embedding_vector": json.dumps(embedding_list),
				"composite_text": metadata.get("composite_text", ""),
				"supplier_context": metadata.get("supplier_context"),
				"is_human_corrected": metadata.get("is_human_corrected", 0),
				"item_group": metadata.get("item_group"),
				"hsn_code": metadata.get("hsn_code"),
				"last_updated": frappe.utils.now_datetime(),
			})
		else:
			doc = frappe.new_doc("Embedding Index")
			doc.source_doctype = source_doctype
			doc.source_name = source_name
			doc.embedding_vector = json.dumps(embedding_list)
			doc.composite_text = metadata.get("composite_text", "")
			doc.supplier_context = metadata.get("supplier_context")
			doc.is_human_corrected = metadata.get("is_human_corrected", 0)
			doc.item_group = metadata.get("item_group")
			doc.hsn_code = metadata.get("hsn_code")
			doc.last_updated = frappe.utils.now_datetime()
			doc.insert(ignore_permissions=True)

		# Update in-memory index
		with self._lock:
			if self._loaded:
				vec = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
				meta_entry = {
					"source_doctype": source_doctype,
					"source_name": source_name,
					"composite_text": metadata.get("composite_text", ""),
					"supplier_context": metadata.get("supplier_context"),
					"is_human_corrected": metadata.get("is_human_corrected", 0),
					"item_group": metadata.get("item_group"),
					"hsn_code": metadata.get("hsn_code"),
				}

				# Check if already exists in memory
				for i, m in enumerate(self._metadata):
					if m["source_doctype"] == source_doctype and m["source_name"] == source_name:
						self._embeddings[i] = vec.flatten()
						self._metadata[i] = meta_entry
						return

				# Append new
				if self._embeddings.shape[0] == 0:
					self._embeddings = vec
				else:
					self._embeddings = np.vstack([self._embeddings, vec])
				self._metadata.append(meta_entry)

	def remove(self, source_doctype, source_name):
		"""Remove from both doctype and in-memory matrix."""
		# Remove from DB
		existing = frappe.db.get_value(
			"Embedding Index",
			{"source_doctype": source_doctype, "source_name": source_name},
			"name",
		)
		if existing:
			frappe.delete_doc("Embedding Index", existing, ignore_permissions=True)

		# Remove from memory
		with self._lock:
			if self._loaded:
				for i, m in enumerate(self._metadata):
					if m["source_doctype"] == source_doctype and m["source_name"] == source_name:
						self._embeddings = np.delete(self._embeddings, i, axis=0)
						self._metadata.pop(i)
						break

	def rebuild(self):
		"""Force reload from database."""
		self._loaded = False
		self._load_index()


# Singleton instance
_index_manager = None


def get_index_manager() -> NumpyVectorIndex:
	"""Return a singleton NumpyVectorIndex instance."""
	global _index_manager
	if _index_manager is None:
		_index_manager = NumpyVectorIndex()
	return _index_manager
