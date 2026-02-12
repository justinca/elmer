"""Elmer Dashboard — Main Streamlit application."""

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Elmer Dashboard",
    page_icon="\U0001f4e1",
    layout="wide",
)

# -- Sidebar ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## \U0001f4e1 Elmer")
    st.caption("Home Lab OS \u00b7 v0.1.0")
    st.divider()

    st.caption("SYSTEM")
    system_pages = ["System Status", "Services", "Event Log"]
    st.caption("KNOWLEDGE")
    knowledge_pages = ["Knowledge Base", "Notes", "Transcriptions", "Chat"]

    all_pages = system_pages + knowledge_pages
    page = st.radio(
        "Navigation",
        all_pages,
        label_visibility="collapsed",
    )

    st.divider()

    # Auto-refresh (disable for Chat page to avoid losing input).
    if page != "Chat":
        auto_refresh = st.toggle("Auto-refresh", value=True)
        refresh_interval = st.select_slider(
            "Interval (sec)",
            options=[10, 15, 30, 60, 120],
            value=30,
            disabled=not auto_refresh,
        )
    else:
        auto_refresh = False

# -- Auto-refresh via JS ------------------------------------------------------

if auto_refresh:
    components.html(
        f"<script>setTimeout(function(){{window.parent.location.reload()}}"
        f",{refresh_interval * 1000})</script>",
        height=0,
    )

# -- Page router ---------------------------------------------------------------

if page == "System Status":
    from views.system_status import render
    render()

elif page == "Services":
    from views.services import render
    render()

elif page == "Event Log":
    from views.events import render
    render()

elif page == "Knowledge Base":
    from views.knowledge import render
    render()

elif page == "Notes":
    from views.notes import render
    render()

elif page == "Transcriptions":
    from views.transcriptions import render
    render()

elif page == "Chat":
    from views.chat import render
    render()
