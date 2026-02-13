"""DX Spots — live spot feed, needs highlighting, band activity, spot map."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI

_BAND_ORDER = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]


def render() -> None:
    st.header("DX Spots")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # ── Cluster Status Indicator ─────────────────────────────────────────

    status = api.get_dx_cluster_status()
    summary = api.get_dx_summary()

    s1, s2, s3, s4 = st.columns(4)

    with s1:
        if status and status.get("connected"):
            host = status.get("host", "?")
            st.markdown(
                f'<div style="background:rgba(0,204,150,0.15);color:#00CC96;'
                f'padding:6px 12px;border-radius:4px;font-weight:600;">'
                f'Connected — {host}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="background:rgba(239,85,59,0.15);color:#EF553B;'
                'padding:6px 12px;border-radius:4px;font-weight:600;">'
                'Disconnected</div>',
                unsafe_allow_html=True,
            )

    with s2:
        total = status.get("total_spots_received", 0) if status else 0
        st.metric("Total Spots", f"{total:,}")

    with s3:
        in_mem = status.get("spots_in_memory", 0) if status else 0
        st.metric("In Memory", in_mem)

    with s4:
        hour_total = summary.get("total_last_hour", 0) if summary else 0
        st.metric("Last Hour", hour_total)

    st.divider()

    # ── Tabs ─────────────────────────────────────────────────────────────

    tab_spots, tab_activity, tab_needs, tab_lookup = st.tabs(
        ["Live Spots", "Band Activity", "Needs List", "Callsign Lookup"]
    )

    with tab_spots:
        _render_spots(api)

    with tab_activity:
        _render_activity(api, summary)

    with tab_needs:
        _render_needs(api)

    with tab_lookup:
        _render_lookup(api)


def _render_spots(api: ElmerAPI) -> None:
    """Live spot feed with filters and needs highlighting."""
    # Load needs list for highlighting.
    needs = api.get_dx_needs()
    need_entities = {n.get("entity", "").lower() for n in needs} if needs else set()

    # Filters.
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        band_filter = st.selectbox(
            "Band", ["All"] + _BAND_ORDER, key="dx_spot_band",
        )
    with f2:
        mode_filter = st.selectbox(
            "Mode", ["All", "CW", "SSB", "FT8", "FT4", "RTTY", "AM"], key="dx_spot_mode",
        )
    with f3:
        entity_filter = st.text_input("Entity", key="dx_spot_entity", placeholder="e.g. Japan")
    with f4:
        continent_filter = st.selectbox(
            "Continent", ["All", "NA", "SA", "EU", "AF", "AS", "OC"], key="dx_spot_cont",
        )

    spots = api.get_dx_spots(
        band=band_filter if band_filter != "All" else None,
        mode=mode_filter if mode_filter != "All" else None,
        entity=entity_filter or None,
        limit=200,
    )

    if not spots:
        st.info("No spots found. The DX cluster connection may still be initializing.")
        return

    # Apply continent filter client-side (API may not support it directly).
    if continent_filter != "All":
        spots = [s for s in spots if s.get("dx_continent", "") == continent_filter]

    st.caption(f"{len(spots)} spots")

    # Column headers.
    hdr = st.columns([1.2, 2, 1.5, 1, 1, 2, 2, 1])
    hdr[0].markdown("**Time**")
    hdr[1].markdown("**DX Call**")
    hdr[2].markdown("**Freq**")
    hdr[3].markdown("**Band**")
    hdr[4].markdown("**Mode**")
    hdr[5].markdown("**Entity**")
    hdr[6].markdown("**Spotter**")
    hdr[7].markdown("**Comment**")

    for s in spots[:100]:
        freq = s.get("frequency", 0)
        band = s.get("band", "?")
        mode = s.get("mode", "?")
        dx = s.get("dx_call", "?")
        entity = s.get("dx_entity", "")
        spotter = s.get("spotter", "?")
        comment = s.get("comment", "")
        ts = (s.get("timestamp") or "")[:19]
        time_display = ts[11:16] if len(ts) > 11 else ts

        # Highlight spots matching needs list.
        is_needed = entity.lower() in need_entities if entity else False

        if is_needed:
            # Red highlight for needed entities.
            cols = st.columns([1.2, 2, 1.5, 1, 1, 2, 2, 1])
            cols[0].markdown(f'<span style="color:#EF553B;font-weight:bold;">{time_display}</span>',
                             unsafe_allow_html=True)
            cols[1].markdown(f'<span style="color:#EF553B;font-weight:bold;">{dx}</span>',
                             unsafe_allow_html=True)
            cols[2].caption(f"{freq:.1f}")
            cols[3].caption(band)
            cols[4].caption(mode)
            cols[5].markdown(f'<span style="color:#EF553B;font-weight:bold;">{entity} NEED</span>',
                             unsafe_allow_html=True)
            cols[6].caption(spotter)
            cols[7].caption(comment[:30])
        else:
            cols = st.columns([1.2, 2, 1.5, 1, 1, 2, 2, 1])
            cols[0].caption(time_display)
            cols[1].markdown(f"**{dx}**")
            cols[2].caption(f"{freq:.1f}")
            cols[3].caption(band)
            cols[4].caption(mode)
            cols[5].caption(entity)
            cols[6].caption(spotter)
            cols[7].caption(comment[:30])


def _render_activity(api: ElmerAPI, summary: dict | None) -> None:
    """Band activity chart and mode breakdown."""
    if not summary:
        st.info("No activity summary available.")
        return

    # Band activity bar chart.
    band_data = summary.get("bands", {})
    if band_data:
        st.subheader("Spots per Band (Last Hour)")
        ordered = [(b, band_data.get(b, 0)) for b in _BAND_ORDER if b in band_data]
        # Add any unexpected bands.
        known = {b for b, _ in ordered}
        for b, c in sorted(band_data.items()):
            if b not in known:
                ordered.append((b, c))

        if ordered:
            fig = go.Figure(data=[go.Bar(
                x=[b for b, _ in ordered],
                y=[c for _, c in ordered],
                marker_color="#636EFA",
                text=[c for _, c in ordered],
                textposition="outside",
            )])
            fig.update_layout(
                height=300,
                margin=dict(l=40, r=20, t=30, b=30),
                xaxis_title="Band",
                yaxis_title="Spots",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
            )
            st.plotly_chart(fig, use_container_width=True)

    # Mode breakdown pie chart.
    mode_data = summary.get("modes", {})
    if mode_data:
        st.subheader("Mode Breakdown (Last Hour)")
        mode_colors = {
            "CW": "#636EFA", "SSB": "#00CC96", "FT8": "#FFA15A",
            "FT4": "#EF553B", "RTTY": "#AB63FA", "AM": "#19D3F3",
        }
        labels = list(mode_data.keys())
        values = list(mode_data.values())
        colors = [mode_colors.get(m, "#636EFA") for m in labels]

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker=dict(colors=colors),
        )])
        fig.update_layout(
            height=300,
            margin=dict(l=40, r=40, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_needs(api: ElmerAPI) -> None:
    """Needs list manager — view, add, remove."""
    needs = api.get_dx_needs()

    if needs:
        st.caption(f"{len(needs)} entities on needs list")

        for n in sorted(needs, key=lambda x: x.get("priority", 5)):
            priority = n.get("priority", 5)
            entity = n.get("entity", "?")
            band = n.get("band") or "Any"
            mode = n.get("mode") or "Any"
            notes = n.get("notes", "")
            nid = n.get("id")

            p_colors = {1: "#EF553B", 2: "#EF553B", 3: "#FFA15A", 4: "#636EFA", 5: "#636EFA"}
            color = p_colors.get(priority, "#636EFA")

            cols = st.columns([0.5, 2.5, 1, 1, 2, 0.8])
            cols[0].markdown(
                f'<span style="color:{color};font-weight:bold;">P{priority}</span>',
                unsafe_allow_html=True,
            )
            cols[1].markdown(f"**{entity}**")
            cols[2].caption(band)
            cols[3].caption(mode)
            cols[4].caption(notes)
            if nid is not None:
                if cols[5].button("X", key=f"del_need_{nid}"):
                    api.delete_dx_need(nid)
                    st.rerun()
    else:
        st.info("Needs list is empty.")

    # Add new need.
    st.divider()
    st.subheader("Add Need")
    ac1, ac2, ac3, ac4, ac5 = st.columns([3, 1, 1, 1, 2])
    with ac1:
        new_entity = st.text_input("Entity", key="need_entity", placeholder="e.g. Bouvet Island")
    with ac2:
        new_band = st.selectbox("Band", ["Any"] + _BAND_ORDER, key="need_band")
    with ac3:
        new_mode = st.selectbox("Mode", ["Any", "CW", "SSB", "FT8", "RTTY"], key="need_mode")
    with ac4:
        new_priority = st.selectbox("Priority", [1, 2, 3, 4, 5], index=2, key="need_priority")
    with ac5:
        new_notes = st.text_input("Notes", key="need_notes", placeholder="optional")

    if st.button("Add to Needs List", type="primary", key="need_add_btn"):
        if new_entity:
            payload = {
                "entity": new_entity,
                "priority": new_priority,
                "band": new_band if new_band != "Any" else None,
                "mode": new_mode if new_mode != "Any" else None,
                "notes": new_notes,
            }
            result = api.add_dx_need(payload)
            if result:
                st.success(f"Added {new_entity} to needs list.")
                st.rerun()
            else:
                st.error("Failed to add need.")
        else:
            st.warning("Enter an entity name.")


def _render_lookup(api: ElmerAPI) -> None:
    """Callsign / DXCC entity lookup."""
    lookup_call = st.text_input("Callsign", placeholder="e.g. JA1ABC", key="dx_lookup_call")
    if lookup_call:
        result = api.lookup_entity(lookup_call)
        if result:
            lc1, lc2, lc3, lc4, lc5 = st.columns(5)
            lc1.metric("Entity", result.get("entity_name", "?"))
            lc2.metric("Prefix", result.get("prefix", "?"))
            lc3.metric("Continent", result.get("continent", "?"))
            lc4.metric("CQ Zone", result.get("cq_zone", "?"))
            lc5.metric("ITU Zone", result.get("itu_zone", "?"))
        else:
            st.warning(f"No DXCC entity found for '{lookup_call}'")
