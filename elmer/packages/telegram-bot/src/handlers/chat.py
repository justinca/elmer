"""Chat handler — forwards text messages to Elmer Core LLM."""

import logging

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger("elmer.telegram.chat")

SYSTEM_PROMPT = (
    "You are Elmer, a helpful AI assistant for W0ABE's home lab and "
    "amateur radio station. You help monitor systems, answer questions "
    "about the setup, and provide radio-related assistance. "
    "Be concise — this is a Telegram chat."
)

# Telegram message limit is 4096 chars.
MAX_MESSAGE_LEN = 4000


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward user text to the Core /llm/chat endpoint."""
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    # Show typing indicator.
    await update.message.chat.send_action(ChatAction.TYPING)

    # Build messages payload.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    url = f"{settings.core_base_url}/llm/chat"
    payload = {
        "model": "llama3",
        "messages": messages,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except httpx.RequestError as exc:
        logger.error("LLM request failed: %s", exc)
        await update.message.reply_text(
            "Couldn't reach the LLM service right now. Try again shortly."
        )
        return

    # Check for errors.
    error = data.get("error")
    if error:
        await update.message.reply_text(f"LLM error: {error}")
        return

    # Extract response text.
    msg = data.get("message")
    if not msg or not msg.get("content"):
        await update.message.reply_text("No response from Elmer. The LLM might be loading.")
        return

    reply = msg["content"].strip()

    # Split long responses into multiple messages.
    if len(reply) <= MAX_MESSAGE_LEN:
        await update.message.reply_text(reply)
    else:
        chunks = _split_message(reply)
        for chunk in chunks:
            await update.message.reply_text(chunk)


def _split_message(text: str) -> list[str]:
    """Split text into chunks that fit Telegram's message limit.

    Tries to break on paragraph boundaries, then sentences, then hard cut.
    """
    chunks: list[str] = []
    while len(text) > MAX_MESSAGE_LEN:
        # Try to break at a paragraph boundary.
        cut = text.rfind("\n\n", 0, MAX_MESSAGE_LEN)
        if cut == -1:
            # Try single newline.
            cut = text.rfind("\n", 0, MAX_MESSAGE_LEN)
        if cut == -1:
            # Try sentence boundary.
            cut = text.rfind(". ", 0, MAX_MESSAGE_LEN)
            if cut != -1:
                cut += 1  # include the period
        if cut == -1:
            # Hard cut.
            cut = MAX_MESSAGE_LEN
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
