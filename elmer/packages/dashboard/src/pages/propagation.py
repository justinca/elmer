"""Propagation — ham radio mission control.

Solar conditions, HF band status, 7-day history, and forecast.
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from api_client import ElmerAPI

_BAND_ORDER = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]

_COND_COLOR = {"good": "#00CC96", "fair": "#FFA15A", "poor": "#EF553B"}
_COND_BG = {"good": "rgba(0,204,150,0.15)", "fair": "rgba(255,161,90,0.15)", "poor": "rgba(239,85,59,0.15)"}


def render() -> None:
    st.header("Propagation")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()
    data = api.get_propagation()

    if data is None:
        st.warning("Could not reach propagation service. Is Core API running?")
        return

    # ── Solar Conditions Cards ───────────────────────────────────────────
    forecast = api.get_propagation_forecast()
    sfi_trend = _trend_arrow(forecast.get("solar_flux_trend", "")) if forecast else ""
    k_trend = _trend_arrow(forecast.get("k_index_trend", "")) if forecast else ""

    st.subheader("Solar Conditions")

    c1, c2, c3, c4, c5 = st.columns(5)

    sfi = data.get("solar_flux")
    c1.metric("Solar Flux (SFI)", f"{sfi:.0f}" if sfi else "—", delta=sfi_trend or None)

    ssn = data.get("sunspot_number")
    c2.metric("Sunspot Number", ssn if ssn is not None else "—")

    a_idx = data.get("a_index")
    k_idx = data.get("k_index")
    c3.metric("A-Index", a_idx if a_idx is not None else "—")

    k_display = f"{k_idx:.1f}" if k_idx is not None else "—"
    c4.metric("K-Index", k_display, delta=k_trend or None)

    xray = data.get("x_ray_flux") or "—"
    c5.metric("X-Ray / Flare", xray)

    # K-index color bar.
    if k_idx is not None:
        if k_idx < 3:
            k_color, k_label = "#00CC96", "Quiet"
        elif k_idx <= 5:
            k_color, k_label = "#FFA15A", "Unsettled"
        else:
            k_color, k_label = "#EF553B", "Storm"
        st.markdown(
            f'<div style="background:{k_color};color:#111;padding:4px 12px;'
            f'border-radius:4px;display:inline-block;font-weight:bold;font-size:0.85em;">'
            f'K={k_idx:.1f} — {k_label}</div>',
            unsafe_allow_html=True,
        )

    # Secondary row.
    c6, c7, c8, c9, c10 = st.columns(5)
    storm = data.get("geomag_storm") or "None"
    c6.metric("Geomag Storm", storm)
    c7.metric("Geomag Field", data.get("geomag_field") or "—")
    c8.metric("Signal Noise", data.get("signal_noise") or "—")

    wind = data.get("solar_wind")
    c9.metric("Solar Wind", f"{wind:.0f} km/s" if wind else "—")

    mag = data.get("magnetic_field")
    c10.metric("Bz (nT)", f"{mag:.1f}" if mag is not None else "—")

    st.divider()

    # ── Band Conditions Grid ─────────────────────────────────────────────

    st.subheader("HF Band Conditions")

    bands = data.get("bands", {})
    if bands:
        _render_band_grid(bands)
    else:
        st.info("No band condition data available yet.")

    st.divider()

    # ── D-RAP & VHF ──────────────────────────────────────────────────────

    col_drap, col_vhf = st.columns(2)

    with col_drap:
        drap = data.get("drap", {})
        if drap:
            st.subheader("D-Region Absorption")
            max_haf = drap.get("max_haf_mhz", 0)
            active = drap.get("absorption_active", False)
            if active:
                st.warning(f"Absorption active — HAF: {max_haf} MHz")
            else:
                st.success(f"Normal — Max HAF: {max_haf} MHz")
            xray_msg = drap.get("xray_message", "")
            proton_msg = drap.get("proton_message", "")
            if xray_msg:
                st.caption(f"X-Ray: {xray_msg}")
            if proton_msg:
                st.caption(f"Proton: {proton_msg}")

    with col_vhf:
        vhf = data.get("vhf", [])
        if vhf:
            st.subheader("VHF Conditions")
            for v in vhf:
                name = v.get("name", "?")
                loc = v.get("location", "").replace("_", " ")
                status = v.get("status", "?")
                st.caption(f"**{name}** ({loc}): {status}")

    st.divider()

    # ── 7-Day History Chart ──────────────────────────────────────────────

    st.subheader("7-Day Propagation History")
    history = api.get_propagation_history(hours=168)
    if history:
        _render_history_chart(history)
    else:
        st.info("No historical data yet. Data is collected every 15 minutes.")

    st.divider()

    # ── Forecast ─────────────────────────────────────────────────────────

    st.subheader("Forecast")
    if forecast:
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown("**Geomagnetic Field**")
            st.caption(forecast.get("geomag_field", "—"))
        with fc2:
            st.markdown("**Signal Noise Level**")
            st.caption(forecast.get("signal_noise", "—"))
        muf = forecast.get("muf")
        if muf and muf != "NoRpt":
            st.caption(f"MUF: {muf}")
        updated = forecast.get("updated", "")
        if updated:
            st.caption(f"Forecast updated: {updated}")
    else:
        st.info("No forecast data available.")

    # ── Source status ────────────────────────────────────────────────────

    src_status = data.get("source_status", {})
    updated = data.get("updated", "")
    parts = []
    if updated:
        parts.append(f"Updated: {updated[:19]}")
    if src_status:
        for src, status in src_status.items():
            icon = "ok" if status == "ok" else "err"
            parts.append(f"{src}: {icon}")
    if parts:
        st.caption(" | ".join(parts))


# ── Helpers ──────────────────────────────────────────────────────────────


def _trend_arrow(trend: str) -> str:
    """Convert trend strings to arrow text for st.metric delta."""
    t = trend.lower().strip()
    if t in ("rising", "up", "increasing"):
        return "Rising"
    if t in ("falling", "down", "decreasing"):
        return "Falling"
    return ""


def _render_band_grid(bands: dict) -> None:
    """Render band conditions as a color-coded grid — one row per band."""
    band_names = [b for b in _BAND_ORDER if b in bands]
    if not band_names:
        return

    # Header row.
    hdr = st.columns([1.2, 2, 2])
    hdr[0].markdown("**Band**")
    hdr[1].markdown("**Day**")
    hdr[2].markdown("**Night**")

    for band in band_names:
        bc = bands[band]
        day_cond = (bc.get("day") or "—").lower()
        night_cond = (bc.get("night") or "—").lower()

        cols = st.columns([1.2, 2, 2])
        cols[0].markdown(f"**{band}**")
        cols[1].markdown(_condition_badge(bc.get("day", "—")), unsafe_allow_html=True)
        cols[2].markdown(_condition_badge(bc.get("night", "—")), unsafe_allow_html=True)


def _condition_badge(cond: str) -> str:
    """Return an HTML badge for a band condition."""
    key = cond.lower()
    color = _COND_COLOR.get(key, "#636EFA")
    bg = _COND_BG.get(key, "rgba(99,110,250,0.15)")
    return (
        f'<span style="background:{bg};color:{color};padding:2px 10px;'
        f'border-radius:3px;font-weight:600;font-size:0.9em;">'
        f'{cond}</span>'
    )


def _render_history_chart(history: list[dict]) -> None:
    """SFI and K-index over time with dual Y-axis."""
    timestamps = []
    sfi_values = []
    k_values = []

    for h in reversed(history):
        ts = h.get("timestamp", "")[:16]
        timestamps.append(ts)
        sfi_values.append(h.get("solar_flux"))
        k_values.append(h.get("k_index"))

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=timestamps, y=sfi_values,
            mode="lines",
            name="Solar Flux (SFI)",
            line=dict(color="#636EFA", width=2),
            fill="tozeroy",
            fillcolor="rgba(99,110,250,0.1)",
        ),
        secondary_y=False,
    )

    # K-index with color-coded segments.
    k_colors = []
    for k in k_values:
        if k is None:
            k_colors.append("#636EFA")
        elif k < 3:
            k_colors.append("#00CC96")
        elif k <= 5:
            k_colors.append("#FFA15A")
        else:
            k_colors.append("#EF553B")

    fig.add_trace(
        go.Bar(
            x=timestamps, y=k_values,
            name="K-Index",
            marker=dict(color=k_colors),
            opacity=0.6,
        ),
        secondary_y=True,
    )

    fig.update_layout(
        height=350,
        margin=dict(l=50, r=50, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        bargap=0.1,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title_text="SFI", secondary_y=False, showgrid=False)
    fig.update_yaxes(title_text="K-Index", secondary_y=True, range=[0, 9], showgrid=False)

    st.plotly_chart(fig, use_container_width=True)
