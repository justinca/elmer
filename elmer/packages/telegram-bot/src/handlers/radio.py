"""Radio intelligence commands for the Elmer Telegram Bot.

Commands:
  /prop       — current propagation summary (one-liner per band)
  /bands      — band conditions grid (compact, mobile-friendly)
  /solar      — solar indices (SFI, SSN, K-index, flare status)
  /spots      — recent DX spots, optional [band] [mode] filters
  /dx <call>  — DXCC entity lookup for a callsign
  /needs      — show needs list
  /need       — add entity to needs list: /need <entity> [band] [mode]
  /pota       — POTA spots or park info: /pota [park_id]
  /plan       — activation plan: /plan <park_id>
  /log        — recent QSO summary: /log [days]
  /dxcc       — DXCC award progress
  /contest    — upcoming contests or current contest status
"""

import logging

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger("elmer.telegram.radio")

_TIMEOUT = 10.0
_LONG_TIMEOUT = 30.0

_COND_EMOJI = {"good": "\U0001f7e2", "fair": "\U0001f7e1", "poor": "\U0001f534"}
_BAND_ORDER = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]


async def _api_get(path: str, params: dict | None = None,
                   timeout: float = _TIMEOUT) -> dict | list | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{settings.core_base_url}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


async def _api_post(path: str, json_data: dict | None = None) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{settings.core_base_url}{path}", json=json_data)
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


async def _api_delete(path: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(f"{settings.core_base_url}{path}")
            resp.raise_for_status()
            return resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Core API error (%s): %s", path, exc)
        return None


def _cond(text: str) -> str:
    """Condition text to emoji."""
    return _COND_EMOJI.get(text.lower(), "\u2753") + " " + text


# ── /prop ────────────────────────────────────────────────────────────────


async def cmd_prop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/prop — one-liner propagation summary per band."""
    await update.message.chat.send_action(ChatAction.TYPING)
    data = await _api_get("/propagation")
    if not data:
        await update.message.reply_text("\u26a0\ufe0f Could not fetch propagation data.")
        return

    bands = data.get("bands", {})
    sfi = data.get("solar_flux", "?")
    k = data.get("k_index")
    k_str = f"{k:.1f}" if k is not None else "?"

    lines = [f"\U0001f4e1 *Propagation* (SFI {sfi} / K {k_str})"]
    lines.append("")
    for b in _BAND_ORDER:
        bc = bands.get(b)
        if not bc:
            continue
        day = bc.get("day", "?")
        night = bc.get("night", "?")
        lines.append(f"`{b:>4}` Day: {_cond(day)} | Night: {_cond(night)}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /bands ───────────────────────────────────────────────────────────────


async def cmd_bands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/bands — compact band conditions grid."""
    await update.message.chat.send_action(ChatAction.TYPING)
    data = await _api_get("/propagation")
    if not data:
        await update.message.reply_text("\u26a0\ufe0f Could not fetch band data.")
        return

    bands = data.get("bands", {})

    # Compact grid: band | day emoji | night emoji.
    lines = ["\U0001f4e1 *Band Conditions*"]
    lines.append("`Band  Day   Night`")
    lines.append("`" + "-" * 18 + "`")
    for b in _BAND_ORDER:
        bc = bands.get(b)
        if not bc:
            continue
        d = _COND_EMOJI.get(bc.get("day", "").lower(), "\u2753")
        n = _COND_EMOJI.get(bc.get("night", "").lower(), "\u2753")
        lines.append(f"`{b:>4}`  {d}     {n}")

    # Legend.
    lines.append("")
    lines.append("\U0001f7e2 Good  \U0001f7e1 Fair  \U0001f534 Poor")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /solar ───────────────────────────────────────────────────────────────


async def cmd_solar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/solar — solar indices."""
    await update.message.chat.send_action(ChatAction.TYPING)
    data = await _api_get("/propagation")
    if not data:
        await update.message.reply_text("\u26a0\ufe0f Could not fetch solar data.")
        return

    sfi = data.get("solar_flux", "?")
    ssn = data.get("sunspot_number", "?")
    a = data.get("a_index", "?")
    k = data.get("k_index")
    k_str = f"{k:.1f}" if k is not None else "?"
    xray = data.get("x_ray_flux", "?")
    storm = data.get("geomag_storm", "None")
    field = data.get("geomag_field", "?")
    wind = data.get("solar_wind")
    wind_str = f"{wind:.0f} km/s" if wind else "?"

    # K-index emoji.
    if k is not None:
        if k < 3:
            k_emoji = "\U0001f7e2"
        elif k <= 5:
            k_emoji = "\U0001f7e1"
        else:
            k_emoji = "\U0001f534"
    else:
        k_emoji = ""

    lines = [
        "\u2600\ufe0f *Solar Conditions*",
        "",
        f"SFI: *{sfi}*",
        f"Sunspot Number: *{ssn}*",
        f"A-Index: *{a}*",
        f"K-Index: *{k_str}* {k_emoji}",
        f"X-Ray Flux: *{xray}*",
        f"Geomag Storm: *{storm}*",
        f"Geomag Field: *{field}*",
        f"Solar Wind: *{wind_str}*",
    ]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /spots ───────────────────────────────────────────────────────────────


async def cmd_spots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/spots [band] [mode] — recent DX spots."""
    await update.message.chat.send_action(ChatAction.TYPING)

    args = context.args or []
    params: dict = {"limit": 15}
    for arg in args:
        a = arg.upper()
        if a in ("CW", "SSB", "FT8", "FT4", "RTTY", "AM"):
            params["mode"] = a
        elif a.endswith("M") and a[:-1].isdigit():
            params["band"] = arg.lower()

    spots = await _api_get("/dx/spots", params=params)
    if not spots or not isinstance(spots, list):
        await update.message.reply_text("No DX spots found.")
        return

    # Also load needs for highlighting.
    needs = await _api_get("/dx/needs")
    need_entities = set()
    if isinstance(needs, list):
        need_entities = {n.get("entity", "").lower() for n in needs}

    lines = [f"\U0001f4e1 *DX Spots* ({len(spots)})"]
    for s in spots[:15]:
        dx = s.get("dx_call", "?")
        freq = s.get("frequency", 0)
        band = s.get("band", "?")
        mode = s.get("mode", "?")
        entity = s.get("dx_entity", "")
        ts = (s.get("timestamp") or "")
        time_str = ts[11:16] if len(ts) > 11 else ""

        is_needed = entity.lower() in need_entities if entity else False
        prefix = "\U0001f534 " if is_needed else ""

        line = f"`{time_str}` {prefix}*{dx}* {freq:.1f} {band} {mode}"
        if entity:
            line += f" ({entity})"
        if is_needed:
            line += " *NEED*"
        lines.append(line)

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /dx ──────────────────────────────────────────────────────────────────


async def cmd_dx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/dx <callsign> — DXCC entity lookup."""
    if not context.args:
        await update.message.reply_text("Usage: `/dx JA1ABC`", parse_mode="Markdown")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    call = context.args[0].upper()
    result = await _api_get(f"/dx/entities/{call}")
    if not result:
        await update.message.reply_text(f"No DXCC entity found for `{call}`.",
                                        parse_mode="Markdown")
        return

    lines = [
        f"\U0001f50d *{call}*",
        "",
        f"Entity: *{result.get('entity_name', '?')}*",
        f"Prefix: `{result.get('prefix', '?')}`",
        f"Continent: *{result.get('continent', '?')}*",
        f"CQ Zone: {result.get('cq_zone', '?')}",
        f"ITU Zone: {result.get('itu_zone', '?')}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /needs ───────────────────────────────────────────────────────────────


async def cmd_needs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/needs — show needs list."""
    await update.message.chat.send_action(ChatAction.TYPING)
    needs = await _api_get("/dx/needs")
    if not needs or not isinstance(needs, list):
        await update.message.reply_text("Needs list is empty.")
        return

    lines = [f"\U0001f4cb *Needs List* ({len(needs)})"]
    for n in sorted(needs, key=lambda x: x.get("priority", 5)):
        p = n.get("priority", 5)
        entity = n.get("entity", "?")
        band = n.get("band") or "Any"
        mode = n.get("mode") or "Any"
        lines.append(f"P{p} *{entity}* — {band}/{mode}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /need ────────────────────────────────────────────────────────────────


async def cmd_need(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/need <entity> [band] [mode] — add to needs list."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: `/need Bouvet Island` or `/need Japan 20m CW`",
            parse_mode="Markdown",
        )
        return

    # Parse: first arg(s) are entity, optional band and mode at end.
    band = None
    mode = None
    entity_parts = []

    for arg in args:
        a = arg.upper()
        if a in ("CW", "SSB", "FT8", "FT4", "RTTY"):
            mode = a
        elif a.endswith("M") and a[:-1].isdigit():
            band = arg.lower()
        else:
            entity_parts.append(arg)

    entity = " ".join(entity_parts)
    if not entity:
        await update.message.reply_text("Please specify an entity name.")
        return

    payload = {"entity": entity, "priority": 3}
    if band:
        payload["band"] = band
    if mode:
        payload["mode"] = mode

    result = await _api_post("/dx/needs", json_data=payload)
    if result:
        parts = [f"Added *{entity}*"]
        if band:
            parts.append(f"on {band}")
        if mode:
            parts.append(mode)
        parts.append("to needs list.")
        await update.message.reply_text(
            "\u2705 " + " ".join(parts), parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("\u274c Failed to add need.")


# ── /pota ────────────────────────────────────────────────────────────────


async def cmd_pota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pota [park_id] — POTA spots or park info."""
    await update.message.chat.send_action(ChatAction.TYPING)

    if context.args:
        # Park info mode.
        park_id = context.args[0].upper()
        park = await _api_get(f"/pota/park/{park_id}", timeout=_LONG_TIMEOUT)
        if not park:
            await update.message.reply_text(f"Park `{park_id}` not found.",
                                            parse_mode="Markdown")
            return

        lines = [
            f"\U0001f3d5\ufe0f *{park.get('reference', '?')} — {park.get('name', '?')}*",
            "",
            f"Type: {park.get('park_type', '?')}",
            f"Location: {park.get('location_name', park.get('location_desc', '?'))}",
            f"Grid: `{park.get('grid4', '?')}`",
            f"Activations: {park.get('activations', 0)}",
            f"QSOs: {park.get('contacts', 0):,}",
        ]
        if park.get("first_activator"):
            lines.append(f"First: {park['first_activator']} ({park.get('first_activation_date', '?')})")
        if park.get("website"):
            lines.append(f"Web: {park['website']}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # Current spots mode.
    spots = await _api_get("/pota/spots", timeout=_LONG_TIMEOUT)
    if not spots or not isinstance(spots, list):
        await update.message.reply_text("No active POTA spots.")
        return

    lines = [f"\U0001f3d5\ufe0f *POTA Spots* ({len(spots)})"]
    for s in spots[:12]:
        act = s.get("activator", "?")
        ref = s.get("reference", "")
        freq = s.get("frequency", "")
        mode = s.get("mode", "")
        park = s.get("park_name", "")[:25]
        lines.append(f"*{act}* @ `{ref}` {freq} {mode}\n  _{park}_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /plan ────────────────────────────────────────────────────────────────


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/plan <park_id> — quick activation plan."""
    if not context.args:
        await update.message.reply_text("Usage: `/plan US-1228`", parse_mode="Markdown")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    park_id = context.args[0].upper()
    plan = await _api_get(f"/pota/plan/{park_id}", timeout=_LONG_TIMEOUT)
    if not plan:
        await update.message.reply_text(f"Could not plan for `{park_id}`.",
                                        parse_mode="Markdown")
        return

    park = plan.get("park", {})
    lines = [
        f"\U0001f3d5\ufe0f *Activation Plan: {park.get('reference', '?')}*",
        f"_{park.get('name', '?')}_",
        "",
        f"\U0001f4cd {plan.get('distance_miles', 0)} mi / {plan.get('bearing', 0):.0f}\u00b0",
        f"\U0001f4e1 Activations: {park.get('activations', 0)} | QSOs: {park.get('contacts', 0):,}",
    ]

    recs = plan.get("band_recommendations", [])
    if recs:
        lines.append("")
        lines.append("*Band Recommendations:*")
        for r in recs[:4]:
            cond = r.get("condition", "?")
            emoji = _COND_EMOJI.get(cond.lower(), "")
            lines.append(
                f"  {emoji} *{r.get('band', '?')}* {r.get('mode', '')} "
                f"({r.get('time_window', '')}) — {cond}"
            )

    nearby = plan.get("nearby_parks", [])
    if nearby:
        lines.append("")
        lines.append(f"*Nearby:* {len(nearby)} parks within 30 mi")
        for n in nearby[:3]:
            dist = n.get("distance_miles")
            dist_str = f"{dist:.1f} mi" if dist is not None else "?"
            lines.append(f"  `{n.get('reference', '')}` {n.get('name', '')[:20]} ({dist_str})")

    notes = plan.get("notes", [])
    if notes:
        lines.append("")
        for note in notes[:3]:
            lines.append(f"\u2022 {note}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /log ─────────────────────────────────────────────────────────────────


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/log [days] — recent QSO summary."""
    await update.message.chat.send_action(ChatAction.TYPING)

    stats = await _api_get("/log/stats")
    if not stats:
        await update.message.reply_text("\u26a0\ufe0f Log4OM data not available.")
        return

    total = stats.get("total_qsos", 0)
    countries = stats.get("unique_countries", 0)

    lines = [
        "\U0001f4d3 *Log Summary*",
        "",
        f"Total QSOs: *{total:,}*",
        f"Countries: *{countries}*",
    ]

    by_band = stats.get("qsos_by_band", {})
    if by_band:
        lines.append("")
        lines.append("*By Band:*")
        for b in _BAND_ORDER:
            count = by_band.get(b)
            if count:
                lines.append(f"  `{b:>4}` {count:,}")

    by_mode = stats.get("qsos_by_mode", {})
    if by_mode:
        lines.append("")
        lines.append("*By Mode:*")
        for mode, count in sorted(by_mode.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  `{mode:>5}` {count:,}")

    first = (stats.get("first_qso") or "")[:10]
    last = (stats.get("last_qso") or "")[:10]
    if first:
        lines.append(f"\nSpan: {first} to {last}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /dxcc ────────────────────────────────────────────────────────────────


async def cmd_dxcc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/dxcc — DXCC award progress."""
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _api_get("/log/dxcc")
    entities = data if isinstance(data, list) else (
        data.get("entities", []) if data else []
    )

    if not entities:
        await update.message.reply_text("No DXCC data available.")
        return

    # Count by mode.
    all_e = set()
    cw_e = set()
    ssb_e = set()
    digi_e = set()

    for e in entities:
        c = e.get("country", "?")
        all_e.add(c)
        for m in e.get("modes_worked", []):
            mu = m.upper()
            if mu == "CW":
                cw_e.add(c)
            elif mu in ("SSB", "AM", "FM"):
                ssb_e.add(c)
            elif mu in ("FT8", "FT4", "RTTY", "JT65", "PSK31"):
                digi_e.add(c)

    # Continent breakdown.
    conts: dict[str, int] = {}
    for e in entities:
        cont = e.get("continent", "?")
        if cont:
            conts[cont] = conts.get(cont, 0) + 1

    def bar(count: int, target: int = 100) -> str:
        filled = min(count * 10 // target, 10)
        return "\u2588" * filled + "\u2591" * (10 - filled)

    lines = [
        "\U0001f3c6 *DXCC Progress*",
        "",
        f"Mixed:   `{bar(len(all_e))}` {len(all_e)}/100",
        f"Phone:   `{bar(len(ssb_e))}` {len(ssb_e)}/100",
        f"CW:      `{bar(len(cw_e))}` {len(cw_e)}/100",
        f"Digital: `{bar(len(digi_e))}` {len(digi_e)}/100",
        "",
        "*By Continent:*",
    ]
    for cont in ["NA", "SA", "EU", "AF", "AS", "OC"]:
        count = conts.get(cont, 0)
        if count:
            lines.append(f"  {cont}: {count}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /contest ─────────────────────────────────────────────────────────────


async def cmd_contest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/contest — upcoming contests."""
    await update.message.chat.send_action(ChatAction.TYPING)

    contests = await _api_get("/contest/upcoming", params={"days": 60})
    if not contests or not isinstance(contests, list):
        await update.message.reply_text("No upcoming contests.")
        return

    lines = [f"\U0001f3c6 *Upcoming Contests* ({len(contests)})"]
    for c in contests[:8]:
        name = c.get("full_name", c.get("name", "?"))
        start = (c.get("start_utc", "") or "")[:10]
        mode = c.get("mode", "")
        is_major = c.get("is_major", False)
        star = " \u2b50" if is_major else ""

        lines.append(f"\n*{name}*{star}")
        lines.append(f"  {start} | {mode}")
        exchange = c.get("exchange", "")
        if exchange:
            lines.append(f"  Exchange: {exchange}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
