"""Elmer Dashboard — Main Streamlit application."""

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Elmer Dashboard",
    page_icon="\U0001f4e1",
    layout="wide",
)

# -- Navigation groups --------------------------------------------------------

_NAV_GROUPS = [
    ("Radio", ["Propagation", "DX Spots", "Log Analysis", "POTA", "Contests"]),
    ("System", ["System Status", "Services", "Event Log"]),
    ("Knowledge", ["Knowledge Base", "Notes", "Transcriptions", "Chat"]),
    ("Agents", ["Agents", "Agent Builder", "Agent Runs", "Orchestrator"]),
]

# Flat list for the radio widget (Streamlit radio doesn't support groups).
_ALL_PAGES = [p for _, pages in _NAV_GROUPS for p in pages]

# -- Sidebar ------------------------------------------------------------------

if "page" not in st.session_state:
    st.session_state.page = "Propagation"


def _nav_to(p: str) -> None:
    st.session_state.page = p


with st.sidebar:
    st.markdown("## \U0001f4e1 Elmer")
    st.caption("Home Lab OS \u00b7 v0.2.0")

    for group_name, pages in _NAV_GROUPS:
        st.divider()
        st.caption(group_name.upper())
        for p in pages:
            is_active = st.session_state.page == p
            st.button(
                p,
                key=f"nav_{p}",
                on_click=_nav_to,
                args=(p,),
                use_container_width=True,
                type="primary" if is_active else "secondary",
            )

    st.divider()

    page = st.session_state.page

    # Auto-refresh (disable for Chat and builder pages to avoid losing input).
    no_refresh_pages = {"Chat", "Agent Builder", "Transcriptions"}
    if page not in no_refresh_pages:
        auto_refresh = st.toggle("Auto-refresh", value=True)
        refresh_interval = st.select_slider(
            "Interval (sec)",
            options=[10, 15, 30, 60, 120, 300],
            value=30,
            disabled=not auto_refresh,
        )
    else:
        auto_refresh = False

# -- Auto-refresh (uses st.rerun internally — no full page reload) -----------

if auto_refresh:
    st_autorefresh(interval=refresh_interval * 1000, key="auto_refresh")

# -- Page router ---------------------------------------------------------------

page = st.session_state.page

# Radio group — new enhanced pages.
if page == "Propagation":
    from pages.propagation import render
    render()

elif page == "DX Spots":
    from pages.dx_spots import render
    render()

elif page == "Log Analysis":
    from pages.log_analysis import render
    render()

elif page == "POTA":
    from pages.pota import render
    render()

elif page == "Contests":
    from pages.contest import render
    render()

# System group.
elif page == "System Status":
    from views.system_status import render
    render()

elif page == "Services":
    from views.services import render
    render()

elif page == "Event Log":
    from views.events import render
    render()

# Knowledge group.
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

# Agents group.
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
