"""Basic command handlers for the Telegram bot."""

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to Elmer! Your AI home lab assistant.\n\n"
        "Commands:\n"
        "/status — System status\n"
        "/help — Show this message"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    await update.message.reply_text(
        "Checking system status...\n"
        "(Status check not yet wired to core API)"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "Elmer Bot Commands:\n"
        "/start — Welcome message\n"
        "/status — Check system health\n"
        "/help — This help message"
    )


def register_handlers(app: Application):
    """Register all command handlers."""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_command))
