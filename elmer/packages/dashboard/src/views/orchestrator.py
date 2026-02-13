"""Orchestrator page — real-time status, schedule, and controls."""

import streamlit as st

from api_client import ElmerAPI


def render() -> None:
    st.header("Orchestrator")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()
    status = api.get_orchestrator_status()

    if not status:
        st.error("Could not connect to the orchestrator. Is Elmer Core running?")
        return

    # -- Status cards ---------------------------------------------------------

    running = status.get("running", False)
    agents_registered = status.get("agents_registered", 0)
    queue_size = status.get("queue_size", 0)
    num_workers = status.get("workers", 0)
    running_agents = status.get("running_agents", [])

    sc1, sc2, sc3, sc4 = st.columns(4)

    with sc1:
        icon = "🟢" if running else "🔴"
        st.metric("Status", f"{icon} {'Running' if running else 'Stopped'}")

    with sc2:
        st.metric("Agents Registered", agents_registered)

    with sc3:
        st.metric("Queue Depth", queue_size)

    with sc4:
        st.metric("Workers", num_workers)

    # -- Currently running agents ---------------------------------------------

    if running_agents:
        st.subheader("Currently Running")
        for agent_info in running_agents:
            if isinstance(agent_info, str):
                st.markdown(f"🔄 **{agent_info}**")
            elif isinstance(agent_info, dict):
                st.markdown(f"🔄 **{agent_info.get('name', '?')}** (run #{agent_info.get('run_id', '?')})")
    else:
        st.info("No agents currently running.")

    st.divider()

    # -- Registered agents overview -------------------------------------------

    st.subheader("Registered Agents")
    agent_list = status.get("agents", [])
    if agent_list:
        for agent_info in agent_list:
            if isinstance(agent_info, dict):
                name = agent_info.get("name", "?")
                enabled = agent_info.get("enabled", False)
                triggers = agent_info.get("trigger_count", 0)
                icon = "🟢" if enabled else "🔴"
                st.markdown(f"{icon} **{name}** — {triggers} trigger(s)")
            else:
                st.markdown(f"- {agent_info}")
    else:
        st.caption("No agents registered.")

    st.divider()

    # -- Schedule view --------------------------------------------------------

    st.subheader("Scheduled Jobs")
    schedule = api.get_schedule()

    if not schedule:
        st.caption("No scheduled jobs.")
    else:
        for job in schedule:
            job_id = job.get("id", "?")
            next_run = job.get("next_run_time", "?")
            if isinstance(next_run, str) and len(next_run) > 19:
                next_run = next_run[:19]
            trigger_str = job.get("trigger", "?")

            with st.container(border=True):
                jc1, jc2, jc3 = st.columns([3, 3, 2])
                with jc1:
                    st.markdown(f"**{job_id}**")
                with jc2:
                    st.caption(f"Next run: {next_run}")
                with jc3:
                    st.caption(f"Trigger: {trigger_str}")

    st.divider()

    # -- Controls -------------------------------------------------------------

    st.subheader("Controls")
    cc1, cc2 = st.columns(2)

    with cc1:
        if st.button("Reload All Agents", type="primary"):
            with st.spinner("Reloading..."):
                result = api.reload_orchestrator()
            if result:
                st.success(f"Reloaded! {result}")
            else:
                st.error("Reload failed.")

    with cc2:
        st.caption("Reloads agent definitions from the database and re-registers all triggers.")
