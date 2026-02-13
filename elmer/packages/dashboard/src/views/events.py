"""Event Log page — browsable event feed from elmer.events."""

import streamlit as st
import pandas as pd

from api_client import ElmerAPI


def render() -> None:
    st.header("Event Log")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # -- Filters --------------------------------------------------------------

    col1, col2, col3 = st.columns(3)

    nodes = api.get_nodes()
    node_ids = ["All"] + [
        n.get("node_id", "") for n in nodes if n.get("node_id")
    ]

    with col1:
        source_filter = st.selectbox("Source", node_ids)

    with col2:
        type_filter = st.text_input(
            "Event type", placeholder="e.g. heartbeat"
        )

    with col3:
        hours = st.select_slider(
            "Time range (hours)",
            options=[1, 6, 12, 24, 48, 72],
            value=24,
        )

    # Pause toggle
    paused = st.toggle("Pause auto-scroll", value=False)

    st.divider()

    # -- Fetch events ---------------------------------------------------------

    with st.spinner("Loading events..."):
        if source_filter and source_filter != "All":
            events = api.get_node_history(source_filter, hours=hours)
        else:
            events = api.get_events(hours=hours)

    if type_filter:
        events = [
            e
            for e in events
            if type_filter.lower() in e.get("event_type", "").lower()
        ]

    if not events:
        st.info("No events found for the selected filters.")
        return

    st.caption(f"Showing {len(events)} events")

    # -- Display as DataFrame -------------------------------------------------

    df = pd.DataFrame(events)

    display_cols = []
    for col_name in ("timestamp", "source", "event_type", "data"):
        if col_name in df.columns:
            display_cols.append(col_name)

    if "data" in display_cols:
        df["data"] = df["data"].apply(
            lambda x: str(x) if x else ""
        )

    if display_cols:
        st.dataframe(
            df[display_cols],
            use_container_width=True,
            hide_index=True,
        )
