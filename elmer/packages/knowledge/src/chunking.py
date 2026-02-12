"""Intelligent document chunking — type-aware splitting for the knowledge base."""

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger("elmer.knowledge.chunking")

# --- Content type detection ---

_EXTENSION_MAP: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".log": "text/x-log",
    ".yaml": "text/x-config",
    ".yml": "text/x-config",
    ".json": "text/x-config",
    ".toml": "text/x-config",
    ".conf": "text/x-config",
    ".ini": "text/x-config",
    ".cfg": "text/x-config",
    ".env": "text/x-config",
    ".py": "text/x-code",
    ".js": "text/x-code",
    ".ts": "text/x-code",
    ".sh": "text/x-code",
    ".bash": "text/x-code",
    ".bat": "text/x-code",
    ".ps1": "text/x-code",
    ".sql": "text/x-code",
    ".html": "text/plain",
    ".xml": "text/plain",
    ".rst": "text/plain",
}


@dataclass
class ChunkInfo:
    """A single chunk of a document with position and context metadata."""

    text: str
    index: int
    start_line: int | None = None
    end_line: int | None = None
    section: str | None = None
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def detect_content_type(file_path: str | Path) -> str:
    """Detect content type from file extension."""
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_MAP.get(ext, "text/plain")


def chunk_document(
    text: str,
    content_type: str,
    source_path: str | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[ChunkInfo]:
    """Chunk a document using the appropriate strategy for its content type.

    Args:
        text: The full document text.
        content_type: MIME-like type (e.g. "text/markdown").
        source_path: Original file path for metadata.
        chunk_size: Max characters per chunk (default from config).
        overlap: Overlap characters between chunks (default from config).

    Returns:
        List of ChunkInfo objects.
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP

    if not text or not text.strip():
        return []

    dispatcher = {
        "text/markdown": _chunk_markdown,
        "text/plain": _chunk_plaintext,
        "text/csv": _chunk_csv,
        "text/x-log": _chunk_log,
        "text/x-config": _chunk_config,
        "text/x-code": _chunk_code,
    }

    chunker = dispatcher.get(content_type, _chunk_plaintext)
    try:
        chunks = chunker(text, source_path, chunk_size, overlap)
    except Exception:
        logger.warning(
            "Chunker for %s failed on %s, falling back to plaintext",
            content_type, source_path,
        )
        chunks = _chunk_plaintext(text, source_path, chunk_size, overlap)

    # Re-index to ensure consecutive numbering.
    for i, chunk in enumerate(chunks):
        chunk.index = i
        chunk.source_path = source_path

    return chunks


# --- Markdown chunking ---


def _chunk_markdown(
    text: str, source_path: str | None, chunk_size: int, overlap: int,
) -> list[ChunkInfo]:
    """Chunk markdown by header boundaries, prepending heading context."""
    header_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    chunks: list[ChunkInfo] = []
    lines = text.split("\n")

    # Build sections: list of (heading, level, start_line, body)
    sections: list[tuple[str, int, int, str]] = []
    last_pos = 0
    last_heading = ""
    last_level = 0
    last_start = 1

    for match in header_re.finditer(text):
        # Capture everything before this header as the previous section body.
        body = text[last_pos:match.start()].strip()
        if body or last_heading:
            sections.append((last_heading, last_level, last_start, body))
        last_heading = match.group(2).strip()
        last_level = len(match.group(1))
        last_pos = match.end()
        last_start = text[:match.start()].count("\n") + 1

    # Final section.
    trailing = text[last_pos:].strip()
    if trailing or last_heading:
        sections.append((last_heading, last_level, last_start, trailing))

    # If no headers found, fall back to plaintext chunking.
    if not sections or (len(sections) == 1 and not sections[0][0]):
        return _chunk_plaintext(text, source_path, chunk_size, overlap)

    # Track parent headings for context.
    parent_h1 = ""
    parent_h2 = ""

    for heading, level, start_line, body in sections:
        if level == 1:
            parent_h1 = heading
            parent_h2 = ""
        elif level == 2:
            parent_h2 = heading

        # Build context prefix.
        context_parts = []
        if level >= 2 and parent_h1:
            context_parts.append(f"# {parent_h1}")
        if level >= 3 and parent_h2:
            context_parts.append(f"## {parent_h2}")
        if heading:
            context_parts.append(f"{'#' * level} {heading}")
        context_prefix = "\n".join(context_parts)

        # If section fits in one chunk, emit it.
        full_text = f"{context_prefix}\n\n{body}".strip() if body else context_prefix
        if len(full_text) <= chunk_size:
            if full_text:
                chunks.append(ChunkInfo(
                    text=full_text,
                    index=0,
                    start_line=start_line,
                    section=heading or None,
                ))
        else:
            # Sub-chunk the body by paragraphs.
            sub_chunks = _split_by_paragraphs(body, chunk_size - len(context_prefix) - 4, overlap)
            for sc_text in sub_chunks:
                chunk_text = f"{context_prefix}\n\n{sc_text}".strip()
                chunks.append(ChunkInfo(
                    text=chunk_text,
                    index=0,
                    start_line=start_line,
                    section=heading or None,
                ))

    return chunks


# --- Plaintext chunking ---


def _chunk_plaintext(
    text: str, source_path: str | None, chunk_size: int, overlap: int,
) -> list[ChunkInfo]:
    """Chunk plain text by paragraph boundaries with overlap."""
    if len(text) <= chunk_size:
        return [ChunkInfo(text=text.strip(), index=0, start_line=1)]

    paragraphs = _split_by_paragraphs(text, chunk_size, overlap)
    chunks: list[ChunkInfo] = []
    line_offset = 1

    for para_text in paragraphs:
        chunks.append(ChunkInfo(
            text=para_text,
            index=0,
            start_line=line_offset,
        ))
        line_offset += para_text.count("\n") + 1

    return chunks


def _split_by_paragraphs(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into chunks at paragraph boundaries with overlap."""
    paragraphs = re.split(r"\n\n+", text.strip())
    result: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                result.append(current)
            # If the paragraph itself exceeds chunk_size, split by sentences.
            if len(para) > chunk_size:
                sentence_chunks = _split_by_sentences(para, chunk_size, overlap)
                result.extend(sentence_chunks)
                current = ""
            else:
                # Start overlap from tail of the previous chunk.
                if result and overlap > 0:
                    tail = result[-1][-overlap:]
                    current = f"{tail} {para}".strip()
                else:
                    current = para

    if current.strip():
        result.append(current.strip())

    return result


def _split_by_sentences(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text at sentence boundaries as a last resort."""
    sentence_re = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_re.split(text)
    result: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                result.append(current)
            current = sentence

    if current.strip():
        result.append(current.strip())

    return result


# --- Config file chunking ---


def _chunk_config(
    text: str, source_path: str | None, chunk_size: int, overlap: int,
) -> list[ChunkInfo]:
    """Chunk config files by sections/keys."""
    ext = Path(source_path).suffix.lower() if source_path else ""

    if ext == ".json":
        return _chunk_json(text, source_path, chunk_size)
    if ext in (".ini", ".conf", ".cfg"):
        return _chunk_ini(text, source_path, chunk_size)
    if ext in (".yaml", ".yml"):
        return _chunk_yaml(text, source_path, chunk_size)
    if ext == ".toml":
        return _chunk_ini(text, source_path, chunk_size)  # TOML sections are INI-like
    if ext == ".env":
        return _chunk_plaintext(text, source_path, chunk_size, overlap)

    return _chunk_plaintext(text, source_path, chunk_size, overlap)


def _chunk_json(text: str, source_path: str | None, chunk_size: int) -> list[ChunkInfo]:
    """Chunk JSON by top-level keys."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [ChunkInfo(text=text.strip(), index=0, start_line=1)]

    if isinstance(data, dict):
        chunks: list[ChunkInfo] = []
        for key, value in data.items():
            fragment = json.dumps({key: value}, indent=2, default=str)
            if len(fragment) <= chunk_size:
                chunks.append(ChunkInfo(text=fragment, index=0, section=key))
            else:
                # Large value — sub-chunk as plaintext.
                for sub in _split_by_paragraphs(fragment, chunk_size, 0):
                    chunks.append(ChunkInfo(text=sub, index=0, section=key))
        return chunks if chunks else [ChunkInfo(text=text.strip(), index=0)]

    # Array or scalar — treat as plaintext.
    return _chunk_plaintext(text, source_path, chunk_size, 0)


def _chunk_ini(text: str, source_path: str | None, chunk_size: int) -> list[ChunkInfo]:
    """Chunk INI/TOML-style files by [section] headers."""
    section_re = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)
    sections: list[tuple[str, str]] = []
    positions = [(m.start(), m.group(1)) for m in section_re.finditer(text)]

    if not positions:
        return [ChunkInfo(text=text.strip(), index=0, start_line=1)]

    # Content before first section.
    preamble = text[:positions[0][0]].strip()
    if preamble:
        sections.append(("preamble", preamble))

    for i, (pos, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        body = text[pos:end].strip()
        sections.append((name, body))

    chunks: list[ChunkInfo] = []
    for name, body in sections:
        if len(body) <= chunk_size:
            chunks.append(ChunkInfo(text=body, index=0, section=name))
        else:
            for sub in _split_by_paragraphs(body, chunk_size, 0):
                chunks.append(ChunkInfo(text=sub, index=0, section=name))

    return chunks


def _chunk_yaml(text: str, source_path: str | None, chunk_size: int) -> list[ChunkInfo]:
    """Chunk YAML by top-level keys (regex-based, no PyYAML dependency)."""
    key_re = re.compile(r"^(\S[^:\s]*):\s*", re.MULTILINE)
    positions = [(m.start(), m.group(1)) for m in key_re.finditer(text)]

    if not positions:
        return [ChunkInfo(text=text.strip(), index=0, start_line=1)]

    chunks: list[ChunkInfo] = []
    for i, (pos, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        body = text[pos:end].strip()
        start_line = text[:pos].count("\n") + 1
        if len(body) <= chunk_size:
            chunks.append(ChunkInfo(text=body, index=0, start_line=start_line, section=key))
        else:
            for sub in _split_by_paragraphs(body, chunk_size, 0):
                chunks.append(ChunkInfo(text=sub, index=0, start_line=start_line, section=key))

    return chunks


# --- CSV chunking ---


def _chunk_csv(
    text: str, source_path: str | None, chunk_size: int, overlap: int,
) -> list[ChunkInfo]:
    """Chunk CSV by converting rows to natural language summaries."""
    try:
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
    except csv.Error:
        return _chunk_plaintext(text, source_path, chunk_size, overlap)

    if len(rows) < 2:
        return [ChunkInfo(text=text.strip(), index=0, start_line=1)]

    headers = rows[0]
    chunks: list[ChunkInfo] = []
    current_lines: list[str] = []
    current_len = 0
    row_start = 2  # 1-indexed, skip header

    for row_idx, row in enumerate(rows[1:], start=2):
        # Convert row to natural language.
        parts = [f"{h}: {v}" for h, v in zip(headers, row) if v.strip()]
        line = "; ".join(parts)
        candidate_len = current_len + len(line) + 1

        if candidate_len > chunk_size and current_lines:
            chunk_text = "\n".join(current_lines)
            chunks.append(ChunkInfo(
                text=chunk_text,
                index=0,
                start_line=row_start,
                end_line=row_idx - 1,
                metadata={"headers": headers, "row_start": row_start, "row_end": row_idx - 1},
            ))
            current_lines = []
            current_len = 0
            row_start = row_idx

        current_lines.append(line)
        current_len += len(line) + 1

    if current_lines:
        chunk_text = "\n".join(current_lines)
        chunks.append(ChunkInfo(
            text=chunk_text,
            index=0,
            start_line=row_start,
            end_line=row_start + len(current_lines) - 1,
            metadata={"headers": headers, "row_start": row_start, "row_end": row_start + len(current_lines) - 1},
        ))

    return chunks


# --- Log file chunking ---


_MAX_LOG_LINES = 500


def _chunk_log(
    text: str, source_path: str | None, chunk_size: int, overlap: int,
) -> list[ChunkInfo]:
    """Chunk log files with smart truncation for large files."""
    lines = text.split("\n")
    truncated = False
    original_count = len(lines)

    if len(lines) > _MAX_LOG_LINES:
        # Keep first 20% and last 80%.
        head_count = _MAX_LOG_LINES // 5
        tail_count = _MAX_LOG_LINES - head_count
        head = lines[:head_count]
        tail = lines[-tail_count:]
        skipped = len(lines) - head_count - tail_count
        lines = head + [f"[... {skipped} lines truncated ...]"] + tail
        truncated = True

    sampled = "\n".join(lines)
    chunks = _chunk_plaintext(sampled, source_path, chunk_size, overlap)

    if truncated:
        for chunk in chunks:
            chunk.metadata["truncated"] = True
            chunk.metadata["original_lines"] = original_count

    return chunks


# --- Code chunking ---


def _chunk_code(
    text: str, source_path: str | None, chunk_size: int, overlap: int,
) -> list[ChunkInfo]:
    """Chunk code by function/class boundaries."""
    # Python-style: split on top-level def/class/async def.
    boundary_re = re.compile(r"^(?=(?:class |def |async def )\w)", re.MULTILINE)
    positions = [m.start() for m in boundary_re.finditer(text)]

    if not positions:
        return _chunk_plaintext(text, source_path, chunk_size, overlap)

    chunks: list[ChunkInfo] = []

    # Preamble (imports, module docstring, etc.)
    if positions[0] > 0:
        preamble = text[:positions[0]].strip()
        if preamble:
            chunks.append(ChunkInfo(
                text=preamble, index=0, start_line=1, section="preamble",
            ))

    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        block = text[pos:end].strip()
        start_line = text[:pos].count("\n") + 1

        # Extract function/class name.
        name_match = re.match(r"(?:async\s+)?(?:def|class)\s+(\w+)", block)
        section_name = name_match.group(1) if name_match else None

        if len(block) <= chunk_size:
            chunks.append(ChunkInfo(
                text=block, index=0, start_line=start_line, section=section_name,
            ))
        else:
            # Sub-split large functions by blank lines.
            for sub in _split_by_paragraphs(block, chunk_size, overlap):
                chunks.append(ChunkInfo(
                    text=sub, index=0, start_line=start_line, section=section_name,
                ))

    return chunks
