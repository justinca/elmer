"""Agent Runs page — execution history with filters and statistics."""

from datetime import datetime

import streamlit as st

from api_client import ElmerAPI

STATUS_ICON = {
    "completed": "✅",
    "failed": "❌",
    "pending": "⏳",
    "running": "🔄",
}


def render() -> None:
    st.header("Agent Runs")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # -- Filters --------------------------------------------------------------

    fc1, fc2, fc3 = st.columns(3)

    with fc1:
        status_filter = st.selectbox(
            "Status", ["All", "completed", "failed", "pending", "running"]
        )

    with fc2:
        trigger_filter = st.selectbox(
            "Trigger Type", ["All", "api", "mqtt", "schedule", "event"]
        )

    with fc3:
        limit = st.select_slider("Limit", options=[20, 50, 100, 200], value=50)

    # -- Fetch runs -----------------------------------------------------------

    runs = api.list_all_runs(
        limit=limit,
        status=status_filter if status_filter != "All" else None,
        trigger_type=trigger_filter if trigger_filter != "All" else None,
    )

    # -- Statistics -----------------------------------------------------------

    if runs:
        total = len(runs)
        completed = sum(1 for r in runs if r.get("status") == "completed")
        failed = sum(1 for r in runs if r.get("status") == "failed")
        durations = [r["duration_seconds"] for r in runs if r.get("duration_seconds")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Runs", total)
        sc2.metric("Completed", completed)
        sc3.metric("Failed", failed)
        sc4.metric("Avg Duration", f"{avg_duration:.1f}s")

        # -- Runs by agent chart ----------------------------------------------

        agent_counts: dict[str, int] = {}
        for r in runs:
            aname = r.get("agent_name", "?")
            agent_counts[aname] = agent_counts.get(aname, 0) + 1

        if agent_counts:
            st.subheader("Runs by Agent")
            st.bar_chart(agent_counts)

        st.divider()

    # -- Run list -------------------------------------------------------------

    if not runs:
        st.info("No runs found matching the filters.")
        return

    for run in runs:
        run_id = run.get("id", "?")
        status = run.get("status", "?")
        icon = STATUS_ICON.get(status, "❓")
        agent_name = run.get("agent_name", "?")
        trigger_type = run.get("trigger_type", "?")
        started = run.get("started_at", "")
        completed_at = run.get("completed_at", "")
        duration = run.get("duration_seconds")

        # Format time.
        started_str = started[:19] if started else "?"
        dur_str = f"{duration:.1f}s" if duration else "—"

        with st.container(border=True):
            cols = st.columns([1, 3, 2, 2, 2])

            with cols[0]:
                st.markdown(f"**#{run_id}**")

            with cols[1]:
                st.markdown(f"{icon} **{agent_name}**")

            with cols[2]:
                st.caption(f"Trigger: {trigger_type}")

            with cols[3]:
                st.caption(f"Started: {started_str}")

            with cols[4]:
                st.caption(f"Duration: {dur_str}")

            # Expandable run details.
            with st.expander("Details"):
                detail = api.get_agent_run(run_id)
                if detail:
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        st.markdown(f"**Status:** {detail.get('status')}")
                        st.markdown(f"**Agent:** {detail.get('agent_name')}")
                        st.markdown(f"**Trigger:** {detail.get('trigger_type')}")
                        if detail.get("started_at"):
                            st.markdown(f"**Started:** {detail['started_at'][:19]}")
                        if detail.get("completed_at"):
                            st.markdown(f"**Completed:** {detail['completed_at'][:19]}")
                        if detail.get("duration_seconds"):
                            st.markdown(f"**Duration:** {detail['duration_seconds']:.1f}s")

                    with dc2:
                        if detail.get("error"):
                            st.error(f"Error: {detail['error']}")
                        if detail.get("trigger_data"):
                            st.markdown("**Trigger Data:**")
                            st.json(detail["trigger_data"])

                    if detail.get("input_data"):
                        st.markdown("**Input:**")
                        st.json(detail["input_data"])

                    if detail.get("output_data"):
                        st.markdown("**Output:**")
                        output = detail["output_data"]
                        # Show the response text prominently if present.
                        if isinstance(output, dict) and output.get("response"):
                            st.markdown(output["response"])
                        else:
                            st.json(output)
                else:
                    st.warning("Could not load run details.")
