"""Chat handler — RAG-powered conversations via Elmer Core /chat API."""

import logging

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger("elmer.telegram.chat")

# Telegram message limit is 4096 chars.
MAX_MESSAGE_LEN = 4000
CHAT_TIMEOUT = 180.0
SEARCH_TIMEOUT = 30.0

# Per-user conversation mapping: telegram_user_id -> elmer_conversation_id
_user_conversations: dict[int, int] = {}

# Per-user model override: telegram_user_id -> model name
_user_models: dict[int, str] = {}

# Per-user web search mode: telegram_user_id -> "auto" | "on" | "off"
_user_search_modes: dict[int, str] = {}

DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_SEARCH_MODE = "auto"


def get_user_conversation(user_id: int) -> int | None:
    """Get the current conversation ID for a Telegram user."""
    return _user_conversations.get(user_id)


def set_user_conversation(user_id: int, conversation_id: int) -> None:
    """Map a Telegram user to an Elmer conversation."""
    _user_conversations[user_id] = conversation_id


def clear_user_conversation(user_id: int) -> int | None:
    """Clear a user's conversation mapping. Returns old ID if any."""
    return _user_conversations.pop(user_id, None)


def get_user_model(user_id: int) -> str:
    """Get the user's selected LLM model."""
    return _user_models.get(user_id, DEFAULT_MODEL)


def set_user_model(user_id: int, model: str) -> None:
    """Set the user's preferred LLM model."""
    _user_models[user_id] = model


def get_user_search_mode(user_id: int) -> str:
    """Get the user's web search mode."""
    return _user_search_modes.get(user_id, DEFAULT_SEARCH_MODE)


def set_user_search_mode(user_id: int, mode: str) -> None:
    """Set the user's web search mode."""
    _user_search_modes[user_id] = mode


# ------------------------------------------------------------------
# Core chat (used by handle_message and cmd_websearch)
# ------------------------------------------------------------------


async def _chat_with_core(
    user_text: str,
    user_id: int,
    web_search: str = "auto",
) -> dict | None:
    """Call Core /chat API and return parsed response, or None on error."""
    conversation_id = get_user_conversation(user_id)
    model = get_user_model(user_id)

    payload: dict = {
        "message": user_text,
        "model": model,
        "web_search": web_search,
    }
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id

    url = f"{settings.core_base_url}/chat"

    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Update conversation mapping.
    new_convo_id = data.get("conversation_id")
    if new_convo_id is not None:
        set_user_conversation(user_id, new_convo_id)

    return data


def _format_chat_reply(data: dict) -> str:
    """Build the Telegram reply text from a /chat response."""
    response_text = data.get("response", "").strip()
    sources = data.get("sources_used", [])
    web_performed = data.get("web_search_performed", False)
    web_sources = data.get("web_sources", [])

    # Build source footnote.
    source_names = []
    for s in sources:
        path = s.get("source_path") or s.get("source") or ""
        # Extract just the filename from paths like /app/docs/foo.md#chunk-0
        name = path.rsplit("/", 1)[-1].split("#")[0] if "/" in path else path.split("#")[0]
        if name and name not in source_names:
            source_names.append(name)

    # Prefix: globe if web search was used, brain if knowledge, speech bubble otherwise.
    if web_performed:
        prefix = "\U0001f310 "  # globe
    elif sources:
        prefix = "\U0001f9e0 "  # brain
    else:
        prefix = "\U0001f4ac "  # speech bubble

    reply = prefix + response_text

    # Append local source footnote.
    if source_names:
        footnote = "\n\n\U0001f4da Sources: " + ", ".join(source_names[:5])
        if len(reply) + len(footnote) <= MAX_MESSAGE_LEN:
            reply += footnote

    # Append web source footnote.
    if web_sources:
        web_lines = ["\n\n\U0001f310 Web sources:"]
        for ws in web_sources[:5]:
            title = ws.get("title", "")
            url = ws.get("url", "")
            if title and url:
                web_lines.append(f"\u2022 {title} \u2014 {url}")
            elif url:
                web_lines.append(f"\u2022 {url}")
        web_footer = "\n".join(web_lines)
        if len(reply) + len(web_footer) <= MAX_MESSAGE_LEN:
            reply += web_footer

    return reply


# ------------------------------------------------------------------
# Message handler (regular text messages)
# ------------------------------------------------------------------


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward user text to the Core /chat RAG endpoint."""
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    user_id = update.effective_user.id if update.effective_user else 0

    # Show typing indicator.
    await update.message.chat.send_action(ChatAction.TYPING)

    # Map user search mode to the API web_search parameter.
    mode = get_user_search_mode(user_id)
    if mode == "on":
        web_search = "force"
    elif mode == "off":
        web_search = "off"
    else:
        web_search = "auto"

    try:
        data = await _chat_with_core(user_text, user_id, web_search=web_search)
    except httpx.TimeoutException:
        logger.error("Chat request timed out")
        await update.message.reply_text(
            "Sorry, I'm having trouble connecting to my brain right now. "
            "Try again in a moment."
        )
        return
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.error("Chat request failed: %s", exc)
        await update.message.reply_text(
            "Sorry, I'm having trouble connecting to my brain right now. "
            "Try again in a moment."
        )
        return

    # Check for errors.
    error = data.get("error")
    response_text = data.get("response", "").strip()

    if not response_text and error:
        await update.message.reply_text(f"LLM error: {error}")
        return

    if not response_text:
        await update.message.reply_text(
            "No response from Elmer. The LLM might be loading."
        )
        return

    reply = _format_chat_reply(data)

    # Send response, splitting if needed.
    if len(reply) <= MAX_MESSAGE_LEN:
        await update.message.reply_text(reply)
    else:
        chunks = _split_message(reply)
        for chunk in chunks:
            await update.message.reply_text(chunk)


# ------------------------------------------------------------------
# /websearch <query> — force web search with LLM
# ------------------------------------------------------------------


async def cmd_websearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force a web search and answer with results."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /websearch <query>\n"
            "Example: /websearch latest solar flux index"
        )
        return

    query = " ".join(context.args)
    user_id = update.effective_user.id if update.effective_user else 0

    # Show typing indicator.
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        data = await _chat_with_core(query, user_id, web_search="force")
    except httpx.TimeoutException:
        logger.error("Websearch chat timed out")
        await update.message.reply_text("Search timed out. Try again.")
        return
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.error("Websearch chat failed: %s", exc)
        await update.message.reply_text("Could not reach the chat service.")
        return

    response_text = data.get("response", "").strip()
    if not response_text:
        error = data.get("error")
        await update.message.reply_text(
            f"No response. {error}" if error else "No response from Elmer."
        )
        return

    reply = _format_chat_reply(data)

    if len(reply) <= MAX_MESSAGE_LEN:
        await update.message.reply_text(reply)
    else:
        for chunk in _split_message(reply):
            await update.message.reply_text(chunk)


# ------------------------------------------------------------------
# /web <query> — quick web search without LLM
# ------------------------------------------------------------------


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick web search — returns raw results without LLM processing."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /web <query>\n"
            "Example: /web IC-7300 price"
        )
        return

    query = " ".join(context.args)
    await update.message.chat.send_action(ChatAction.TYPING)

    url = f"{settings.core_base_url}/search/web"

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.post(url, json={
                "query": query,
                "max_results": 3,
            })
            resp.raise_for_status()
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.error("Web search failed: %s", exc)
        await update.message.reply_text("Web search failed. Try again later.")
        return

    results = data.get("results", [])
    if not results:
        await update.message.reply_text(f"No web results for \"{query}\".")
        return

    lines = [f"\U0001f310 Web results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        snippet = r.get("snippet", "")
        result_url = r.get("url", "")
        lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet[:200]}")
        if result_url:
            lines.append(f"   {result_url}")
        if i < len(results):
            lines.append("")

    reply = "\n".join(lines)
    if len(reply) <= MAX_MESSAGE_LEN:
        await update.message.reply_text(reply)
    else:
        for chunk in _split_message(reply):
            await update.message.reply_text(chunk)


# ------------------------------------------------------------------
# /searchmode [auto|on|off] — per-user search preference
# ------------------------------------------------------------------


async def cmd_searchmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show or set the web search mode."""
    user_id = update.effective_user.id if update.effective_user else 0
    current = get_user_search_mode(user_id)

    if not context.args:
        mode_desc = {
            "auto": "LLM decides when to search",
            "on": "always search the web",
            "off": "never auto-search (use /websearch to force)",
        }
        await update.message.reply_text(
            f"\U0001f310 Search mode: *{current}* \u2014 {mode_desc.get(current, '')}\n"
            "\n"
            "Usage: /searchmode auto|on|off",
            parse_mode="Markdown",
        )
        return

    mode = context.args[0].lower()
    if mode not in ("auto", "on", "off"):
        await update.message.reply_text(
            "Invalid mode. Choose: auto, on, or off"
        )
        return

    set_user_search_mode(user_id, mode)
    labels = {"auto": "Auto", "on": "Always On", "off": "Off"}
    await update.message.reply_text(
        f"\U0001f310 Search mode set to *{labels[mode]}*",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# Photo handler
# ------------------------------------------------------------------


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acknowledge photo messages — image analysis not yet available."""
    await update.message.reply_text(
        "I can see you sent a photo, but image analysis isn't available "
        "yet. That's planned for a future update. "
        "For now, try describing what you'd like to know about it."
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _split_message(text: str) -> list[str]:
    """Split text into chunks that fit Telegram's message limit."""
    chunks: list[str] = []
    while len(text) > MAX_MESSAGE_LEN:
        cut = text.rfind("\n\n", 0, MAX_MESSAGE_LEN)
        if cut == -1:
            cut = text.rfind("\n", 0, MAX_MESSAGE_LEN)
        if cut == -1:
            cut = text.rfind(". ", 0, MAX_MESSAGE_LEN)
            if cut != -1:
                cut += 1
        if cut == -1:
            cut = MAX_MESSAGE_LEN
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
