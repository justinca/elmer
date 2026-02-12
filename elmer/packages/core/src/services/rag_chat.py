"""RAG chat engine — knowledge-augmented conversation with Ollama."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import settings
from . import db
from . import conversation as convo

logger = logging.getLogger("elmer.rag_chat")

SYSTEM_PROMPT = """\
You are Elmer, a knowledgeable AI assistant for W0ABE's home lab \
and amateur radio station. You have access to the operator's notes, \
documentation, transcripts, and system information.

Use the provided context to answer questions accurately. If the \
context doesn't contain relevant information, say so and answer \
from your general knowledge. Always cite your sources when using \
context.

Be concise, technical when appropriate, and helpful. You understand \
amateur radio, home automation, networking, Linux, and Docker.\
"""

EMBED_TIMEOUT = 60.0
CHAT_TIMEOUT = 120.0
# llama3.1:8b context window is ~8192 tokens; ~4 chars per token.
MAX_CONTEXT_CHARS = 24000
MAX_HISTORY_MESSAGES = 10
KNOWLEDGE_RESULT_LIMIT = 5
KNOWLEDGE_THRESHOLD = 0.3

# Simple concurrency limiter: only 1 chat at a time.
_chat_semaphore = asyncio.Semaphore(1)


@dataclass
class SourceCitation:
    """A knowledge source that was used as context."""

    source: str
    source_path: str | None = None
    score: float = 0.0
    snippet: str = ""


@dataclass
class ChatResponse:
    """Response from the RAG chat engine."""

    response: str
    conversation_id: int
    model: str
    sources_used: list[SourceCitation] = field(default_factory=list)
    error: str | None = None


async def chat(
    message: str,
    conversation_id: int | None = None,
    model: str = "llama3.1:8b",
    channel: str = "api",
) -> ChatResponse:
    """Process a chat message with RAG context augmentation.

    Steps:
      1. Create or load conversation
      2. Embed user message and search knowledge base
      3. Build augmented prompt (system + context + history + message)
      4. Send to Ollama via worker (with fallback)
      5. Store messages and return response with citations
    """
    async with _chat_semaphore:
        return await _chat_inner(message, conversation_id, model, channel)


async def _chat_inner(
    message: str,
    conversation_id: int | None,
    model: str,
    channel: str,
) -> ChatResponse:
    # 1. Create or load conversation.
    if conversation_id is None:
        conversation_id = await convo.create_conversation(channel=channel)
    else:
        existing = await convo.get_conversation(conversation_id)
        if existing is None:
            conversation_id = await convo.create_conversation(channel=channel)

    # 2. Search knowledge base for relevant context.
    sources_used: list[SourceCitation] = []
    context_block = ""
    try:
        sources_used, context_block = await _search_knowledge(message)
    except Exception:
        logger.warning("Knowledge search failed, continuing without context")

    # 3. Build the messages list for Ollama.
    history = await convo.get_history(conversation_id, limit=MAX_HISTORY_MESSAGES)
    ollama_messages = _build_messages(history, message, context_block)

    # 4. Store the user message.
    context_refs = [
        {"source": s.source, "source_path": s.source_path, "score": s.score}
        for s in sources_used
    ]
    await convo.add_message(conversation_id, "user", message, context_used=context_refs or None)

    # 5. Call Ollama.
    try:
        assistant_text = await _call_ollama(model, ollama_messages)
    except Exception as exc:
        error_msg = f"LLM service unavailable: {exc}"
        logger.error(error_msg)
        return ChatResponse(
            response="I'm sorry, I can't respond right now — the LLM service "
                     "appears to be offline. Please check that Ollama is running "
                     "on the worker machine.",
            conversation_id=conversation_id,
            model=model,
            sources_used=sources_used,
            error=error_msg,
        )

    # 6. Store assistant response.
    await convo.add_message(conversation_id, "assistant", assistant_text)

    return ChatResponse(
        response=assistant_text,
        conversation_id=conversation_id,
        model=model,
        sources_used=sources_used,
    )


# --- Knowledge search ---


async def _search_knowledge(query: str) -> tuple[list[SourceCitation], str]:
    """Embed query, search knowledge base, return citations and context block."""
    embedding = await _get_embedding(query)
    vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

    # Search across all knowledge tables.
    tables = {
        "documents": ("content", "source_path", "title"),
        "notes": ("content", "source_path", "title"),
        "transcriptions": ("transcript", "audio_file", None),
    }

    all_results: list[dict[str, Any]] = []
    for table, (content_col, path_col, title_col) in tables.items():
        try:
            cols = [
                "id",
                f"{content_col} AS content",
                "metadata",
                f"1 - (embedding <=> $1::vector) AS score",
            ]
            if path_col:
                cols.append(f"{path_col} AS source_path")
            if title_col:
                cols.append(f"{title_col} AS title")

            query_sql = f"""
                SELECT {', '.join(cols)}
                FROM elmer.{table}
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> $1::vector) >= $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """
            rows = await db.fetch_all(
                query_sql, vec_str, KNOWLEDGE_THRESHOLD, KNOWLEDGE_RESULT_LIMIT,
            )
            for row in rows:
                all_results.append({
                    "content": row["content"] or "",
                    "source": table,
                    "source_path": row.get("source_path"),
                    "title": row.get("title"),
                    "score": float(row["score"]),
                })
        except Exception:
            logger.warning("Knowledge search failed for table %s", table)

    # Sort by score and take top N.
    all_results.sort(key=lambda r: r["score"], reverse=True)
    top = all_results[:KNOWLEDGE_RESULT_LIMIT]

    if not top:
        return [], ""

    # Build citations and context block.
    citations: list[SourceCitation] = []
    context_parts: list[str] = []
    total_chars = 0

    for result in top:
        snippet = result["content"][:200]
        source_label = result["source_path"] or result["source"]

        citations.append(SourceCitation(
            source=result["source"],
            source_path=result["source_path"],
            score=result["score"],
            snippet=snippet,
        ))

        chunk = f"[Source: {source_label}]\n{result['content']}"
        if total_chars + len(chunk) > MAX_CONTEXT_CHARS:
            # Truncate this chunk to fit.
            remaining = MAX_CONTEXT_CHARS - total_chars
            if remaining > 100:
                chunk = chunk[:remaining] + "\n[...truncated]"
                context_parts.append(chunk)
            break
        context_parts.append(chunk)
        total_chars += len(chunk)

    context_block = (
        "Relevant context from your knowledge base:\n\n"
        + "\n\n".join(context_parts)
    )
    return citations, context_block


# --- Prompt building ---


def _build_messages(
    history: list[dict[str, Any]],
    user_message: str,
    context_block: str,
) -> list[dict[str, str]]:
    """Build the full messages list for Ollama."""
    messages: list[dict[str, str]] = []

    # System prompt — always first.
    system_content = SYSTEM_PROMPT
    if context_block:
        system_content += "\n\n" + context_block
    else:
        system_content += (
            "\n\nNote: No specific context was found in the knowledge base "
            "for this query. Answer from your general knowledge."
        )
    messages.append({"role": "system", "content": system_content})

    # Conversation history (trimmed to fit context window).
    total_chars = len(system_content) + len(user_message)
    history_to_include: list[dict[str, str]] = []

    for msg in reversed(history):
        msg_chars = len(msg.get("content", ""))
        if total_chars + msg_chars > MAX_CONTEXT_CHARS:
            break
        history_to_include.insert(0, {
            "role": msg["role"],
            "content": msg["content"],
        })
        total_chars += msg_chars

    messages.extend(history_to_include)

    # Current user message — always last.
    messages.append({"role": "user", "content": user_message})

    return messages


# --- Ollama call ---


async def _call_ollama(
    model: str,
    messages: list[dict[str, str]],
) -> str:
    """Send chat request to Ollama via worker, falling back to direct."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    # Try worker first.
    worker_url = f"{settings.worker_base_url}/llm/chat"
    try:
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            resp = await client.post(worker_url, json=payload)
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            msg = data.get("message", {})
            if msg and msg.get("content"):
                return msg["content"]
            logger.warning("Worker returned empty chat response, trying Ollama direct")
    except (httpx.RequestError, RuntimeError) as exc:
        logger.warning("Worker chat failed (%s), falling back to Ollama direct", exc)

    # Fall back to direct Ollama.
    ollama_url = f"{settings.ollama_base_url}/api/chat"
    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    if data.get("error"):
        raise RuntimeError(data["error"])

    msg = data.get("message", {})
    return msg.get("content", "")


# --- Embedding helper ---


async def _get_embedding(text: str) -> list[float]:
    """Generate embedding via worker, falling back to Ollama direct."""
    worker_url = f"{settings.worker_base_url}/llm/embed"
    ollama_url = f"{settings.ollama_base_url}/api/embed"
    payload = {"model": "nomic-embed-text", "input": text}

    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(worker_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or []
            if embeddings:
                return embeddings[0]
            # Old format fallback.
            embedding = data.get("embedding") or []
            if embedding:
                return embedding
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), trying Ollama direct", exc)

    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings") or []
        if embeddings:
            return embeddings[0]
        embedding = data.get("embedding") or []
        if embedding:
            return embedding

    raise RuntimeError("No embeddings returned from worker or Ollama")
