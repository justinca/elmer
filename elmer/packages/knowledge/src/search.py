"""Search — query the knowledge base for relevant documents."""

from typing import Any


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_documents(
    query_embedding: list[float],
    document_embeddings: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Find the most similar documents to a query embedding.

    Args:
        query_embedding: The query vector.
        document_embeddings: List of dicts with 'embedding' and 'content' keys.
        top_k: Number of results to return.

    Returns:
        Top-k most similar documents sorted by similarity.
    """
    scored = []
    for doc in document_embeddings:
        score = cosine_similarity(query_embedding, doc["embedding"])
        scored.append({**doc, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
