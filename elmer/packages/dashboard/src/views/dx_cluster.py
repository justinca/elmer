"""DX Cluster page — live spots, needs list, cluster status."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("DX Cluster")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # -- Cluster status bar ---------------------------------------------------

    status = api.get_dx_cluster_status()
    summary = api.get_dx_summary()

    col_status, col_spots, col_hour = st.columns(3)

    with col_status:
        if status and status.get("connected"):
            host = status.get("host", "?")
            st.metric("Cluster", f"Connected ({host})")
        else:
            st.metric("Cluster", "Disconnected")

    with col_spots:
        total = status.get("total_spots_received", 0) if status else 0
        st.metric("Total Spots", total)

    with col_hour:
        hour_total = summary.get("total_last_hour", 0) if summary else 0
        st.metric("Last Hour", hour_total)

    # -- Band activity chart --------------------------------------------------

    if summary and summary.get("bands"):
        st.subheader("Band Activity (Last Hour)")
        bands = summary["bands"]
        band_order = ["160m", "80m", "60m", "40m", "30m", "20m", "17m",
                      "15m", "12m", "10m", "6m"]
        ordered = [(b, bands.get(b, 0)) for b in band_order if b in bands]
        if ordered:
            fig = go.Figure(data=[go.Bar(
                x=[b[0] for b in ordered],
                y=[b[1] for b in ordered],
                marker_color="#636EFA",
            )])
            fig.update_layout(
                height=250,
                margin=dict(l=40, r=20, t=20, b=30),
                xaxis_title="Band",
                yaxis_title="Spots",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # -- Spot filters ---------------------------------------------------------

    st.subheader("Recent Spots")

    col_band, col_mode, col_entity = st.columns(3)

    with col_band:
        band_filter = st.selectbox(
            "Band", ["All", "160m", "80m", "60m", "40m", "30m", "20m",
                      "17m", "15m", "12m", "10m", "6m"],
        )
    with col_mode:
        mode_filter = st.selectbox(
            "Mode", ["All", "CW", "SSB", "FT8", "FT4", "RTTY"],
        )
    with col_entity:
        entity_filter = st.text_input("Entity", placeholder="e.g. Japan")

    # Fetch spots with filters.
    spots = api.get_dx_spots(
        band=band_filter if band_filter != "All" else None,
        mode=mode_filter if mode_filter != "All" else None,
        entity=entity_filter or None,
        limit=100,
    )

    if not spots:
        st.info("No spots found. The DX cluster connection may still be initializing.")
    else:
        st.caption(f"Showing {len(spots)} spots")

        for s in spots[:50]:
            freq = s.get("frequency", 0)
            band = s.get("band", "?")
            mode = s.get("mode", "?")
            dx = s.get("dx_call", "?")
            entity = s.get("dx_entity", "")
            spotter = s.get("spotter", "?")
            comment = s.get("comment", "")
            ts = (s.get("timestamp") or "")[:19]

            entity_display = f" ({entity})" if entity else ""

            with st.container(border=True):
                cols = st.columns([2, 2, 3, 1])
                with cols[0]:
                    st.markdown(f"**{dx}**{entity_display}")
                with cols[1]:
                    st.caption(f"{freq:.1f} kHz · {band} {mode}")
                with cols[2]:
                    st.caption(f"de {spotter}: {comment[:60]}")
                with cols[3]:
                    st.caption(ts[11:])

    st.divider()

    # -- Needs list -----------------------------------------------------------

    st.subheader("Needs List")

    needs = api.get_dx_needs()
    if needs:
        st.caption(f"{len(needs)} entities needed")

        for n in needs:
            priority = n.get("priority", 5)
            entity = n.get("entity", "?")
            band = n.get("band") or "Any"
            mode = n.get("mode") or "Any"
            notes = n.get("notes", "")
            nid = n.get("id")

            priority_label = {1: "P1", 2: "P2", 3: "P3", 4: "P4", 5: "P5"}
            p_str = priority_label.get(priority, f"P{priority}")

            st.caption(f"**{p_str}** {entity} — {band}/{mode} {notes}")
    else:
        st.info("Needs list is empty. Add entities you need via the API.")

    # -- Callsign lookup ------------------------------------------------------

    st.divider()
    st.subheader("Callsign Lookup")
    lookup_call = st.text_input("Callsign", placeholder="e.g. JA1ABC")
    if lookup_call:
        result = api.lookup_entity(lookup_call)
        if result:
            st.success(
                f"**{result['entity_name']}** "
                f"(prefix: {result['prefix']}, "
                f"continent: {result['continent']}, "
                f"CQ: {result['cq_zone']}, ITU: {result['itu_zone']})"
            )
        else:
            st.warning(f"No DXCC entity found for '{lookup_call}'")
