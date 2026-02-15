"""Basic command handlers for the Elmer Telegram Bot."""

import logging
from datetime import datetime

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings
from .chat import clear_user_conversation, get_user_model, set_user_model

logger = logging.getLogger("elmer.telegram.commands")

# Status emoji mapping.
_STATUS = {
    "online": "\u2705",     # green check
    "offline": "\u274c",     # red X
    "unreachable": "\u26a0\ufe0f",  # warning
    "unknown": "\u2753",     # question mark
}


def _icon(status: str) -> str:
    return _STATUS.get(status, "\u2753")


async def _api_get(path: str, params: dict | None = None) -> dict | None:
    """GET request to Elmer Core. Returns parsed JSON or None."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.core_base_url}{path}", params=params,
            )
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


def _ago(dt_str: str | None) -> str:
    """Human-readable time-ago from an ISO timestamp."""
    if not dt_str:
        return "never"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        delta = datetime.now(dt.tzinfo) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return "?"


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message."""
    await update.message.reply_text(
        "\U0001f4e1 *Elmer \u2014 W0ABE Home Lab*\n"
        "\n"
        "I'm Elmer, your AI-powered home lab assistant.\n"
        "I know about your systems, radio setup, network,\n"
        "and anything in your knowledge base.\n"
        "\n"
        "*Just send me a message* and I'll answer using\n"
        "your docs, notes, and transcripts as context.\n"
        "\n"
        "\U0001f9e0 *Knowledge*\n"
        "/search _query_ \u2014 Search your knowledge base\n"
        "/sources \u2014 See what's indexed\n"
        "/notes \u2014 Recent Obsidian notes\n"
        "\n"
        "\U0001f3a4 *Transcription*\n"
        "Send a voice message to transcribe it\n"
        "/transcripts \u2014 Recent transcriptions\n"
        "\n"
        "\U0001f5a5 *System*\n"
        "/status \u2014 System overview\n"
        "/nodes \u2014 All nodes\n"
        "\n"
        "/help for the full command list. 73!",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /status
# ------------------------------------------------------------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """System status summary."""
    # Core health.
    health = await _api_get("/health")
    if health is None:
        await update.message.reply_text(
            "\u274c Core unreachable — cannot fetch status."
        )
        return

    # Nodes.
    nodes_data = await _api_get("/health/nodes")
    nodes = nodes_data.get("nodes", []) if nodes_data else []

    online = sum(1 for n in nodes if n["status"] == "online")
    total = len(nodes)

    uptime_s = health.get("uptime_seconds", 0)
    hours = int(uptime_s // 3600)
    mins = int((uptime_s % 3600) // 60)

    lines = [
        f"\U0001f4e1 *Elmer Status*",
        f"",
        f"\u2705 Core: {health.get('status', '?')} (v{health.get('version', '?')})",
        f"\u23f1 Uptime: {hours}h {mins}m",
        f"\U0001f5a5 Nodes: {online}/{total} online",
        f"",
    ]

    for node in nodes:
        icon = _icon(node["status"])
        name = node.get("name", node.get("node_id", "?"))
        meta = node.get("metadata", {})
        cpu = meta.get("cpu_percent")
        ram = meta.get("ram_percent")
        extra = ""
        if cpu is not None and ram is not None:
            extra = f"  cpu {cpu:.0f}% ram {ram:.0f}%"
        lines.append(f"{icon} {name}: {node['status']}{extra}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /nodes
# ------------------------------------------------------------------

async def cmd_nodes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all nodes."""
    data = await _api_get("/health/nodes")
    if data is None:
        await update.message.reply_text("\u274c Could not reach Core API.")
        return

    nodes = data.get("nodes", [])
    if not nodes:
        await update.message.reply_text("No nodes registered yet.")
        return

    lines = ["\U0001f5a5 *Nodes*\n"]
    for n in nodes:
        icon = _icon(n["status"])
        name = n.get("name", n.get("node_id", "?"))
        seen = _ago(n.get("last_seen"))
        ntype = n.get("node_type", "")
        lines.append(f"{icon} *{name}* ({ntype})")
        lines.append(f"    {n['status']} \u2022 seen {seen}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /node <name>
# ------------------------------------------------------------------

async def cmd_node(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed status for a specific node."""
    if not context.args:
        await update.message.reply_text("Usage: /node _name_", parse_mode="Markdown")
        return

    node_id = context.args[0].lower()
    data = await _api_get(f"/health/nodes/{node_id}")
    if data is None:
        await update.message.reply_text(f"Node '{node_id}' not found.")
        return

    icon = _icon(data.get("status", "unknown"))
    seen = _ago(data.get("last_seen"))
    meta = data.get("metadata", {})

    lines = [
        f"{icon} *{data.get('name', node_id)}*",
        f"",
        f"Type: {data.get('node_type', '?')}",
        f"Status: {data.get('status', '?')}",
        f"Last seen: {seen}",
    ]

    if meta.get("hostname"):
        lines.append(f"Host: {meta['hostname']}")
    if meta.get("platform"):
        lines.append(f"Platform: {meta['platform']}")
    if meta.get("cpu_percent") is not None:
        lines.append(f"CPU: {meta['cpu_percent']:.1f}%")
    if meta.get("ram_percent") is not None:
        lines.append(
            f"RAM: {meta['ram_percent']:.1f}% "
            f"({meta.get('ram_used_mb', 0)}/"
            f"{meta.get('ram_total_mb', 0)} MB)"
        )
    if meta.get("disk_percent") is not None:
        lines.append(
            f"Disk: {meta['disk_percent']:.1f}% "
            f"({meta.get('disk_used_gb', 0):.1f}/"
            f"{meta.get('disk_total_gb', 0):.1f} GB)"
        )
    if meta.get("cpu_temp_c") is not None:
        lines.append(f"CPU temp: {meta['cpu_temp_c']}\u00b0C")
    if meta.get("system_uptime_seconds") is not None:
        h = int(meta["system_uptime_seconds"] // 3600)
        lines.append(f"System uptime: {h}h")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /services
# ------------------------------------------------------------------

async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all services and their status."""
    data = await _api_get("/health/nodes")
    if data is None:
        await update.message.reply_text("\u274c Could not reach Core API.")
        return

    nodes = data.get("nodes", [])
    if not nodes:
        await update.message.reply_text("No services registered.")
        return

    lines = ["\u2699\ufe0f *Services*\n"]
    for n in nodes:
        icon = _icon(n["status"])
        name = n.get("name", n.get("node_id", "?"))
        ntype = n.get("node_type", "")
        host = n.get("host", "")
        port = n.get("port", 0)
        addr = f"{host}:{port}" if host and port else "—"
        lines.append(f"{icon} *{name}*")
        lines.append(f"    {ntype} \u2022 {addr} \u2022 {n['status']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /events [n]
# ------------------------------------------------------------------

async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent events."""
    limit = 10
    if context.args:
        try:
            limit = max(1, min(50, int(context.args[0])))
        except ValueError:
            pass

    # Try the events endpoint first, fall back to node history.
    data = await _api_get("/events", params={"limit": limit})
    if data is not None:
        events = data if isinstance(data, list) else data.get("events", [])
    else:
        # Fallback: aggregate from all known nodes.
        nodes_data = await _api_get("/health/nodes")
        events = []
        if nodes_data:
            for n in nodes_data.get("nodes", []):
                nid = n.get("node_id", n.get("name", ""))
                hist = await _api_get(
                    f"/health/nodes/{nid}/history", params={"hours": 24},
                )
                if hist:
                    events.extend(hist.get("events", []))
        # Sort by timestamp descending, take top N.
        events.sort(
            key=lambda e: e.get("timestamp", ""), reverse=True,
        )
        events = events[:limit]

    if not events:
        await update.message.reply_text("No recent events.")
        return

    lines = [f"\U0001f4cb *Recent Events* (last {len(events)})\n"]
    for ev in events:
        ts = ev.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts = dt.strftime("%H:%M")
            except ValueError:
                ts = ts[:16]
        source = ev.get("source", "?")
        etype = ev.get("event_type", "?")
        lines.append(f"`{ts}` {source}: {etype}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /help
# ------------------------------------------------------------------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all commands."""
    await update.message.reply_text(
        "\U0001f4e1 *Elmer Commands*\n"
        "\n"
        "*Chat*\n"
        "Send any message \u2014 AI chat with knowledge\n"
        "/newchat \u2014 Start fresh conversation\n"
        "/model _name_ \u2014 Switch LLM model\n"
        "/models \u2014 List available models\n"
        "\n"
        "\U0001f310 *Web Search*\n"
        "Messages auto-search when needed\n"
        "/websearch _query_ \u2014 Search web & answer\n"
        "/web _query_ \u2014 Quick web search (no AI)\n"
        "/searchmode _\\[auto|on|off\\]_ \u2014 Search mode\n"
        "\n"
        "*Knowledge*\n"
        "/search _query_ \u2014 Semantic search\n"
        "/sources \u2014 Knowledge sources & counts\n"
        "/notes \u2014 Recent Obsidian notes\n"
        "/note _id_ \u2014 Read a specific note\n"
        "/sync \u2014 Trigger manual sync\n"
        "\n"
        "*Transcription*\n"
        "Send a voice message to transcribe\n"
        "/transcripts \u2014 Recent transcriptions\n"
        "/transcript _id_ \u2014 Read full transcript\n"
        "/tsearch _query_ \u2014 Search transcriptions\n"
        "\n"
        "*System*\n"
        "/status \u2014 System overview\n"
        "/nodes \u2014 All nodes with status\n"
        "/node _name_ \u2014 Detailed node info\n"
        "/services \u2014 Service list\n"
        "/events _\\[n\\]_ \u2014 Last N events\n"
        "/notifications _on/off_ \u2014 Toggle alerts\n"
        "/help \u2014 This message",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /newchat
# ------------------------------------------------------------------

async def cmd_newchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a fresh conversation (reset RAG context)."""
    user_id = update.effective_user.id if update.effective_user else 0
    old_id = clear_user_conversation(user_id)
    if old_id is not None:
        await update.message.reply_text(
            "\U0001f195 New conversation started. Previous context cleared."
        )
    else:
        await update.message.reply_text(
            "\U0001f195 Ready for a new conversation."
        )


# ------------------------------------------------------------------
# /model <name>
# ------------------------------------------------------------------

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch the LLM model for chat."""
    user_id = update.effective_user.id if update.effective_user else 0

    if not context.args:
        current = get_user_model(user_id)
        await update.message.reply_text(
            f"Current model: `{current}`\n"
            "Usage: /model _name_ (e.g. /model llama3.1:8b)\n"
            "Use /models to see available options.",
            parse_mode="Markdown",
        )
        return

    model_name = context.args[0]
    set_user_model(user_id, model_name)
    await update.message.reply_text(f"Model switched to `{model_name}`", parse_mode="Markdown")


# ------------------------------------------------------------------
# /models
# ------------------------------------------------------------------

async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List available models from Ollama."""
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_get("/llm/models")
    if data is None:
        await update.message.reply_text("Could not reach the LLM service.")
        return

    models = data.get("models", [])
    error = data.get("error")
    if error:
        await update.message.reply_text(f"LLM error: {error}")
        return

    if not models:
        await update.message.reply_text("No models available.")
        return

    user_id = update.effective_user.id if update.effective_user else 0
    current = get_user_model(user_id)

    lines = ["\U0001f916 *Available Models*\n"]
    for m in models:
        name = m.get("name", "?")
        size = m.get("size")
        size_str = ""
        if size:
            gb = size / (1024 ** 3)
            size_str = f" ({gb:.1f} GB)"
        marker = " \u2190 current" if name == current else ""
        lines.append(f"  \u2022 `{name}`{size_str}{marker}")

    lines.append(f"\nUse /model _name_ to switch.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /notifications on|off
# ------------------------------------------------------------------

async def cmd_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle notification alerts."""
    user_id = update.effective_user.id if update.effective_user else 0

    if not context.args:
        # Check current state.
        notifier = context.application.bot_data.get("notifier")
        muted = context.application.bot_data.get("muted_users", set())
        is_muted = user_id in muted
        state = "off" if is_muted else "on"
        await update.message.reply_text(
            f"Notifications are currently *{state}*.\n"
            "Usage: /notifications on or /notifications off",
            parse_mode="Markdown",
        )
        return

    action = context.args[0].lower()
    muted = context.application.bot_data.setdefault("muted_users", set())

    if action == "off":
        muted.add(user_id)
        await update.message.reply_text("\U0001f515 Notifications disabled.")
    elif action == "on":
        muted.discard(user_id)
        await update.message.reply_text("\U0001f514 Notifications enabled.")
    else:
        await update.message.reply_text("Usage: /notifications on or /notifications off")
