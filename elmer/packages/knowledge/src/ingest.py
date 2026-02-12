"""Document ingestion — reads and chunks documents for the knowledge base."""

from pathlib import Path


def read_markdown_files(vault_path: str | Path) -> list[dict[str, str]]:
    """Read all markdown files from a directory (e.g., Obsidian vault).

    Returns a list of dicts with 'path' and 'content' keys.
    """
    vault = Path(vault_path)
    documents = []
    for md_file in vault.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8", errors="replace")
        documents.append({"path": str(md_file), "content": content})
    return documents


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks.

    Args:
        text: The text to chunk.
        chunk_size: Maximum characters per chunk.
        overlap: Number of overlapping characters between chunks.

    Returns:
        A list of text chunks.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks
