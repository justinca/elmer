"""Propagation page — solar conditions and HF band status."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI

_BAND_ORDER = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]

_COND_COLOR = {
    "good": "#00CC96",
    "fair": "#FFA15A",
    "poor": "#EF553B",
    "": "#636EFA",
}


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

    # -- Solar summary cards --------------------------------------------------

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Solar Flux (SFI)", data.get("solar_flux") or "—")
    c2.metric("Sunspot Number", data.get("sunspot_number") or "—")
    c3.metric("A-Index", data.get("a_index") or "—")

    k_val = data.get("k_index")
    k_display = f"{k_val:.1f}" if k_val is not None else "—"
    c4.metric("K-Index", k_display)

    xray = data.get("x_ray_flux") or "—"
    c5.metric("X-Ray Flux", xray)

    # Secondary row.
    c6, c7, c8, c9 = st.columns(4)
    storm = data.get("geomag_storm") or "None"
    c6.metric("Geomag Storm", storm)
    c7.metric("Geomag Field", data.get("geomag_field") or "—")
    c8.metric("Signal Noise", data.get("signal_noise") or "—")

    wind = data.get("solar_wind")
    c9.metric("Solar Wind", f"{wind:.0f} km/s" if wind else "—")

    st.divider()

    # -- Band conditions table ------------------------------------------------

    st.subheader("HF Band Conditions")

    bands = data.get("bands", {})
    if bands:
        _render_band_chart(bands)
    else:
        st.info("No band condition data available yet.")

    st.divider()

    # -- DRAP / VHF conditions ------------------------------------------------

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

    # -- Historical chart -----------------------------------------------------

    st.subheader("24-Hour History")
    history = api.get_propagation_history(hours=24)
    if history:
        _render_history_chart(history)
    else:
        st.info("No historical data yet. Data is collected every 15 minutes.")

    # -- Source status --------------------------------------------------------

    src_status = data.get("source_status", {})
    updated = data.get("updated", "")
    if updated:
        st.caption(f"Last updated: {updated[:19]}")
    if src_status:
        parts = []
        for src, status in src_status.items():
            icon = "ok" if status == "ok" else "err"
            parts.append(f"{src}: {icon}")
        st.caption("Sources: " + " | ".join(parts))


def _render_band_chart(bands: dict) -> None:
    """Render band conditions as a color-coded horizontal bar chart."""
    band_names = [b for b in _BAND_ORDER if b in bands]
    if not band_names:
        return

    day_colors = []
    night_colors = []
    day_labels = []
    night_labels = []

    for band in band_names:
        bc = bands[band]
        day_cond = bc.get("day", "").lower()
        night_cond = bc.get("night", "").lower()

        day_colors.append(_COND_COLOR.get(day_cond, "#636EFA"))
        night_colors.append(_COND_COLOR.get(night_cond, "#636EFA"))
        day_labels.append(bc.get("day", "—"))
        night_labels.append(bc.get("night", "—"))

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=band_names,
        x=[1] * len(band_names),
        orientation="h",
        name="Day",
        marker=dict(color=day_colors),
        text=day_labels,
        textposition="inside",
        insidetextanchor="middle",
        hovertemplate="%{y} Day: %{text}<extra></extra>",
    ))

    fig.add_trace(go.Bar(
        y=band_names,
        x=[1] * len(band_names),
        orientation="h",
        name="Night",
        marker=dict(color=night_colors),
        text=night_labels,
        textposition="inside",
        insidetextanchor="middle",
        hovertemplate="%{y} Night: %{text}<extra></extra>",
    ))

    fig.update_layout(
        barmode="stack",
        height=400,
        margin=dict(l=60, r=20, t=30, b=30),
        xaxis=dict(visible=False),
        yaxis=dict(autorange="reversed", title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white", size=14),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_history_chart(history: list[dict]) -> None:
    """Render SFI and K-index history as a line chart."""
    timestamps = []
    sfi_values = []
    k_values = []

    # History is sorted newest-first, reverse for chronological.
    for h in reversed(history):
        ts = h.get("timestamp", "")[:16]
        timestamps.append(ts)
        sfi_values.append(h.get("solar_flux"))
        k_values.append(h.get("k_index"))

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=timestamps, y=sfi_values,
        mode="lines+markers",
        name="Solar Flux (SFI)",
        line=dict(color="#636EFA", width=2),
        yaxis="y",
    ))

    fig.add_trace(go.Scatter(
        x=timestamps, y=k_values,
        mode="lines+markers",
        name="K-Index",
        line=dict(color="#EF553B", width=2),
        yaxis="y2",
    ))

    fig.update_layout(
        height=300,
        margin=dict(l=50, r=50, t=30, b=30),
        xaxis=dict(title=""),
        yaxis=dict(title="SFI", side="left", showgrid=False),
        yaxis2=dict(title="K-Index", side="right", overlaying="y",
                    range=[0, 9], showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
    )

    st.plotly_chart(fig, use_container_width=True)
