"""Logbook page — QSO browser, DXCC tracker, statistics, and AI analysis."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("Logbook")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # -- Status bar -----------------------------------------------------------

    stats = api.get_log_stats()
    status = api.get_log_status()

    if stats is None and status is None:
        st.warning(
            "Cannot reach Log4OM data. Is the worker running and "
            "ELMER_LOG4OM_DB_PATH configured?"
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total QSOs", f"{stats.get('total_qsos', 0):,}" if stats else "?")
    with c2:
        st.metric("Countries", stats.get("unique_countries", 0) if stats else "?")
    with c3:
        st.metric("Unique Calls", f"{stats.get('unique_calls', 0):,}" if stats else "?")
    with c4:
        st.metric("Grids", stats.get("unique_grids", 0) if stats else "?")

    st.divider()

    # -- Tabs -----------------------------------------------------------------

    tab_recent, tab_search, tab_dxcc, tab_stats, tab_analysis = st.tabs(
        ["Recent QSOs", "Search", "DXCC", "Statistics", "AI Analysis"]
    )

    # === Recent QSOs =========================================================

    with tab_recent:
        _render_recent(api)

    # === Search ==============================================================

    with tab_search:
        _render_search(api)

    # === DXCC ================================================================

    with tab_dxcc:
        _render_dxcc(api)

    # === Statistics ===========================================================

    with tab_stats:
        _render_stats(api, stats)

    # === AI Analysis =========================================================

    with tab_analysis:
        _render_analysis(api)


def _render_recent(api: ElmerAPI) -> None:
    """Recent QSOs tab with filters."""
    col_band, col_mode, col_call, col_country = st.columns(4)

    with col_band:
        band = st.selectbox(
            "Band", ["All", "160m", "80m", "60m", "40m", "30m", "20m",
                      "17m", "15m", "12m", "10m", "6m", "2m"],
            key="log_band",
        )
    with col_mode:
        mode = st.selectbox(
            "Mode", ["All", "CW", "SSB", "FT8", "FT4", "RTTY", "FM", "AM"],
            key="log_mode",
        )
    with col_call:
        call = st.text_input("Callsign", key="log_call", placeholder="e.g. JA1ABC")
    with col_country:
        country = st.text_input("Country", key="log_country", placeholder="e.g. Japan")

    col_since, col_until, col_limit = st.columns(3)
    with col_since:
        since = st.date_input("Since", value=None, key="log_since")
    with col_until:
        until = st.date_input("Until", value=None, key="log_until")
    with col_limit:
        limit = st.select_slider("Limit", [25, 50, 100, 200, 500], value=50, key="log_limit")

    data = api.get_log_qsos(
        limit=limit,
        call=call or None,
        band=band if band != "All" else None,
        mode=mode if mode != "All" else None,
        country=country or None,
        since=since.isoformat() if since else None,
        until=until.isoformat() if until else None,
    )

    qsos = data if isinstance(data, list) else (data.get("qsos", []) if data else [])

    if not qsos:
        st.info("No QSOs found matching filters.")
        return

    st.caption(f"Showing {len(qsos)} QSOs")

    # Display as compact cards.
    for q in qsos:
        qso_date = q.get("qso_date", "")[:10]
        callsign = q.get("call", "?")
        qband = q.get("band", "")
        qmode = q.get("mode", "")
        freq = q.get("freq", "")
        qcountry = q.get("country", "")
        name = q.get("name", "")
        grid = q.get("grid", "")
        rst_s = q.get("rst_sent", "")
        rst_r = q.get("rst_rcvd", "")
        comment = q.get("comment", "")

        name_display = f" — {name}" if name else ""
        country_display = f" ({qcountry})" if qcountry else ""
        rst_display = f" RST {rst_s}/{rst_r}" if rst_s or rst_r else ""
        grid_display = f" [{grid}]" if grid else ""
        freq_display = f" {freq}" if freq else ""

        with st.container(border=True):
            cols = st.columns([1.5, 2.5, 3, 1])
            with cols[0]:
                st.caption(qso_date)
            with cols[1]:
                st.markdown(f"**{callsign}**{name_display}{country_display}")
            with cols[2]:
                st.caption(f"{qband} {qmode}{freq_display}{rst_display}{grid_display}")
            with cols[3]:
                if comment:
                    st.caption(comment[:40])


def _render_search(api: ElmerAPI) -> None:
    """Full-text search across QSO fields."""
    query = st.text_input("Search QSOs", placeholder="Callsign, name, country, comment...", key="log_search_q")

    if not query:
        st.caption("Enter a search term to find QSOs.")
        return

    results = api.search_log(query, limit=100)
    qsos = results if isinstance(results, list) else (results.get("results", []) if results else [])

    if not qsos:
        st.info(f"No QSOs matching '{query}'.")
        return

    st.caption(f"Found {len(qsos)} results")

    for q in qsos:
        callsign = q.get("call", "?")
        qso_date = q.get("qso_date", "")[:10]
        band = q.get("band", "")
        mode = q.get("mode", "")
        country = q.get("country", "")
        name = q.get("name", "")
        comment = q.get("comment", "")

        line = f"**{callsign}** {name or ''} ({country}) — {band} {mode} — {qso_date}"
        if comment:
            line += f" — _{comment[:60]}_"
        st.markdown(line)


def _render_dxcc(api: ElmerAPI) -> None:
    """DXCC entity summary with band/mode detail."""
    dxcc_data = api.get_log_dxcc()
    entities = dxcc_data if isinstance(dxcc_data, list) else (
        dxcc_data.get("entities", []) if dxcc_data else []
    )

    if not entities:
        st.info("No DXCC data available.")
        return

    st.metric("DXCC Entities Worked", len(entities))

    # Continent breakdown.
    continents: dict[str, int] = {}
    for e in entities:
        cont = e.get("continent", "?")
        if cont:
            continents[cont] = continents.get(cont, 0) + 1

    if continents:
        fig = go.Figure(data=[go.Bar(
            x=list(continents.keys()),
            y=list(continents.values()),
            marker_color="#636EFA",
        )])
        fig.update_layout(
            height=200,
            margin=dict(l=40, r=20, t=20, b=30),
            xaxis_title="Continent",
            yaxis_title="Entities",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Entity table.
    st.subheader("Entity Detail")
    filter_cont = st.selectbox("Filter by continent", ["All", "NA", "SA", "EU", "AF", "AS", "OC", "AN"], key="dxcc_cont")

    filtered = entities
    if filter_cont != "All":
        filtered = [e for e in entities if e.get("continent") == filter_cont]

    for e in sorted(filtered, key=lambda x: x.get("country", "")):
        country = e.get("country", "?")
        count = e.get("count", 0)
        bands = ", ".join(e.get("bands_worked", []))
        modes = ", ".join(e.get("modes_worked", []))
        confirmed = ""
        if e.get("lotw_confirmed"):
            confirmed += " LoTW"
        if e.get("qsl_confirmed"):
            confirmed += " QSL"

        with st.container(border=True):
            cols = st.columns([2, 1, 2, 2, 1])
            with cols[0]:
                st.markdown(f"**{country}**")
            with cols[1]:
                st.caption(f"{count} QSOs")
            with cols[2]:
                st.caption(f"Bands: {bands or 'N/A'}")
            with cols[3]:
                st.caption(f"Modes: {modes or 'N/A'}")
            with cols[4]:
                if confirmed:
                    st.caption(confirmed.strip())


def _render_stats(api: ElmerAPI, stats: dict | None) -> None:
    """Statistics charts and numbers."""
    if not stats:
        st.info("No statistics available.")
        return

    # Band chart.
    by_band = stats.get("qsos_by_band", {})
    if by_band:
        st.subheader("QSOs by Band")
        band_order = ["160m", "80m", "60m", "40m", "30m", "20m", "17m",
                      "15m", "12m", "10m", "6m", "2m"]
        ordered = [(b, by_band.get(b, 0)) for b in band_order if b in by_band]
        # Add any bands not in our standard list.
        known = {b for b, _ in ordered}
        for b, c in sorted(by_band.items()):
            if b not in known:
                ordered.append((b, c))

        if ordered:
            fig = go.Figure(data=[go.Bar(
                x=[b for b, _ in ordered],
                y=[c for _, c in ordered],
                marker_color="#636EFA",
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

    # Mode chart.
    by_mode = stats.get("qsos_by_mode", {})
    if by_mode:
        st.subheader("QSOs by Mode")
        fig = go.Figure(data=[go.Pie(
            labels=list(by_mode.keys()),
            values=list(by_mode.values()),
            hole=0.4,
        )])
        fig.update_layout(
            height=300,
            margin=dict(l=40, r=40, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Yearly trend.
    by_year = stats.get("qsos_by_year", {})
    if by_year:
        st.subheader("QSOs by Year")
        years = sorted(by_year.keys())
        fig = go.Figure(data=[go.Bar(
            x=years,
            y=[by_year[y] for y in years],
            marker_color="#00CC96",
        )])
        fig.update_layout(
            height=300,
            margin=dict(l=40, r=20, t=20, b=30),
            xaxis_title="Year",
            yaxis_title="QSOs",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Top calls.
    top = stats.get("top_calls", [])
    if top:
        st.subheader("Top 10 Callsigns")
        for t in top:
            if isinstance(t, dict):
                st.caption(f"**{t.get('call', '?')}** — {t.get('count', 0)} QSOs")
            else:
                st.caption(str(t))

    # Date range.
    first = stats.get("first_qso", "")
    last = stats.get("last_qso", "")
    if first or last:
        st.caption(f"Log span: {first[:10] if first else '?'} to {last[:10] if last else '?'}")


def _render_analysis(api: ElmerAPI) -> None:
    """LLM-based log analysis."""
    col_days, col_focus = st.columns([1, 2])

    with col_days:
        days = st.slider("Days to analyze", 7, 365, 30, key="analysis_days")
    with col_focus:
        focus = st.text_input("Focus area (optional)", key="analysis_focus",
                              placeholder="e.g. DX performance, contest results")

    col_analyze, col_sync, col_needs = st.columns(3)

    with col_analyze:
        if st.button("Analyze Log", type="primary"):
            with st.spinner("Running LLM analysis..."):
                result = api.analyze_log(days=days, focus=focus or None)
            if result:
                st.markdown(result.get("analysis", "No analysis returned."))
                st.caption(
                    f"Analyzed {result.get('qso_count', 0)} QSOs "
                    f"over {result.get('days_analyzed', 0)} days"
                )
            else:
                st.error("Analysis failed. Check that the worker and LLM are available.")

    with col_sync:
        if st.button("Sync to Knowledge Base"):
            with st.spinner("Syncing daily summaries..."):
                result = api.sync_log()
            if result:
                synced = result.get("synced", 0)
                errors = result.get("errors", [])
                st.success(f"Synced {synced} days to knowledge base.")
                if errors:
                    st.warning(f"{len(errors)} errors during sync.")
            else:
                st.error("Sync failed.")

    with col_needs:
        if st.button("Check Needs vs Log"):
            with st.spinner("Cross-referencing needs list..."):
                result = api.check_log_needs()
            if result:
                total = result.get("total_needs", 0)
                confirmed = result.get("total_confirmed", 0)
                st.info(f"{confirmed}/{total} needs already worked in log.")

                worked = result.get("confirmed_worked", [])
                if worked:
                    st.subheader("Already Worked")
                    for w in worked:
                        st.caption(
                            f"{w['entity']} — {w.get('qso_count', 0)} QSOs, "
                            f"bands: {', '.join(w.get('bands_worked', []))}"
                        )

                needed = result.get("still_needed", [])
                if needed:
                    st.subheader("Still Needed")
                    for n in needed:
                        band = n.get("band") or "Any"
                        mode = n.get("mode") or "Any"
                        st.caption(f"P{n.get('priority', 5)} {n['entity']} — {band}/{mode}")
            else:
                st.error("Needs check failed.")
