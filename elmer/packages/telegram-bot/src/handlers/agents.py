"""Agent management commands for the Elmer Telegram Bot."""

import logging
from datetime import datetime

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger("elmer.telegram.agents")

_TIMEOUT = 10.0
_RUN_TIMEOUT = 180.0


async def _api_get(path: str, params: dict | None = None) -> dict | list | None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{settings.core_base_url}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


async def _api_post(path: str, json_data: dict | None = None) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=_RUN_TIMEOUT) as client:
            resp = await client.post(f"{settings.core_base_url}{path}", json=json_data)
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


def _ago(dt_str: str | None) -> str:
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


# -- /agents ------------------------------------------------------------------

async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all agents with status."""
    await update.message.chat.send_action(ChatAction.TYPING)

    agents = await _api_get("/agents")
    if not agents or not isinstance(agents, list):
        await update.message.reply_text("\u26a0\ufe0f Could not fetch agents.")
        return

    lines = ["\U0001f916 *Agents*\n"]
    for a in agents:
        name = a.get("name", "?")
        enabled = a.get("enabled", False)
        icon = "\U0001f7e2" if enabled else "\U0001f534"
        model = a.get("model", "?")
        triggers = a.get("triggers", [])
        t_types = ", ".join(t.get("type", "?") for t in triggers) if triggers else "api"
        lines.append(f"{icon} `{name}` — {model}")
        lines.append(f"   Triggers: {t_types}")

    lines.append(f"\n_{len(agents)} agents total_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# -- /agent <name> ------------------------------------------------------------

async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed info on a specific agent."""
    if not context.args:
        await update.message.reply_text("Usage: `/agent <name>`", parse_mode="Markdown")
        return

    name = context.args[0]
    await update.message.chat.send_action(ChatAction.TYPING)

    agent = await _api_get(f"/agents/{name}")
    if not agent:
        await update.message.reply_text(f"\u274c Agent `{name}` not found.", parse_mode="Markdown")
        return

    icon = "\U0001f7e2" if agent.get("enabled") else "\U0001f534"
    display = agent.get("display_name") or name
    desc = agent.get("description", "No description")[:200]
    model = agent.get("model", "?")
    timeout = agent.get("timeout_seconds", "?")
    max_conc = agent.get("max_concurrent", "?")
    channels = ", ".join(agent.get("output_channels", [])) or "none"

    temp = agent.get("temperature")
    temp_str = f"{temp}" if temp is not None else "default"

    lines = [
        f"{icon} *{display}* (`{name}`)\n",
        f"\U0001f4dd {desc}\n",
        f"\U0001f9e0 Model: `{model}`",
        f"\U0001f321\ufe0f Temperature: {temp_str}",
        f"\u23f1 Timeout: {timeout}s | Max concurrent: {max_conc}",
        f"\U0001f4e4 Output: {channels}",
    ]

    # Triggers
    triggers = agent.get("triggers", [])
    if triggers:
        lines.append("\n\U0001f50c *Triggers:*")
        for t in triggers:
            t_type = t.get("type", "?")
            if t_type == "mqtt":
                lines.append(f"  \u2022 MQTT: `{t.get('topic', '?')}`")
            elif t_type == "schedule":
                cron = t.get("cron")
                interval = t.get("interval_seconds")
                if cron:
                    lines.append(f"  \u2022 Cron: `{cron}`")
                elif interval:
                    lines.append(f"  \u2022 Every {interval}s")
            elif t_type == "event":
                lines.append(f"  \u2022 Event: `{t.get('event_type', '?')}`")
            else:
                lines.append(f"  \u2022 {t_type}")

    # Tools
    tools = agent.get("tools", [])
    if tools:
        tool_names = ", ".join(f"`{t.get('name', '?')}`" for t in tools)
        lines.append(f"\n\U0001f527 Tools: {tool_names}")

    # Recent runs
    runs = await _api_get(f"/agents/{name}/runs", params={"limit": 3})
    if runs and isinstance(runs, list) and runs:
        lines.append("\n\U0001f4ca *Recent runs:*")
        for r in runs:
            status = r.get("status", "?")
            s_icon = {"completed": "\u2705", "failed": "\u274c", "timeout": "\u23f3",
                       "running": "\U0001f504", "pending": "\u23f3"}.get(status, "\u2753")
            dur = r.get("duration_seconds")
            dur_str = f" ({dur:.1f}s)" if dur else ""
            trigger = r.get("trigger_type", "?")
            started = _ago(r.get("started_at"))
            lines.append(f"  {s_icon} {trigger} — {started}{dur_str}")

    # Action buttons
    buttons = []
    if agent.get("enabled"):
        buttons.append(InlineKeyboardButton("\u25b6 Run", callback_data=f"agent_run:{name}"))
        buttons.append(InlineKeyboardButton("\u23f8 Disable", callback_data=f"agent_disable:{name}"))
    else:
        buttons.append(InlineKeyboardButton("\u25b6 Enable", callback_data=f"agent_enable:{name}"))
    buttons.append(InlineKeyboardButton("\U0001f4ca Runs", callback_data=f"agent_runs:{name}"))

    keyboard = InlineKeyboardMarkup([buttons])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=keyboard)


# -- /run <name> [input] -----------------------------------------------------

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger an agent run."""
    if not context.args:
        await update.message.reply_text("Usage: `/run <name> [input text]`", parse_mode="Markdown")
        return

    name = context.args[0]
    input_text = " ".join(context.args[1:]) if len(context.args) > 1 else None

    msg = await update.message.reply_text(f"\U0001f504 Running `{name}`...", parse_mode="Markdown")

    payload = {"input": {"message": input_text}} if input_text else {}
    result = await _api_post(f"/agents/{name}/run", json_data=payload)

    if not result:
        await msg.edit_text(f"\u274c Failed to trigger `{name}`.", parse_mode="Markdown")
        return

    run_id = result.get("id", "?")
    await msg.edit_text(
        f"\u2705 Agent `{name}` run #{run_id} started.\n"
        f"Use `/runs {name}` to check results.",
        parse_mode="Markdown",
    )


# -- /enable <name> -----------------------------------------------------------

async def cmd_enable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enable an agent."""
    if not context.args:
        await update.message.reply_text("Usage: `/enable <name>`", parse_mode="Markdown")
        return

    name = context.args[0]
    result = await _api_post(f"/agents/{name}/enable")
    if result:
        await update.message.reply_text(f"\U0001f7e2 Agent `{name}` enabled.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"\u274c Failed to enable `{name}`.", parse_mode="Markdown")


# -- /disable <name> ----------------------------------------------------------

async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disable an agent."""
    if not context.args:
        await update.message.reply_text("Usage: `/disable <name>`", parse_mode="Markdown")
        return

    name = context.args[0]
    result = await _api_post(f"/agents/{name}/disable")
    if result:
        await update.message.reply_text(f"\U0001f534 Agent `{name}` disabled.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"\u274c Failed to disable `{name}`.", parse_mode="Markdown")


# -- /runs [name] -------------------------------------------------------------

async def cmd_runs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent agent runs, optionally filtered by agent name."""
    await update.message.chat.send_action(ChatAction.TYPING)

    if context.args:
        name = context.args[0]
        runs = await _api_get(f"/agents/{name}/runs", params={"limit": 10})
        title = f"\U0001f4ca *Runs for* `{name}`"
    else:
        runs = await _api_get("/agents/runs", params={"limit": 15})
        title = "\U0001f4ca *Recent Agent Runs*"

    if not runs or not isinstance(runs, list):
        await update.message.reply_text("\u26a0\ufe0f Could not fetch runs.")
        return

    if not runs:
        await update.message.reply_text(f"{title}\n\nNo runs found.", parse_mode="Markdown")
        return

    lines = [f"{title}\n"]
    for r in runs:
        status = r.get("status", "?")
        s_icon = {"completed": "\u2705", "failed": "\u274c", "timeout": "\u23f3",
                   "running": "\U0001f504", "pending": "\u23f3"}.get(status, "\u2753")
        agent = r.get("agent_name", "?")
        trigger = r.get("trigger_type", "?")
        dur = r.get("duration_seconds")
        dur_str = f" ({dur:.1f}s)" if dur else ""
        started = _ago(r.get("started_at"))
        lines.append(f"{s_icon} `{agent}` \u2014 {trigger} \u2014 {started}{dur_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# -- /schedule ----------------------------------------------------------------

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show upcoming scheduled agent runs."""
    await update.message.chat.send_action(ChatAction.TYPING)

    jobs = await _api_get("/agents/schedule")
    if not jobs or not isinstance(jobs, list):
        await update.message.reply_text("\u26a0\ufe0f Could not fetch schedule.")
        return

    if not jobs:
        await update.message.reply_text("\U0001f4c5 No scheduled jobs.")
        return

    lines = ["\U0001f4c5 *Scheduled Agent Jobs*\n"]
    for j in jobs:
        agent = j.get("agent_name", "?")
        cron = j.get("cron")
        interval = j.get("interval_seconds")
        next_run = j.get("next_run_time", "?")
        if isinstance(next_run, str) and len(next_run) > 19:
            next_run = next_run[:19]

        if cron:
            lines.append(f"\u23f0 `{agent}` \u2014 cron: `{cron}`")
        elif interval:
            lines.append(f"\U0001f501 `{agent}` \u2014 every {interval}s")
        else:
            lines.append(f"\U0001f4c5 `{agent}`")
        lines.append(f"   Next: {next_run}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# -- Inline keyboard callback handler ----------------------------------------

async def handle_agent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses for agent actions."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""

    if data.startswith("agent_run:"):
        name = data.split(":", 1)[1]
        result = await _api_post(f"/agents/{name}/run")
        if result:
            await query.edit_message_text(
                f"\U0001f504 Running `{name}`... (run #{result.get('id', '?')})\n"
                f"Use `/runs {name}` to check results.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(f"\u274c Failed to trigger `{name}`.", parse_mode="Markdown")

    elif data.startswith("agent_enable:"):
        name = data.split(":", 1)[1]
        result = await _api_post(f"/agents/{name}/enable")
        if result:
            await query.edit_message_text(f"\U0001f7e2 Agent `{name}` enabled.", parse_mode="Markdown")
        else:
            await query.edit_message_text(f"\u274c Failed to enable `{name}`.", parse_mode="Markdown")

    elif data.startswith("agent_disable:"):
        name = data.split(":", 1)[1]
        result = await _api_post(f"/agents/{name}/disable")
        if result:
            await query.edit_message_text(f"\U0001f534 Agent `{name}` disabled.", parse_mode="Markdown")
        else:
            await query.edit_message_text(f"\u274c Failed to disable `{name}`.", parse_mode="Markdown")

    elif data.startswith("agent_runs:"):
        name = data.split(":", 1)[1]
        runs = await _api_get(f"/agents/{name}/runs", params={"limit": 5})
        if runs and isinstance(runs, list):
            lines = [f"\U0001f4ca *Runs for* `{name}`\n"]
            for r in runs:
                status = r.get("status", "?")
                s_icon = {"completed": "\u2705", "failed": "\u274c"}.get(status, "\u2753")
                dur = r.get("duration_seconds")
                dur_str = f" ({dur:.1f}s)" if dur else ""
                lines.append(f"{s_icon} {r.get('trigger_type', '?')} — {_ago(r.get('started_at'))}{dur_str}")
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
        else:
            await query.edit_message_text(f"No runs found for `{name}`.", parse_mode="Markdown")
