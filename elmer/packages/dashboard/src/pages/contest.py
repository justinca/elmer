"""Contests — calendar, live dashboard, history, band advisor."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("Contests")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    tab_upcoming, tab_live, tab_history, tab_advisor = st.tabs(
        ["Upcoming", "Live Dashboard", "History", "Band Advisor"]
    )

    with tab_upcoming:
        _render_upcoming(api)

    with tab_live:
        _render_live(api)

    with tab_history:
        _render_history(api)

    with tab_advisor:
        _render_advisor(api)


# ── Upcoming Contests ────────────────────────────────────────────────────


def _render_upcoming(api: ElmerAPI) -> None:
    """Upcoming contest calendar."""
    days = st.slider("Look ahead (days)", 7, 365, 60, key="contest_days")
    major_only = st.checkbox("Major contests only", value=False, key="contest_major")

    contests = api.get_upcoming_contests(days=days)

    if major_only:
        contests = [c for c in contests if c.get("is_major")]

    if not contests:
        st.info("No upcoming contests in this period.")
        return

    st.caption(f"{len(contests)} contests")

    for c in contests:
        name = c.get("full_name", c.get("name", "?"))
        mode = c.get("mode", "")
        exchange = c.get("exchange", "")
        sponsor = c.get("sponsor", "")
        bands = ", ".join(c.get("bands", []))
        start = (c.get("start_utc", "") or "")[:10]
        end = (c.get("end_utc", "") or "")[:10]
        is_major = c.get("is_major", False)

        with st.container(border=True):
            cols = st.columns([3, 1.5, 2.5, 1])
            with cols[0]:
                label = f"**{name}**"
                if is_major:
                    label += " :star:"
                st.markdown(label)
            with cols[1]:
                st.caption(f"{start} to {end}")
            with cols[2]:
                st.caption(f"{mode} | {exchange}")
                if bands:
                    st.caption(f"Bands: {bands}")
            with cols[3]:
                st.caption(sponsor)


# ── Live Dashboard ───────────────────────────────────────────────────────


def _render_live(api: ElmerAPI) -> None:
    """Live contest dashboard with real-time metrics."""
    contest_name = st.text_input(
        "Contest name (as in Log4OM)",
        key="contest_live_name",
        placeholder="e.g. CQ-WW-CW, ARRL-FD",
    )

    if not contest_name:
        st.caption("Enter the contest name to load the live dashboard.")
        return

    if st.button("Load Dashboard", type="primary", key="contest_load"):
        with st.spinner("Fetching contest data..."):
            dashboard = api.get_contest_dashboard(contest_name)

        if not dashboard:
            st.error("Failed to load contest dashboard. Check the contest name and worker connection.")
            return

        total = dashboard.get("total_qsos", 0)
        if total == 0:
            st.warning(f"No QSOs found for contest '{contest_name}' in the last 3 days.")
            return

        # Top metrics.
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("QSOs", f"{total:,}")
        with m2:
            st.metric("Unique Calls", dashboard.get("unique_calls", 0))
        with m3:
            st.metric("Multipliers", dashboard.get("multipliers", 0))
        with m4:
            st.metric("Est. Score", f"{dashboard.get('estimated_score', 0):,}")

        # Rate section.
        st.subheader("QSO Rate")
        r1, r2, r3 = st.columns(3)
        rate_10 = dashboard.get("rate_last_10", {})
        rate_60 = dashboard.get("rate_last_60", {})
        with r1:
            rate_10_val = rate_10.get("rate_per_hour", 0) if isinstance(rate_10, dict) else 0
            st.metric("Last 10 min", f"{rate_10_val:.0f}/hr")
        with r2:
            rate_60_val = rate_60.get("rate_per_hour", 0) if isinstance(rate_60, dict) else 0
            st.metric("Last 60 min", f"{rate_60_val:.0f}/hr")
        with r3:
            elapsed = dashboard.get("elapsed_hours", 0)
            st.metric("Elapsed", f"{elapsed:.1f} hours")

        # Band breakdown chart.
        bands = dashboard.get("bands_worked", {})
        if bands:
            st.subheader("Band Breakdown")
            band_order = ["160m", "80m", "40m", "20m", "15m", "10m", "6m", "2m"]
            ordered = [(b, bands.get(b, 0)) for b in band_order if b in bands]
            for b, c in sorted(bands.items()):
                if b not in {x[0] for x in ordered}:
                    ordered.append((b, c))

            if ordered:
                band_colors = {
                    "160m": "#AB63FA", "80m": "#636EFA", "40m": "#19D3F3",
                    "20m": "#00CC96", "15m": "#FFA15A", "10m": "#EF553B",
                    "6m": "#FF6692", "2m": "#B6E880",
                }
                colors = [band_colors.get(b, "#636EFA") for b, _ in ordered]

                fig = go.Figure(data=[go.Bar(
                    x=[b for b, _ in ordered],
                    y=[c for _, c in ordered],
                    marker_color=colors,
                    text=[c for _, c in ordered],
                    textposition="outside",
                )])
                fig.update_layout(
                    height=300,
                    margin=dict(l=40, r=20, t=20, b=30),
                    xaxis_title="Band",
                    yaxis_title="QSOs",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                )
                st.plotly_chart(fig, use_container_width=True)

        # Mode breakdown.
        modes = dashboard.get("modes_worked", {})
        if modes:
            st.subheader("Mode Breakdown")
            for mode, count in sorted(modes.items(), key=lambda x: x[1], reverse=True):
                st.caption(f"**{mode}**: {count} QSOs")

        # Time span.
        first = (dashboard.get("first_qso", "") or "")[:19]
        last = (dashboard.get("last_qso", "") or "")[:19]
        if first:
            st.caption(f"First QSO: {first} | Last QSO: {last}")

        # Band recommendation button.
        st.divider()
        current_band = st.selectbox(
            "Current band",
            ["160m", "80m", "40m", "20m", "15m", "10m", "6m"],
            index=3,
            key="contest_live_band",
        )
        if st.button("Suggest Band Change", key="contest_suggest_band"):
            with st.spinner("Analyzing..."):
                rec = api.recommend_band(current_band, contest=contest_name)
            if rec:
                suggested = rec.get("suggested_band", current_band)
                reason = rec.get("reason", "")
                condition = rec.get("band_condition", "")
                if suggested != current_band:
                    st.success(f"Move to **{suggested}** (conditions: {condition})")
                else:
                    st.info(f"Stay on **{current_band}** (conditions: {condition})")
                st.markdown(reason)
            else:
                st.error("Could not get band recommendation.")


# ── History ──────────────────────────────────────────────────────────────


def _render_history(api: ElmerAPI) -> None:
    """Historical contest participation."""
    history = api.get_contest_history()

    if not history:
        st.info("No contest history available. Is Log4OM connected?")
        return

    st.caption(f"{len(history)} contests in log")

    # Bar chart of contests by QSO count.
    names = [h.get("contest_name", "?")[:20] for h in history[:15]]
    counts = [h.get("qso_count", 0) for h in history[:15]]

    if names:
        fig = go.Figure(data=[go.Bar(
            x=names,
            y=counts,
            marker_color="#00CC96",
            text=[f"{c:,}" for c in counts],
            textposition="outside",
        )])
        fig.update_layout(
            height=300,
            margin=dict(l=40, r=20, t=20, b=100),
            xaxis_title="Contest",
            yaxis_title="QSOs",
            xaxis_tickangle=-45,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Contest list.
    for h in history:
        name = h.get("contest_name", "?")
        count = h.get("qso_count", 0)
        first = (h.get("first_qso", "") or "")[:10]
        last = (h.get("last_qso", "") or "")[:10]

        with st.container(border=True):
            cols = st.columns([3, 1, 2])
            with cols[0]:
                st.markdown(f"**{name}**")
            with cols[1]:
                st.caption(f"{count} QSOs")
            with cols[2]:
                st.caption(f"{first} to {last}")


# ── Band Advisor ─────────────────────────────────────────────────────────


def _render_advisor(api: ElmerAPI) -> None:
    """Band change recommendation with optional contest context."""
    col_band, col_contest = st.columns(2)

    with col_band:
        current_band = st.selectbox(
            "Current band",
            ["160m", "80m", "40m", "20m", "17m", "15m", "12m", "10m", "6m"],
            index=3,
            key="advisor_band",
        )
    with col_contest:
        contest = st.text_input(
            "Contest (optional)",
            key="advisor_contest",
            placeholder="e.g. CQ-WW-CW",
        )

    if st.button("Get Recommendation", type="primary", key="advisor_btn"):
        with st.spinner("Analyzing band conditions..."):
            rec = api.recommend_band(current_band, contest=contest or None)

        if not rec:
            st.error("Could not get band recommendation. Check propagation service.")
            return

        suggested = rec.get("suggested_band", current_band)
        reason = rec.get("reason", "")
        condition = rec.get("band_condition", "")

        if suggested != current_band:
            st.success(f"Move to **{suggested}** (conditions: {condition})")
        else:
            st.info(f"Stay on **{current_band}** (conditions: {condition})")

        st.markdown(reason)
