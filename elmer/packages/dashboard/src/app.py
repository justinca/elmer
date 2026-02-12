"""Elmer Dashboard — Main Streamlit application."""

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Elmer Dashboard",
    page_icon="📡",
    layout="wide",
)

# -- Sidebar ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📡 Elmer")
    st.caption("Home Lab OS · v0.1.0")
    st.divider()

    page = st.radio(
        "Navigation",
        ["System Status", "Services", "Event Log"],
        label_visibility="collapsed",
    )

    st.divider()

    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_interval = st.select_slider(
        "Interval (sec)",
        options=[10, 15, 30, 60, 120],
        value=30,
        disabled=not auto_refresh,
    )

# -- Auto-refresh via JS ------------------------------------------------------

if auto_refresh:
    components.html(
        f"<script>setTimeout(function(){{window.parent.location.reload()}}"
        f",{refresh_interval * 1000})</script>",
        height=0,
    )

# -- Page router ---------------------------------------------------------------

if page == "System Status":
    from pages.system_status import render

    render()
elif page == "Services":
    from pages.services import render

    render()
elif page == "Event Log":
    from pages.events import render

    render()
