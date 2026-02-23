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
amateur radio, home automation, networking, Linux, and Docker.

IMPORTANT: You have many tools. You MUST call them to perform \
actions or look up data. NEVER generate fake tool output or pretend \
a tool ran.

AllStar tools (node 68498, W0ABE):
- allstar_status: get node status and connections
- allstar_connect: connect to a specific node number
- allstar_disconnect: disconnect from a specific node
- allstar_disconnect_all: disconnect from all nodes
- allstar_monitor: monitor a node (listen-only)
- allstar_lookup: look up a node in the directory
- allstar_find_active: list currently transmitting nodes
- allstar_search_nodes: search nodes by location/callsign
- allstar_connect_active: find an active node AND connect
- allstar_search_and_connect: search for a node AND connect

Log/QSO tools (Log4OM logbook):
- log_recent_qsos: most recent QSOs
- log_search_qsos: search by callsign, band, mode, country, date
- log_stats: totals by band, mode, DXCC
- log_dxcc: DXCC entity summary

Propagation tools:
- propagation_conditions: solar indices, band conditions (day/night)
- propagation_band_detail: detail for a specific band
- propagation_forecast: HF propagation forecast

DX cluster tools:
- dx_spots: recent DX spots (filter by band/mode/entity)
- dx_spots_summary: cluster activity summary
- dx_lookup_entity: callsign to DXCC entity lookup
- dx_get_needs: DX needs list
- dx_add_need: add entity/band/mode to needs
- dx_remove_need: remove a need by ID

POTA tools:
- pota_spots: current park activator spots
- pota_search_parks: search parks by state or name
- pota_nearby_parks: parks near a grid square
- pota_plan_activation: full activation plan for a park

Contest tools:
- contest_upcoming: upcoming contest calendar
- contest_recommend_band: band change recommendation
- contest_dashboard: live contest score/rates

System tools:
- system_status: core health and all node statuses
- system_scheduler: scheduled task status

Agent tools:
- agent_list: list all AI agents
- agent_trigger: manually run an agent
- agent_recent_runs: recent agent execution history

Tool selection examples:
- "how are the bands?" → propagation_conditions
- "is 20m open?" → propagation_band_detail with band="20m"
- "propagation forecast" → propagation_forecast
- "any DX spots on 40m?" → dx_spots with band="40m"
- "look up JA1ABC" → dx_lookup_entity with callsign="JA1ABC"
- "what do I still need?" → dx_get_needs
- "add Japan 20m CW to needs" → dx_add_need
- "who's activating POTA?" → pota_spots
- "parks near me" → pota_nearby_parks
- "plan activation for US-1228" → pota_plan_activation
- "any contests this weekend?" → contest_upcoming with days=7
- "what band should I switch to?" → contest_recommend_band
- "is everything online?" → system_status
- "run the daily briefing" → agent_trigger with name="daily-briefing"
- "what agents do we have?" → agent_list
- "connect to an active node" → allstar_connect_active
- "connect to estes park" → allstar_search_and_connect
- "summarize today's QSOs" → log_search_qsos with since=today
- "DXCC progress" → log_dxcc

If the user asks what you can do, what tools you have, or about your \
capabilities — answer in plain English. List your abilities in a \
friendly way. Do NOT call any tools for capability questions.

Always report what the tool returned. Do not make up results.\
"""

EMBED_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)
CHAT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)
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
    web_search_performed: bool = False
    web_search_query: str = ""
    web_sources: list[dict[str, str]] = field(default_factory=list)


async def chat(
    message: str,
    conversation_id: int | None = None,
    model: str = "llama3.1:8b",
    channel: str = "api",
    web_search: str = "auto",
) -> ChatResponse:
    """Process a chat message with RAG context augmentation.

    Steps:
      1. Create or load conversation
      2. Embed user message and search knowledge base
      2b. Decide whether to web search, execute if needed
      3. Build augmented prompt (system + context + history + message)
      4. Send to Ollama via worker (with fallback)
      5. Store messages and return response with citations
    """
    async with _chat_semaphore:
        return await _chat_inner(message, conversation_id, model, channel, web_search)


async def _chat_inner(
    message: str,
    conversation_id: int | None,
    model: str,
    channel: str,
    web_search: str,
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

    # 2b. Web search decision and execution.
    top_local_score = max((s.score for s in sources_used), default=0.0)
    web_context_block = ""
    web_source_list: list[dict[str, str]] = []
    search_performed = False
    search_query = ""

    effective_mode = web_search
    if web_search == "auto" and _has_search_marker(message):
        effective_mode = "force"

    if effective_mode != "off":
        try:
            from .search_decision import get_engine
            from .web_search import get_service as get_search_service

            decision = await get_engine().decide(
                message, mode=effective_mode, top_local_score=top_local_score,
            )

            if decision.should_search:
                search_query = decision.search_query
                web_results = await get_search_service().search(
                    decision.search_query, max_results=5,
                )
                if web_results:
                    search_performed = True
                    web_context_block, web_source_list = _format_web_results(web_results)
                    logger.info(
                        "Web search for '%s': %d results (%s)",
                        decision.search_query, len(web_results), decision.reason,
                    )
        except Exception:
            logger.warning("Web search failed, continuing without web results")

    # 3. Build the messages list for Ollama.
    combined_context = context_block
    if web_context_block:
        if combined_context:
            combined_context += "\n\n" + web_context_block
        else:
            combined_context = web_context_block

    history = await convo.get_history(conversation_id, limit=MAX_HISTORY_MESSAGES)
    ollama_messages = _build_messages(
        history, message, combined_context, has_web_results=search_performed,
    )

    # 4. Store the user message.
    context_refs = [
        {"source": s.source, "source_path": s.source_path, "score": s.score}
        for s in sources_used
    ]
    await convo.add_message(conversation_id, "user", message, context_used=context_refs or None)

    # 5. Call Ollama (with AllStar tools available).
    from .chat_tools import CHAT_TOOLS

    try:
        assistant_text = await _call_ollama(model, ollama_messages, tools=CHAT_TOOLS)
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
        web_search_performed=search_performed,
        web_search_query=search_query,
        web_sources=web_source_list,
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

    # Ensure each source type is represented, then fill remaining slots
    # by score.  This prevents one table (e.g. chunked docs) from
    # crowding out personal notes or transcriptions.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in all_results:
        by_source.setdefault(r["source"], []).append(r)
    for v in by_source.values():
        v.sort(key=lambda r: r["score"], reverse=True)

    top: list[dict[str, Any]] = []
    used_ids: set[tuple[str, str | None]] = set()

    # First pass: guarantee top result from each source that returned hits.
    for source in ("notes", "transcriptions", "documents"):
        if source in by_source and by_source[source]:
            best = by_source[source][0]
            key = (best["source"], best.get("source_path"))
            if key not in used_ids:
                top.append(best)
                used_ids.add(key)

    # Second pass: fill remaining slots by global score.
    all_results.sort(key=lambda r: r["score"], reverse=True)
    for r in all_results:
        if len(top) >= KNOWLEDGE_RESULT_LIMIT:
            break
        key = (r["source"], r.get("source_path"))
        if key not in used_ids:
            top.append(r)
            used_ids.add(key)

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
    has_web_results: bool = False,
) -> list[dict[str, str]]:
    """Build the full messages list for Ollama."""
    messages: list[dict[str, str]] = []

    # System prompt — always first.
    system_content = SYSTEM_PROMPT
    if has_web_results:
        system_content += (
            "\n\nYou have been provided with recent web search results below. "
            "Use this information to answer questions about current events, "
            "recent developments, or topics requiring up-to-date information. "
            "When using web search information, mention the source naturally "
            '(e.g., "According to..." or "Based on recent reports..."). '
            "If the web results don't contain relevant information, say so "
            "and answer from your general knowledge instead. "
            "Do NOT make up URLs or citations — only reference sources "
            "actually provided in the search results."
        )
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


# --- Web search helpers ---

MAX_WEB_CONTEXT_CHARS = 8000


def _has_search_marker(message: str) -> bool:
    """Check if the message contains explicit search markers."""
    msg = message.strip().lower()
    return msg.startswith("/websearch") or "[search]" in msg


def _format_web_results(
    results: list,
) -> tuple[str, list[dict[str, str]]]:
    """Format web search results into a context block and source list."""
    from .web_search import WebSearchResult

    parts: list[str] = []
    sources: list[dict[str, str]] = []
    total_chars = 0

    for r in results:
        sources.append({"title": r.title, "url": r.url, "snippet": r.snippet})

        text = r.body if r.body else r.snippet
        chunk = f"[Web: {r.title}]\nURL: {r.url}\n{text}"
        if total_chars + len(chunk) > MAX_WEB_CONTEXT_CHARS:
            remaining = MAX_WEB_CONTEXT_CHARS - total_chars
            if remaining > 100:
                chunk = chunk[:remaining] + "\n[...truncated]"
                parts.append(chunk)
            break
        parts.append(chunk)
        total_chars += len(chunk)

    context_block = (
        "Recent information from web search:\n\n"
        + "\n\n".join(parts)
    )
    return context_block, sources


# --- Ollama call ---


_MAX_TOOL_ROUNDS = 5


def _extract_text_tool_call(content: str) -> dict[str, Any] | None:
    """Detect a tool call emitted as plain text by small models.

    Handles multiple formats the model may produce:
      {"name": "tool", "parameters": {...}}
      {"name": "tool", "args": {...}}
      {"name": "tool", "arguments": {...}}
    Returns ``None`` if the content doesn't look like a tool call.
    """
    # Find all top-level JSON objects by matching balanced braces.
    candidates: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(content):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(content[start : i + 1])
                start = -1

    for raw in candidates:
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue

        if not isinstance(obj, dict):
            continue

        name = obj.get("name", "")
        if not name:
            continue

        # Accept "parameters", "args", or "arguments" as the params key.
        params = (
            obj.get("parameters")
            or obj.get("arguments")
            or obj.get("args")
            or {}
        )
        return {"function": {"name": name, "arguments": params}}

    return None


async def _call_ollama(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """Send chat request to Ollama, with optional tool-calling loop."""
    from .chat_tools import execute_tool

    for round_num in range(_MAX_TOOL_ROUNDS):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            # temperature=0 makes tool calling much more reliable with small models
            payload["options"] = {"temperature": 0}

        data = await _ollama_request(payload)

        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls")

        # Small models sometimes emit tool calls as plain text instead of
        # structured tool_calls.  Detect and recover.
        if not tool_calls:
            content = msg.get("content", "")
            parsed_tc = _extract_text_tool_call(content)
            if parsed_tc is not None:
                tool_calls = [parsed_tc]
                msg["tool_calls"] = tool_calls
                logger.info("Recovered text-format tool call from content")
            else:
                return content

        # Append the assistant message (with tool_calls) to history.
        messages.append(msg)

        # Execute each tool call and append results.
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            tool_args = fn.get("arguments", {})
            logger.info("Chat tool call [round %d]: %s(%s)", round_num + 1, tool_name, tool_args)

            result = await execute_tool(tool_name, tool_args)
            messages.append({"role": "tool", "content": result})

    # If we exhaust rounds, return whatever content we have.
    logger.warning("Chat tool-calling hit max rounds (%d)", _MAX_TOOL_ROUNDS)
    return msg.get("content", "") if msg else ""


async def _ollama_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a single request to Ollama via worker, falling back to direct."""
    # Try worker first.
    worker_url = f"{settings.worker_base_url}/llm/chat"
    try:
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            resp = await client.post(worker_url, json=payload)
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            msg = data.get("message", {})
            if msg and (msg.get("content") or msg.get("tool_calls")):
                return data
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

    return data


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
