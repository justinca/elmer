"""Radio Control — SDR Console band scanner and radio status.

Shows current frequency/mode, band scanner status with controls,
scan order with activity indicators, and a dwell time slider.
"""

import streamlit as st

from api_client import ElmerAPI

_BAND_ORDER = ["10m", "12m", "15m", "17m", "20m", "40m", "80m"]
_COND_COLOR = {"good": "#00CC96", "fair": "#FFA15A", "poor": "#EF553B"}
_COND_BG = {"good": "rgba(0,204,150,0.15)", "fair": "rgba(255,161,90,0.15)", "poor": "rgba(239,85,59,0.15)"}


def render() -> None:
    st.header("Radio Control")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # -- Radio status row --------------------------------------------------
    radio = api.get_radio_status()

    st.subheader("SDR Console")
    if radio is None:
        st.warning("Could not reach Worker — is it running?")
    else:
        c1, c2, c3, c4 = st.columns(4)
        connected = radio.get("connected", False)
        freq = radio.get("frequency_hz") or 0
        mode = radio.get("mode") or "?"
        rig = radio.get("rig_type", "?")

        with c1:
            color = "#00CC96" if connected else "#EF553B"
            label = "Connected" if connected else "Disconnected"
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.05);padding:8px 12px;'
                f'border-radius:4px;border-left:4px solid {color};">'
                f'<small style="color:#888;">Status</small><br>'
                f'<b style="color:{color};">{label}</b></div>',
                unsafe_allow_html=True,
            )
            if not connected:
                if st.button("Connect", key="cat_connect", type="primary"):
                    api.radio_connect()
                    st.rerun()
        with c2:
            freq_display = f"{freq / 1_000_000:.6f} MHz" if freq else "---"
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.05);padding:8px 12px;'
                f'border-radius:4px;border-left:4px solid #636EFA;">'
                f'<small style="color:#888;">Frequency</small><br>'
                f'<b>{freq_display}</b></div>',
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.05);padding:8px 12px;'
                f'border-radius:4px;border-left:4px solid #636EFA;">'
                f'<small style="color:#888;">Mode</small><br>'
                f'<b>{mode}</b></div>',
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.05);padding:8px 12px;'
                f'border-radius:4px;border-left:4px solid #636EFA;">'
                f'<small style="color:#888;">Rig</small><br>'
                f'<b>{rig}</b></div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # -- Band Scanner section ----------------------------------------------
    st.subheader("Band Scanner")
    scanner = api.get_scanner_status()

    if scanner is None:
        st.warning("Could not reach scanner service.")
        return

    scanning = scanner.get("scanning", False)
    paused = scanner.get("paused", False)
    current_band = scanner.get("current_band", "")
    current_freq = scanner.get("current_frequency", 0)
    remaining = scanner.get("time_remaining", 0)
    scan_order = scanner.get("scan_order", [])
    dwell = scanner.get("dwell_seconds", 900)
    cycles = scanner.get("cycle_count", 0)
    is_day = scanner.get("is_daytime", True)

    # Status indicator.
    if scanning and not paused:
        status_html = (
            '<span style="background:rgba(0,204,150,0.15);color:#00CC96;'
            'padding:2px 10px;border-radius:3px;font-weight:600;">'
            'Scanning</span>'
        )
    elif scanning and paused:
        status_html = (
            '<span style="background:rgba(255,161,90,0.15);color:#FFA15A;'
            'padding:2px 10px;border-radius:3px;font-weight:600;">'
            'Paused</span>'
        )
    else:
        status_html = (
            '<span style="background:rgba(136,136,136,0.15);color:#888;'
            'padding:2px 10px;border-radius:3px;font-weight:600;">'
            'Stopped</span>'
        )

    time_mode = "Daytime" if is_day else "Nighttime"

    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(f"**Status:** {status_html}", unsafe_allow_html=True)
    s2.markdown(f"**Mode:** {time_mode}")
    s3.markdown(f"**Cycles:** {cycles}")
    if scanning:
        mins, secs = divmod(remaining, 60)
        s4.markdown(f"**Remaining:** {mins}m {secs:02d}s")

    # Control buttons.
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if not scanning:
            if st.button("Start", type="primary", key="scan_start", use_container_width=True):
                api.scanner_start()
                st.rerun()
        else:
            if st.button("Stop", type="secondary", key="scan_stop", use_container_width=True):
                api.scanner_stop()
                st.rerun()
    with b2:
        if scanning and not paused:
            if st.button("Pause", key="scan_pause", use_container_width=True):
                api.scanner_pause()
                st.rerun()
        elif scanning and paused:
            if st.button("Resume", type="primary", key="scan_resume", use_container_width=True):
                api.scanner_resume()
                st.rerun()
    with b3:
        if scanning:
            if st.button("Next Band", key="scan_next", use_container_width=True):
                api.scanner_next()
                st.rerun()
    with b4:
        pass  # spacer

    # Dwell time slider.
    new_dwell = st.select_slider(
        "Dwell time",
        options=[60, 120, 300, 600, 900, 1200, 1800],
        value=dwell,
        format_func=lambda x: f"{x // 60}m" if x >= 60 else f"{x}s",
        key="dwell_slider",
    )
    if new_dwell != dwell:
        api.scanner_dwell(new_dwell)

    st.divider()

    # -- Scan order with activity indicators -------------------------------
    if scan_order:
        st.subheader("Scan Order")

        # Fetch spot summary for activity indicators.
        spot_summary = api.get_dx_summary()
        spot_counts: dict[str, int] = {}
        if spot_summary and isinstance(spot_summary, dict):
            spot_counts = spot_summary.get("bands", spot_summary)

        # Fetch propagation for condition badges.
        prop = api.get_propagation_bands()
        band_conditions: dict = {}
        if prop and isinstance(prop, dict):
            band_conditions = prop.get("bands", prop)

        # Header row.
        hdr = st.columns([1.2, 1.5, 1.5, 1.5, 1])
        hdr[0].markdown("**Band**")
        hdr[1].markdown("**Frequency**")
        hdr[2].markdown("**Condition**")
        hdr[3].markdown("**Spots**")
        hdr[4].markdown("**Status**")

        for band in scan_order:
            cols = st.columns([1.2, 1.5, 1.5, 1.5, 1])

            # Band name (highlight current).
            if band == current_band and scanning:
                cols[0].markdown(f"**{band}** \u25c0")
            else:
                cols[0].markdown(f"{band}")

            # Frequency.
            freq_map = {
                "10m": "28.074", "12m": "24.915", "15m": "21.074",
                "17m": "18.100", "20m": "14.074", "40m": "7.074", "80m": "3.573",
            }
            cols[1].markdown(f"`{freq_map.get(band, '?')} MHz`")

            # Condition badge.
            bc = band_conditions.get(band, {})
            cond = bc.get("day", "?") if is_day else bc.get("night", "?")
            cond_lower = cond.lower() if isinstance(cond, str) else "?"
            color = _COND_COLOR.get(cond_lower, "#636EFA")
            bg = _COND_BG.get(cond_lower, "rgba(99,110,250,0.15)")
            cols[2].markdown(
                f'<span style="background:{bg};color:{color};padding:2px 8px;'
                f'border-radius:3px;font-weight:600;font-size:0.85em;">'
                f'{cond}</span>',
                unsafe_allow_html=True,
            )

            # Spot count.
            count = spot_counts.get(band, 0) if isinstance(spot_counts, dict) else 0
            if isinstance(count, int) and count > 0:
                bar_len = min(count, 20)
                bar = "\u2588" * (bar_len // 4 + 1)
                cols[3].markdown(f"{count} {bar}")
            else:
                cols[3].caption("---")

            # Status indicator.
            if band == current_band and scanning:
                if paused:
                    cols[4].markdown("\u23f8\ufe0f Paused")
                else:
                    cols[4].markdown("\u25b6\ufe0f Active")
            else:
                cols[4].caption("\u2014")
