"""Agents page — card-based management of agent definitions."""

import streamlit as st

from api_client import ElmerAPI

STATUS_ICON = {"enabled": "🟢", "disabled": "🔴"}


def render() -> None:
    st.header("Agents")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()
    agents = api.list_agents()

    if not agents:
        st.info("No agents defined yet. Use the Agent Builder to create one.")
        return

    # -- Summary row ----------------------------------------------------------

    enabled_count = sum(1 for a in agents if a.get("enabled"))
    disabled_count = len(agents) - enabled_count

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Agents", len(agents))
    c2.metric("Enabled", enabled_count)
    c3.metric("Disabled", disabled_count)

    st.divider()

    # -- Agent cards ----------------------------------------------------------

    for agent in agents:
        name = agent.get("name", "")
        display_name = agent.get("display_name") or name
        enabled = agent.get("enabled", False)
        icon = STATUS_ICON.get("enabled" if enabled else "disabled", "⚪")
        model = agent.get("model", "")
        description = agent.get("description", "")
        triggers = agent.get("triggers", [])
        tools = agent.get("tools", [])
        channels = agent.get("output_channels", [])

        with st.container(border=True):
            cols = st.columns([4, 2, 2])

            with cols[0]:
                st.markdown(f"### {icon} {display_name}")
                if description:
                    st.caption(description[:200])

            with cols[1]:
                st.markdown(f"**Model:** `{model}`")
                trigger_types = [t.get("type", "?") for t in triggers]
                if trigger_types:
                    st.caption(f"Triggers: {', '.join(trigger_types)}")
                if tools:
                    tool_names = [t.get("name", "?") for t in tools]
                    st.caption(f"Tools: {', '.join(tool_names)}")

            with cols[2]:
                # Enable/disable toggle
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if enabled:
                        if st.button("Disable", key=f"disable_{name}", type="secondary"):
                            api.disable_agent(name)
                            st.rerun()
                    else:
                        if st.button("Enable", key=f"enable_{name}", type="primary"):
                            api.enable_agent(name)
                            st.rerun()

                with btn_col2:
                    if enabled:
                        if st.button("Run", key=f"run_{name}", type="primary"):
                            with st.spinner(f"Running {display_name}..."):
                                result = api.trigger_agent_run(name)
                            if result:
                                st.success(f"Run started (ID: {result.get('id')})")
                            else:
                                st.error("Failed to start run")

            # -- Expandable details -------------------------------------------

            with st.expander("Details"):
                detail_tabs = st.tabs(["Config", "Triggers", "Tools", "Recent Runs"])

                with detail_tabs[0]:
                    st.markdown(f"**Name:** `{name}`")
                    st.markdown(f"**Model:** `{model}`")
                    current_temp = agent.get("temperature")
                    temp_display = f"{current_temp}" if current_temp is not None else "default"
                    st.markdown(f"**Temperature:** {temp_display}")
                    new_temp = st.slider(
                        "Temperature",
                        min_value=0.0, max_value=2.0, step=0.1,
                        value=current_temp if current_temp is not None else 0.7,
                        key=f"temp_{name}",
                    )
                    if (current_temp is None and new_temp != 0.7) or (
                        current_temp is not None and new_temp != current_temp
                    ):
                        if st.button("Save Temperature", key=f"save_temp_{name}", type="primary"):
                            api.update_agent(name, {"temperature": new_temp})
                            st.rerun()
                    st.markdown(f"**Max Concurrent:** {agent.get('max_concurrent', 1)}")
                    st.markdown(f"**Timeout:** {agent.get('timeout_seconds', 120)}s")
                    if channels:
                        st.markdown(f"**Output Channels:** {', '.join(channels)}")
                    if agent.get("config"):
                        st.json(agent["config"])
                    st.markdown("**System Prompt:**")
                    prompt_key = f"prompt_{name}"
                    current_prompt = agent.get("system_prompt", "")
                    new_prompt = st.text_area(
                        "System Prompt",
                        value=current_prompt,
                        height=200,
                        key=prompt_key,
                        label_visibility="collapsed",
                    )
                    if new_prompt != current_prompt:
                        if st.button("Save Prompt", key=f"save_prompt_{name}", type="primary"):
                            api.update_agent(name, {"system_prompt": new_prompt})
                            st.rerun()

                with detail_tabs[1]:
                    if not triggers:
                        st.caption("No triggers configured")
                    for i, trigger in enumerate(triggers):
                        t_type = trigger.get("type", "unknown")
                        st.markdown(f"**{i+1}. {t_type.upper()}**")
                        if t_type == "mqtt" and trigger.get("topic"):
                            st.markdown(f"  Topic: `{trigger['topic']}`")
                            if trigger.get("payload_filter"):
                                st.markdown(f"  Filter: `{trigger['payload_filter']}`")
                            debounce = trigger.get("config", {}).get("debounce_seconds")
                            if debounce:
                                st.caption(f"  Debounce: {debounce}s")
                        elif t_type == "schedule":
                            if trigger.get("cron"):
                                st.markdown(f"  Cron: `{trigger['cron']}`")
                            if trigger.get("interval_seconds"):
                                st.markdown(f"  Interval: {trigger['interval_seconds']}s")
                        elif t_type == "event":
                            st.markdown(f"  Event: `{trigger.get('event_type', '?')}`")
                        if trigger.get("config", {}).get("description"):
                            st.caption(f"  {trigger['config']['description']}")

                with detail_tabs[2]:
                    if not tools:
                        st.caption("No tools configured")
                    for tool in tools:
                        st.markdown(f"**{tool.get('name', '?')}** — {tool.get('description', '')}")
                        if tool.get("config"):
                            st.json(tool["config"])

                with detail_tabs[3]:
                    runs = api.list_agent_runs(name, limit=5)
                    if not runs:
                        st.caption("No runs yet")
                    for run in runs:
                        status = run.get("status", "?")
                        s_icon = {"completed": "✅", "failed": "❌", "pending": "⏳", "running": "🔄"}.get(status, "❓")
                        duration = run.get("duration_seconds")
                        dur_str = f" ({duration:.1f}s)" if duration else ""
                        started = run.get("started_at", "?")[:19] if run.get("started_at") else "?"
                        st.markdown(
                            f"{s_icon} **{status}** · {run.get('trigger_type', '?')} · {started}{dur_str}"
                        )

            # -- Delete button (in expander to prevent accidental clicks) ------

            with st.expander("Danger Zone"):
                if st.button(f"Delete {name}", key=f"delete_{name}", type="secondary"):
                    api.delete_agent(name)
                    st.rerun()
