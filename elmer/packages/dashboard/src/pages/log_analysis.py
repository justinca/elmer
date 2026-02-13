"""Log Analysis — QSO analytics, DXCC tracker, contest history, AI insights."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI

_BAND_ORDER = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m", "2m"]


def render() -> None:
    st.header("Log Analysis")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # ── Summary Cards ────────────────────────────────────────────────────

    stats = api.get_log_stats()
    status = api.get_log_status()

    if stats is None and status is None:
        st.warning(
            "Cannot reach Log4OM data. Is the worker running and "
            "ELMER_LOG4OM_DB_PATH configured?"
        )
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total QSOs", f"{stats.get('total_qsos', 0):,}" if stats else "?")
    with c2:
        st.metric("Countries", stats.get("unique_countries", 0) if stats else "?")
    with c3:
        st.metric("Unique Calls", f"{stats.get('unique_calls', 0):,}" if stats else "?")
    with c4:
        st.metric("Grids", stats.get("unique_grids", 0) if stats else "?")
    with c5:
        contests = api.get_log_contests()
        contest_count = len(contests) if isinstance(contests, list) else 0
        st.metric("Contests", contest_count)

    # Date range.
    first = (stats.get("first_qso") or "")[:10] if stats else ""
    last = (stats.get("last_qso") or "")[:10] if stats else ""
    if first:
        st.caption(f"Log span: {first} to {last}")

    st.divider()

    # ── Tabs ─────────────────────────────────────────────────────────────

    tab_charts, tab_dxcc, tab_contests, tab_qsos, tab_ai = st.tabs(
        ["Activity Charts", "DXCC Tracker", "Contest History", "QSO Search", "AI Analysis"]
    )

    with tab_charts:
        _render_charts(api, stats)

    with tab_dxcc:
        _render_dxcc(api)

    with tab_contests:
        _render_contests(api)

    with tab_qsos:
        _render_qsos(api)

    with tab_ai:
        _render_ai(api)


# ── Activity Charts ──────────────────────────────────────────────────────


def _render_charts(api: ElmerAPI, stats: dict | None) -> None:
    """QSO activity charts — band, mode, yearly, top calls."""
    if not stats:
        st.info("No statistics available.")
        return

    col_band, col_mode = st.columns(2)

    # Band distribution bar chart.
    with col_band:
        by_band = stats.get("qsos_by_band", {})
        if by_band:
            st.subheader("QSOs by Band")
            ordered = [(b, by_band.get(b, 0)) for b in _BAND_ORDER if b in by_band]
            known = {b for b, _ in ordered}
            for b, c in sorted(by_band.items()):
                if b not in known:
                    ordered.append((b, c))

            if ordered:
                fig = go.Figure(data=[go.Bar(
                    x=[b for b, _ in ordered],
                    y=[c for _, c in ordered],
                    marker_color="#636EFA",
                    text=[f"{c:,}" for _, c in ordered],
                    textposition="outside",
                )])
                fig.update_layout(
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=30),
                    xaxis_title="Band",
                    yaxis_title="QSOs",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                )
                st.plotly_chart(fig, use_container_width=True)

    # Mode pie chart.
    with col_mode:
        by_mode = stats.get("qsos_by_mode", {})
        if by_mode:
            st.subheader("QSOs by Mode")
            mode_colors = {
                "CW": "#636EFA", "SSB": "#00CC96", "FT8": "#FFA15A",
                "FT4": "#EF553B", "RTTY": "#AB63FA", "FM": "#19D3F3",
                "AM": "#FF6692",
            }
            labels = list(by_mode.keys())
            values = list(by_mode.values())
            colors = [mode_colors.get(m, "#636EFA") for m in labels]

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.4,
                marker=dict(colors=colors),
                textinfo="label+percent",
            )])
            fig.update_layout(
                height=350,
                margin=dict(l=30, r=30, t=20, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                showlegend=False,
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
            text=[f"{by_year[y]:,}" for y in years],
            textposition="outside",
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

    # Top callsigns.
    top = stats.get("top_calls", [])
    if top:
        st.subheader("Top 10 Callsigns")
        if isinstance(top[0], dict):
            calls = [t.get("call", "?") for t in top]
            counts = [t.get("count", 0) for t in top]
        else:
            calls = [str(t) for t in top]
            counts = list(range(len(top), 0, -1))

        fig = go.Figure(data=[go.Bar(
            y=list(reversed(calls)),
            x=list(reversed(counts)),
            orientation="h",
            marker_color="#AB63FA",
            text=[f"{c:,}" for c in reversed(counts)],
            textposition="outside",
        )])
        fig.update_layout(
            height=350,
            margin=dict(l=100, r=40, t=20, b=30),
            xaxis_title="QSOs",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)


# ── DXCC Tracker ─────────────────────────────────────────────────────────


def _render_dxcc(api: ElmerAPI) -> None:
    """DXCC entity tracker with progress bars and per-band detail."""
    dxcc_data = api.get_log_dxcc()
    entities = dxcc_data if isinstance(dxcc_data, list) else (
        dxcc_data.get("entities", []) if dxcc_data else []
    )

    if not entities:
        st.info("No DXCC data available.")
        return

    total_entities = len(entities)

    # Award progress bars.
    st.subheader("Award Progress")

    # Count entities by mode.
    cw_entities = set()
    ssb_entities = set()
    digital_entities = set()
    all_entities = set()

    for e in entities:
        country = e.get("country", "?")
        all_entities.add(country)
        modes = e.get("modes_worked", [])
        for m in modes:
            m_upper = m.upper()
            if m_upper == "CW":
                cw_entities.add(country)
            elif m_upper in ("SSB", "AM", "FM"):
                ssb_entities.add(country)
            elif m_upper in ("FT8", "FT4", "RTTY", "JT65", "PSK31"):
                digital_entities.add(country)

    awards = [
        ("DXCC Mixed", len(all_entities), 100),
        ("DXCC Phone", len(ssb_entities), 100),
        ("DXCC CW", len(cw_entities), 100),
        ("DXCC Digital", len(digital_entities), 100),
    ]

    for name, worked, target in awards:
        pct = min(worked / target * 100, 100) if target else 0
        color = "#00CC96" if pct >= 100 else "#FFA15A" if pct >= 50 else "#636EFA"

        cols = st.columns([2, 4, 1])
        cols[0].markdown(f"**{name}**")
        cols[1].progress(min(pct / 100, 1.0))
        cols[2].caption(f"{worked}/{target}")

    st.divider()

    # Continent breakdown chart.
    continents: dict[str, int] = {}
    for e in entities:
        cont = e.get("continent", "?")
        if cont:
            continents[cont] = continents.get(cont, 0) + 1

    if continents:
        col_chart, col_filter = st.columns([3, 1])
        with col_chart:
            cont_order = ["NA", "SA", "EU", "AF", "AS", "OC", "AN"]
            cont_colors = {
                "NA": "#636EFA", "SA": "#00CC96", "EU": "#FFA15A",
                "AF": "#EF553B", "AS": "#AB63FA", "OC": "#19D3F3", "AN": "#FF6692",
            }
            ordered_conts = [(c, continents.get(c, 0)) for c in cont_order if c in continents]

            fig = go.Figure(data=[go.Bar(
                x=[c for c, _ in ordered_conts],
                y=[v for _, v in ordered_conts],
                marker_color=[cont_colors.get(c, "#636EFA") for c, _ in ordered_conts],
                text=[v for _, v in ordered_conts],
                textposition="outside",
            )])
            fig.update_layout(
                height=250,
                margin=dict(l=40, r=20, t=20, b=30),
                xaxis_title="Continent",
                yaxis_title="Entities",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
            )
            st.plotly_chart(fig, use_container_width=True)

    # Entity detail table.
    st.subheader(f"Entity Detail ({total_entities} worked)")

    filter_cont = st.selectbox(
        "Filter by continent",
        ["All", "NA", "SA", "EU", "AF", "AS", "OC", "AN"],
        key="dxcc_cont_filter",
    )

    filtered = entities
    if filter_cont != "All":
        filtered = [e for e in entities if e.get("continent") == filter_cont]

    # Column headers.
    hdr = st.columns([2.5, 0.8, 2.5, 2.5, 1])
    hdr[0].markdown("**Entity**")
    hdr[1].markdown("**QSOs**")
    hdr[2].markdown("**Bands**")
    hdr[3].markdown("**Modes**")
    hdr[4].markdown("**Confirmed**")

    for e in sorted(filtered, key=lambda x: x.get("country", "")):
        country = e.get("country", "?")
        count = e.get("count", 0)
        bands = ", ".join(e.get("bands_worked", []))
        modes = ", ".join(e.get("modes_worked", []))
        confirmed = ""
        if e.get("lotw_confirmed"):
            confirmed += "LoTW "
        if e.get("qsl_confirmed"):
            confirmed += "QSL"

        cols = st.columns([2.5, 0.8, 2.5, 2.5, 1])
        cols[0].markdown(f"**{country}**")
        cols[1].caption(str(count))
        cols[2].caption(bands or "—")
        cols[3].caption(modes or "—")
        cols[4].caption(confirmed.strip() or "—")


# ── Contest History ──────────────────────────────────────────────────────


def _render_contests(api: ElmerAPI) -> None:
    """Contest participation history."""
    contests = api.get_log_contests()
    contest_list = contests if isinstance(contests, list) else (
        contests.get("contests", []) if contests else []
    )

    if not contest_list:
        st.info("No contest history found in the log.")
        return

    st.caption(f"{len(contest_list)} contests in log")

    # Contest QSO count chart.
    names = [c.get("contest_name", "?")[:20] for c in contest_list[:15]]
    counts = [c.get("qso_count", 0) for c in contest_list[:15]]

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

    # Contest table.
    for c in contest_list:
        name = c.get("contest_name", "?")
        count = c.get("qso_count", 0)
        first = (c.get("first_qso", "") or "")[:10]
        last = (c.get("last_qso", "") or "")[:10]

        with st.container(border=True):
            cols = st.columns([3, 1, 2])
            with cols[0]:
                st.markdown(f"**{name}**")
            with cols[1]:
                st.caption(f"{count} QSOs")
            with cols[2]:
                st.caption(f"{first} to {last}")


# ── QSO Search ───────────────────────────────────────────────────────────


def _render_qsos(api: ElmerAPI) -> None:
    """Recent QSOs with search and filters."""
    col_search, col_band, col_mode = st.columns([3, 1, 1])

    with col_search:
        query = st.text_input("Search", placeholder="Callsign, name, country, comment...",
                              key="log_search_q")
    with col_band:
        band = st.selectbox("Band", ["All"] + _BAND_ORDER, key="log_search_band")
    with col_mode:
        mode = st.selectbox("Mode", ["All", "CW", "SSB", "FT8", "FT4", "RTTY", "FM"],
                            key="log_search_mode")

    if query:
        results = api.search_log(query, limit=100)
        qsos = results if isinstance(results, list) else (
            results.get("results", []) if results else []
        )
    else:
        qsos_data = api.get_log_qsos(
            limit=50,
            band=band if band != "All" else None,
            mode=mode if mode != "All" else None,
        )
        qsos = qsos_data if isinstance(qsos_data, list) else (
            qsos_data.get("qsos", []) if qsos_data else []
        )

    if not qsos:
        st.info("No QSOs found.")
        return

    st.caption(f"Showing {len(qsos)} QSOs")

    # Column headers.
    hdr = st.columns([1.2, 2, 1, 1, 1.5, 1, 1.5])
    hdr[0].markdown("**Date**")
    hdr[1].markdown("**Callsign**")
    hdr[2].markdown("**Band**")
    hdr[3].markdown("**Mode**")
    hdr[4].markdown("**Country**")
    hdr[5].markdown("**RST**")
    hdr[6].markdown("**Grid**")

    for q in qsos:
        qso_date = (q.get("qso_date") or "")[:10]
        callsign = q.get("call", "?")
        qband = q.get("band", "")
        qmode = q.get("mode", "")
        country = q.get("country", "")
        rst_s = q.get("rst_sent", "")
        rst_r = q.get("rst_rcvd", "")
        grid = q.get("grid", "")
        name = q.get("name", "")

        name_display = f" ({name})" if name else ""
        rst = f"{rst_s}/{rst_r}" if rst_s or rst_r else "—"

        cols = st.columns([1.2, 2, 1, 1, 1.5, 1, 1.5])
        cols[0].caption(qso_date)
        cols[1].markdown(f"**{callsign}**{name_display}")
        cols[2].caption(qband)
        cols[3].caption(qmode)
        cols[4].caption(country)
        cols[5].caption(rst)
        cols[6].caption(grid)


# ── AI Analysis ──────────────────────────────────────────────────────────


def _render_ai(api: ElmerAPI) -> None:
    """LLM-powered log analysis and knowledge base sync."""
    col_days, col_focus = st.columns([1, 3])

    with col_days:
        days = st.slider("Days to analyze", 7, 365, 30, key="ai_days")
    with col_focus:
        focus = st.text_input("Focus area (optional)", key="ai_focus",
                              placeholder="e.g. DX performance, contest results, band usage")

    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("Analyze with AI", type="primary", key="ai_analyze_btn"):
            with st.spinner("Running LLM analysis (this may take a minute)..."):
                result = api.analyze_log(days=days, focus=focus or None)
            if result:
                st.markdown("---")
                st.markdown(result.get("analysis", "No analysis returned."))
                st.caption(
                    f"Analyzed {result.get('qso_count', 0)} QSOs "
                    f"over {result.get('days_analyzed', 0)} days"
                )
            else:
                st.error("Analysis failed. Check that the worker and LLM are available.")

    with b2:
        if st.button("Sync to Knowledge Base", key="ai_sync_btn"):
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

    with b3:
        if st.button("Check Needs vs Log", key="ai_needs_btn"):
            with st.spinner("Cross-referencing needs list..."):
                result = api.check_log_needs()
            if result:
                total = result.get("total_needs", 0)
                confirmed = result.get("total_confirmed", 0)
                st.info(f"{confirmed}/{total} needs already worked in log.")

                worked = result.get("confirmed_worked", [])
                if worked:
                    st.markdown("**Already Worked:**")
                    for w in worked:
                        st.caption(
                            f"{w['entity']} — {w.get('qso_count', 0)} QSOs, "
                            f"bands: {', '.join(w.get('bands_worked', []))}"
                        )

                needed = result.get("still_needed", [])
                if needed:
                    st.markdown("**Still Needed:**")
                    for n in needed:
                        band = n.get("band") or "Any"
                        mode = n.get("mode") or "Any"
                        st.caption(f"P{n.get('priority', 5)} {n['entity']} — {band}/{mode}")
            else:
                st.error("Needs check failed.")
