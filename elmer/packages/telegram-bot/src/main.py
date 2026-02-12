"""Elmer Telegram Bot — Application entry point."""

import asyncio
import os

from telegram import Update
from telegram.ext import ApplicationBuilder

from .handlers.basic import register_handlers


def main():
    """Start the Telegram bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = ApplicationBuilder().token(token).build()
    register_handlers(app)

    print("Elmer Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
