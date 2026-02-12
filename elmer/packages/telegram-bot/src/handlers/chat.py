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

# Per-user conversation mapping: telegram_user_id -> elmer_conversation_id
_user_conversations: dict[int, int] = {}

# Per-user model override: telegram_user_id -> model name
_user_models: dict[int, str] = {}

DEFAULT_MODEL = "llama3.1:8b"


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

    # Build request payload.
    conversation_id = get_user_conversation(user_id)
    model = get_user_model(user_id)

    payload: dict = {
        "message": user_text,
        "model": model,
    }
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id

    url = f"{settings.core_base_url}/chat"

    try:
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.error("Chat request timed out")
        await update.message.reply_text(
            "Sorry, I'm having trouble connecting to my brain right now. "
            "Try again in a moment."
        )
        return
    except httpx.RequestError as exc:
        logger.error("Chat request failed: %s", exc)
        await update.message.reply_text(
            "Sorry, I'm having trouble connecting to my brain right now. "
            "Try again in a moment."
        )
        return
    except httpx.HTTPStatusError as exc:
        logger.error("Chat API error: %s", exc)
        await update.message.reply_text(
            "Sorry, something went wrong on the server side. Try again."
        )
        return

    # Update conversation mapping.
    new_convo_id = data.get("conversation_id")
    if new_convo_id is not None:
        set_user_conversation(user_id, new_convo_id)

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

    # Build source footnote.
    sources = data.get("sources_used", [])
    source_names = []
    for s in sources:
        path = s.get("source_path") or s.get("source") or ""
        # Extract just the filename from paths like /app/docs/foo.md#chunk-0
        name = path.rsplit("/", 1)[-1].split("#")[0] if "/" in path else path.split("#")[0]
        if name and name not in source_names:
            source_names.append(name)

    # Prefix: brain emoji if knowledge was used, speech bubble otherwise.
    has_context = len(sources) > 0
    prefix = "\U0001f9e0 " if has_context else "\U0001f4ac "

    reply = prefix + response_text

    # Append source footnote.
    if source_names:
        footnote = "\n\n\U0001f4da Sources: " + ", ".join(source_names[:5])
        # Only add if it fits or we can trim.
        if len(reply) + len(footnote) <= MAX_MESSAGE_LEN:
            reply += footnote

    # Send response, splitting if needed.
    if len(reply) <= MAX_MESSAGE_LEN:
        await update.message.reply_text(reply)
    else:
        chunks = _split_message(reply)
        for chunk in chunks:
            await update.message.reply_text(chunk)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acknowledge photo messages — image analysis not yet available."""
    await update.message.reply_text(
        "I can see you sent a photo, but image analysis isn't available "
        "yet. That's planned for a future update. "
        "For now, try describing what you'd like to know about it."
    )


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
