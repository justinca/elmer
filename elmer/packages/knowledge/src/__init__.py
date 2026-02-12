"""Elmer Knowledge — RAG pipeline and document ingestion."""

from .embeddings import EmbeddingService
from .obsidian_sync import ObsidianSync, SyncResult
from .vector_store import VectorStore

__all__ = ["EmbeddingService", "VectorStore", "ObsidianSync", "SyncResult"]
