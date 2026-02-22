"""Elmer Telegram Bot — entry point.

Connects to MQTT for real-time alerts, registers with Elmer Core,
and serves as the mobile interface to the Elmer home-lab OS.
"""

import logging

import httpx
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import settings
from .handlers.basic import (
    cmd_events,
    cmd_help,
    cmd_model,
    cmd_models,
    cmd_newchat,
    cmd_node,
    cmd_nodes,
    cmd_notifications,
    cmd_services,
    cmd_start,
    cmd_status,
)
from .handlers.chat import (
    cmd_searchmode,
    cmd_web,
    cmd_websearch,
    handle_message,
    handle_photo,
)
from .handlers.knowledge import (
    cmd_note,
    cmd_notes,
    cmd_search,
    cmd_sources,
    cmd_sync,
)
from .handlers.agents import (
    cmd_agent,
    cmd_agents,
    cmd_disable,
    cmd_enable,
    cmd_run,
    cmd_runs,
    cmd_schedule,
    handle_agent_callback,
)
from .handlers.radio import (
    cmd_allstar,
    cmd_bands,
    cmd_contest,
    cmd_dx,
    cmd_dxcc,
    cmd_log,
    cmd_need,
    cmd_needs,
    cmd_plan,
    cmd_pota,
    cmd_prop,
    cmd_solar,
    cmd_spots,
    handle_allstar_callback,
)
from .handlers.notifications import NotificationManager
from .handlers.transcription import (
    cmd_transcript,
    cmd_transcripts,
    cmd_tsearch,
    handle_voice,
)

from elmer_common.logging import setup_logger as _setup_logger

_setup_logger("elmer", logging.INFO)
logger = logging.getLogger("elmer.telegram")


def _is_authorized(user_id: int) -> bool:
    """Check if user is in the allowed list."""
    allowed = settings.allowed_user_ids
    if not allowed:
        return False
    return user_id in allowed


async def _register_with_core() -> None:
    """Announce ourselves to Elmer Core on startup."""
    url = f"{settings.core_base_url}/nodes"
    payload = {
        "node_id": "telegram",
        "name": "Telegram Bot",
        "node_type": "service",
        "host": "",
        "port": 0,
        "status": "online",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
        logger.info("Registered with Elmer Core at %s", settings.core_base_url)
    except httpx.RequestError as exc:
        logger.warning("Could not register with Core (will retry via heartbeat): %s", exc)


async def post_init(application: Application) -> None:
    """Run after the bot application is initialized."""
    await _register_with_core()

    # Set command menu for Telegram UI.
    await application.bot.set_my_commands([
        BotCommand("allstar", "AllStar node status & control"),
        BotCommand("prop", "Propagation summary"),
        BotCommand("bands", "Band conditions grid"),
        BotCommand("solar", "Solar indices"),
        BotCommand("spots", "DX spots [band] [mode]"),
        BotCommand("pota", "POTA spots or park info"),
        BotCommand("dxcc", "DXCC award progress"),
        BotCommand("contest", "Upcoming contests"),
        BotCommand("status", "System status summary"),
        BotCommand("agents", "List all agents"),
        BotCommand("search", "Search knowledge base"),
        BotCommand("websearch", "Web search + AI answer"),
        BotCommand("web", "Quick web search"),
        BotCommand("help", "All commands"),
    ])

    # Start MQTT notification manager.
    notifier = NotificationManager(application.bot, application=application)
    application.bot_data["notifier"] = notifier
    await notifier.start()
    logger.info("MQTT notification manager started")


async def post_shutdown(application: Application) -> None:
    """Clean shutdown of background services."""
    notifier = application.bot_data.get("notifier")
    if notifier:
        await notifier.stop()
    logger.info("Elmer Telegram Bot stopped.")


async def _reject_unauthorized(update: Update, _context) -> None:
    """Catch-all handler for unauthorized users."""
    if update.effective_user is None:
        return
    if _is_authorized(update.effective_user.id):
        return
    if update.message:
        await update.message.reply_text(
            "Sorry, I'm not configured to chat with you.\n"
            "Ask the station operator to add your Telegram user ID "
            f"({update.effective_user.id}) to the allowed list."
        )


def main() -> None:
    """Build and run the bot."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set — exiting.")
        return

    logger.info("Starting Elmer Telegram Bot...")

    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Build user filter for authorized users.
    if settings.allowed_user_ids:
        user_filter = filters.User(user_id=settings.allowed_user_ids)
    else:
        # No users configured — commands won't match, catch-all will reject.
        user_filter = filters.User(user_id={0})

    # Register command handlers (authorized users only).
    commands = {
        # Basic / system.
        "start": cmd_start,
        "status": cmd_status,
        "nodes": cmd_nodes,
        "node": cmd_node,
        "services": cmd_services,
        "events": cmd_events,
        "help": cmd_help,
        # Chat.
        "newchat": cmd_newchat,
        "model": cmd_model,
        "models": cmd_models,
        # Web search.
        "websearch": cmd_websearch,
        "web": cmd_web,
        "searchmode": cmd_searchmode,
        # Knowledge.
        "search": cmd_search,
        "notes": cmd_notes,
        "note": cmd_note,
        "sources": cmd_sources,
        "sync": cmd_sync,
        # Transcription.
        "transcripts": cmd_transcripts,
        "transcript": cmd_transcript,
        "tsearch": cmd_tsearch,
        # Notifications.
        "notifications": cmd_notifications,
        # Agents.
        "agents": cmd_agents,
        "agent": cmd_agent,
        "run": cmd_run,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "runs": cmd_runs,
        "schedule": cmd_schedule,
        # Radio.
        "allstar": cmd_allstar,
        "prop": cmd_prop,
        "bands": cmd_bands,
        "solar": cmd_solar,
        "spots": cmd_spots,
        "dx": cmd_dx,
        "needs": cmd_needs,
        "need": cmd_need,
        "pota": cmd_pota,
        "plan": cmd_plan,
        "log": cmd_log,
        "dxcc": cmd_dxcc,
        "contest": cmd_contest,
    }
    for name, handler_fn in commands.items():
        app.add_handler(CommandHandler(name, handler_fn, filters=user_filter))

    # Text messages -> RAG chat (authorized users only).
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & user_filter,
        handle_message,
    ))

    # Voice messages -> transcription (authorized users only).
    app.add_handler(MessageHandler(
        filters.VOICE & user_filter,
        handle_voice,
    ))

    # Photo messages -> acknowledge (authorized users only).
    app.add_handler(MessageHandler(
        filters.PHOTO & user_filter,
        handle_photo,
    ))

    # Inline keyboard callbacks for agent actions (authorized users only).
    app.add_handler(CallbackQueryHandler(
        handle_agent_callback,
        pattern="^agent_",
    ))

    # Inline keyboard callbacks for AllStar actions.
    app.add_handler(CallbackQueryHandler(
        handle_allstar_callback,
        pattern="^allstar_",
    ))

    # Catch-all: reject unauthorized users with polite message.
    app.add_handler(MessageHandler(filters.ALL, _reject_unauthorized))

    logger.info("Bot ready — polling for updates")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
