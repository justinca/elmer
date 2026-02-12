"""Knowledge commands — search, notes, sources, sync."""

import logging

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger("elmer.telegram.knowledge")

API_TIMEOUT = 30.0


async def _api_get(path: str, params: dict | None = None) -> dict | list | None:
    """GET request to Elmer Core."""
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.core_base_url}{path}", params=params,
            )
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


async def _api_post(path: str, json_data: dict) -> dict | list | None:
    """POST request to Elmer Core."""
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.core_base_url}{path}", json=json_data,
            )
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


# ------------------------------------------------------------------
# /search <query>
# ------------------------------------------------------------------

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Semantic search across all knowledge."""
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return

    query = " ".join(context.args)
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_post("/knowledge/search", {
        "query": query,
        "limit": 3,
        "sources": ["docs", "notes", "transcripts"],
        "threshold": 0.3,
    })

    if data is None:
        await update.message.reply_text("Could not reach the knowledge service.")
        return

    results = data.get("results", [])
    if not results:
        await update.message.reply_text(
            f"No results found for \"{query}\".\n"
            "Try a different query or check /sources."
        )
        return

    lines = [f"\U0001f50d *Search:* {query}\n"]
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        source = r.get("source", "?")
        content = (r.get("content") or "")[:200].replace("\n", " ").strip()
        if not content:
            content = "(empty)"

        # Score bar: filled blocks proportional to score.
        bar_len = round(score * 5)
        bar = "\u2588" * bar_len + "\u2591" * (5 - bar_len)

        lines.append(f"*{i}.* [{bar}] {score:.0%} \u2014 _{source}_")
        lines.append(f"   {content}")
        if i < len(results):
            lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /notes
# ------------------------------------------------------------------

async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List recent synced Obsidian notes."""
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_post("/knowledge/search", {
        "query": "notes",
        "limit": 10,
        "sources": ["notes"],
        "threshold": 0.0,
    })

    if data is None:
        await update.message.reply_text("Could not reach the knowledge service.")
        return

    results = data.get("results", [])
    if not results:
        await update.message.reply_text("No notes found in the knowledge base.")
        return

    lines = ["\U0001f4dd *Recent Notes*\n"]
    for i, r in enumerate(results, 1):
        content = (r.get("content") or "")[:80].replace("\n", " ").strip()
        rid = r.get("id", "?")
        lines.append(f"{i}. `#{rid}` {content}")

    lines.append(f"\nUse /note <id> to read a specific note.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /note <id>
# ------------------------------------------------------------------

async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a specific note's content."""
    if not context.args:
        await update.message.reply_text("Usage: /note <id>")
        return

    note_id = context.args[0].lstrip("#")
    await update.message.chat.send_action(ChatAction.TYPING)

    # Query the notes table directly via search with a very broad query.
    # We'll try to fetch by ID through the knowledge search.
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.core_base_url}/notes/{note_id}",
            )
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title", "Untitled")
                content = data.get("content", "No content")

                # Truncate for Telegram.
                if len(content) > 3800:
                    content = content[:3800] + "\n\n[...truncated]"

                await update.message.reply_text(
                    f"\U0001f4dd *{title}*\n\n{content}",
                    parse_mode="Markdown",
                )
                return
            elif resp.status_code == 404:
                await update.message.reply_text(f"Note #{note_id} not found.")
                return
    except (httpx.RequestError, httpx.HTTPStatusError):
        pass

    await update.message.reply_text(
        f"Could not fetch note #{note_id}. "
        "Use /notes to see available notes."
    )


# ------------------------------------------------------------------
# /sources
# ------------------------------------------------------------------

async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all knowledge sources and document counts."""
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_get("/knowledge/sources")
    if data is None:
        await update.message.reply_text("Could not reach the knowledge service.")
        return

    if not data:
        await update.message.reply_text("No sources in the knowledge base yet.")
        return

    lines = ["\U0001f4da *Knowledge Sources*\n"]
    total = 0
    for src in data:
        name = src.get("source", "?")
        count = src.get("doc_count", 0)
        updated = src.get("latest_update", "")
        if updated:
            # Show just date portion.
            updated = updated[:10]
        total += count
        lines.append(f"  \u2022 *{name}*: {count} chunks (updated {updated})")

    lines.append(f"\n*Total:* {total} chunks across {len(data)} sources")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /sync
# ------------------------------------------------------------------

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger Obsidian sync manually."""
    msg = await update.message.reply_text("\U0001f504 Syncing...")

    # Trigger ingest of docs directory.
    data = await _api_post("/knowledge/ingest/directory", {
        "path": "/data/docs",
        "source": "elmer-docs",
        "recursive": True,
        "patterns": ["*.md"],
    })

    if data is None:
        await msg.edit_text("\u274c Sync failed \u2014 could not reach Core API.")
        return

    ingested = data.get("ingested", 0)
    skipped = data.get("skipped", 0)
    errors = data.get("errors", [])
    error_count = len(errors)

    status = "\u2705" if error_count == 0 else "\u26a0\ufe0f"
    await msg.edit_text(
        f"{status} Done: {ingested} ingested, {skipped} skipped"
        + (f", {error_count} errors" if error_count else "")
    )
