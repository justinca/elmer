"""Elmer Dashboard — Main Streamlit application."""

import streamlit as st
from streamlit_autorefresh import st_autorefresh

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

    all_pages = [
        "System Status", "Services", "Event Log",
        "Knowledge Base", "Notes", "Transcriptions", "Chat",
        "Agents", "Agent Builder", "Agent Runs", "Orchestrator",
    ]
    page = st.radio(
        "Navigation",
        all_pages,
        label_visibility="collapsed",
    )

    st.divider()

    # Auto-refresh (disable for Chat and builder pages to avoid losing input).
    no_refresh_pages = {"Chat", "Agent Builder"}
    if page not in no_refresh_pages:
        auto_refresh = st.toggle("Auto-refresh", value=True)
        refresh_interval = st.select_slider(
            "Interval (sec)",
            options=[10, 15, 30, 60, 120],
            value=30,
            disabled=not auto_refresh,
        )
    else:
        auto_refresh = False

# -- Auto-refresh (uses st.rerun internally — no full page reload) -----------

if auto_refresh:
    st_autorefresh(interval=refresh_interval * 1000, key="auto_refresh")

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

elif page == "Agents":
    from views.agents import render
    render()

elif page == "Agent Builder":
    from views.agent_builder import render
    render()

elif page == "Agent Runs":
    from views.agent_runs import render
    render()

elif page == "Orchestrator":
    from views.orchestrator import render
    render()
