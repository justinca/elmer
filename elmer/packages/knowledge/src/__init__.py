"""Elmer Knowledge — RAG pipeline, document ingestion, and unified search."""

from .chunking import ChunkInfo, chunk_document, detect_content_type
from .embeddings import EmbeddingService
from .ingest import DocumentIngestor, IngestResult, SourceInfo
from .obsidian_sync import ObsidianSync, SyncResult
from .search import SearchResult, UnifiedSearch
from .vector_store import VectorStore

__all__ = [
    "ChunkInfo",
    "chunk_document",
    "detect_content_type",
    "DocumentIngestor",
    "EmbeddingService",
    "IngestResult",
    "ObsidianSync",
    "SearchResult",
    "SourceInfo",
    "SyncResult",
    "UnifiedSearch",
    "VectorStore",
]
