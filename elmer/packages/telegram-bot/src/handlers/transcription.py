"""Transcription commands — voice messages, transcripts, search."""

import logging
import tempfile
from pathlib import Path

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger("elmer.telegram.transcription")

API_TIMEOUT = 30.0
TRANSCRIBE_TIMEOUT = 600.0


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


def _format_duration(seconds: float | None) -> str:
    """Format seconds into Xm Ys."""
    if seconds is None:
        return "?"
    m = int(seconds) // 60
    s = int(seconds) % 60
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ------------------------------------------------------------------
# Voice message handler
# ------------------------------------------------------------------

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Automatically transcribe voice notes sent in Telegram."""
    voice = update.message.voice
    if voice is None:
        return

    duration = voice.duration or 0
    await update.message.chat.send_action(ChatAction.TYPING)
    status_msg = await update.message.reply_text(
        f"\U0001f3a4 Transcribing voice message ({_format_duration(duration)})..."
    )

    # Download the voice file.
    try:
        file = await context.bot.get_file(voice.file_id)
    except Exception as exc:
        logger.error("Failed to get voice file: %s", exc)
        await status_msg.edit_text("\u274c Failed to download voice message.")
        return

    # Save to temp file.
    suffix = ".ogg"  # Telegram voice messages are OGG/Opus.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        await file.download_to_drive(str(tmp_path))

        # Send to Core transcription API.
        async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT) as client:
            with open(tmp_path, "rb") as f:
                resp = await client.post(
                    f"{settings.core_base_url}/transcription/upload",
                    files={"file": (f"telegram_voice_{voice.file_unique_id}.ogg", f, "audio/ogg")},
                )

            if resp.status_code != 200:
                error_detail = "unknown error"
                try:
                    error_detail = resp.json().get("detail", error_detail)
                except Exception:
                    pass
                await status_msg.edit_text(
                    f"\u274c Transcription failed: {error_detail}"
                )
                return

            data = resp.json()

    except httpx.TimeoutException:
        await status_msg.edit_text(
            "\u274c Transcription timed out. The voice message may be too long."
        )
        return
    except httpx.RequestError as exc:
        logger.error("Transcription request failed: %s", exc)
        await status_msg.edit_text(
            "\u274c Could not reach the transcription service."
        )
        return
    finally:
        tmp_path.unlink(missing_ok=True)

    transcript = data.get("transcript", "").strip()
    language = data.get("language", "")
    t_duration = data.get("duration_seconds")
    t_id = data.get("id")

    if not transcript:
        await status_msg.edit_text(
            "\U0001f3a4 Voice message transcribed but no speech was detected."
        )
        return

    # Truncate long transcripts for Telegram.
    display = transcript
    if len(display) > 3800:
        display = display[:3800] + "\n\n[...truncated]"

    lang_str = f" ({language})" if language else ""
    dur_str = f" \u2022 {_format_duration(t_duration)}" if t_duration else ""
    id_str = f" \u2022 #{t_id}" if t_id else ""

    await status_msg.edit_text(
        f"\U0001f3a4 *Transcript*{lang_str}{dur_str}{id_str}\n\n{display}",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /transcripts
# ------------------------------------------------------------------

async def cmd_transcripts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List recent transcriptions."""
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_get("/transcription", params={"limit": 10})
    if data is None:
        await update.message.reply_text("Could not reach the transcription service.")
        return

    if not data:
        await update.message.reply_text("No transcriptions yet.")
        return

    lines = ["\U0001f3a4 *Recent Transcriptions*\n"]
    for t in data:
        tid = t.get("id", "?")
        audio = t.get("audio_file", "?")
        # Shorten the filename.
        if len(audio) > 40:
            audio = audio[:37] + "..."
        duration = _format_duration(t.get("duration_seconds"))
        snippet = (t.get("transcript") or "")[:60].replace("\n", " ")
        lang = t.get("language") or ""

        lines.append(f"`#{tid}` {audio}")
        lang_part = f" \u2022 {lang}" if lang else ""
        lines.append(f"   {duration}{lang_part}")
        if snippet:
            lines.append(f"   _{snippet}_")
        lines.append("")

    lines.append("Use /transcript <id> to see full text.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /transcript <id>
# ------------------------------------------------------------------

async def cmd_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a specific transcript."""
    if not context.args:
        await update.message.reply_text("Usage: /transcript <id>")
        return

    tid = context.args[0].lstrip("#")
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_get(f"/transcription/{tid}")
    if data is None:
        await update.message.reply_text(f"Transcript #{tid} not found.")
        return

    audio = data.get("audio_file", "?")
    transcript = data.get("transcript", "No transcript")
    duration = _format_duration(data.get("duration_seconds"))
    language = data.get("language") or ""
    created = (data.get("created_at") or "")[:16]

    if len(transcript) > 3800:
        transcript = transcript[:3800] + "\n\n[...truncated]"

    header = f"\U0001f3a4 *{audio}*"
    lang_part = f" \u2022 {language}" if language else ""
    meta = f"{duration}{lang_part}"
    if created:
        meta += f" \u2022 {created}"

    await update.message.reply_text(
        f"{header}\n{meta}\n\n{transcript}",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /tsearch <query>
# ------------------------------------------------------------------

async def cmd_tsearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search transcriptions specifically."""
    if not context.args:
        await update.message.reply_text("Usage: /tsearch <query>")
        return

    query = " ".join(context.args)
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_get("/transcription/search", params={"q": query, "limit": 5})
    if data is None:
        await update.message.reply_text("Could not reach the transcription service.")
        return

    if not data:
        await update.message.reply_text(
            f"No transcription results for \"{query}\"."
        )
        return

    lines = [f"\U0001f50d *Transcription search:* {query}\n"]
    for i, r in enumerate(data, 1):
        tid = r.get("id", "?")
        audio = r.get("audio_file", "?")
        score = r.get("score", 0)
        snippet = (r.get("transcript") or "")[:120].replace("\n", " ")

        lines.append(f"*{i}.* `#{tid}` {audio} ({score:.0%})")
        if snippet:
            lines.append(f"   _{snippet}_")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
