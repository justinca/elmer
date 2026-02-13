"""Agent Builder page — form-based agent creation and editing."""

import json

import streamlit as st
import yaml

from api_client import ElmerAPI

# -- Templates ----------------------------------------------------------------

TEMPLATES = {
    "Blank": {
        "display_name": "",
        "description": "",
        "model": "llama3.1:8b",
        "system_prompt": "",
        "tools": [],
        "triggers": [],
        "output_channels": ["log"],
        "config": {},
        "max_concurrent": 1,
        "timeout_seconds": 120,
    },
    "Chat Assistant": {
        "display_name": "Chat Assistant",
        "description": "Responds to chat messages via MQTT.",
        "model": "llama3.1:8b",
        "system_prompt": (
            "You are a helpful assistant for the Elmer home lab. "
            "Answer questions clearly and concisely."
        ),
        "tools": [{"name": "search_knowledge", "description": "Search the knowledge base", "config": {"sources": ["docs", "notes"]}}],
        "triggers": [
            {"type": "api", "config": {"description": "On-demand via API"}},
            {"type": "mqtt", "topic": "elmer/chat/general", "config": {"description": "Respond to chat messages"}},
        ],
        "output_channels": ["mqtt", "log"],
        "config": {},
        "max_concurrent": 2,
        "timeout_seconds": 120,
    },
    "Scheduled Reporter": {
        "display_name": "Scheduled Reporter",
        "description": "Runs on a schedule and produces a summary report.",
        "model": "llama3.1:8b",
        "system_prompt": "You produce concise summary reports. Use bullet points.",
        "tools": [{"name": "query_database", "description": "Query the database for data", "config": {}}],
        "triggers": [
            {"type": "schedule", "cron": "0 8 * * *", "config": {"description": "Daily at 8am"}},
        ],
        "output_channels": ["telegram", "log"],
        "config": {},
        "max_concurrent": 1,
        "timeout_seconds": 60,
    },
    "Event Responder": {
        "display_name": "Event Responder",
        "description": "Reacts to system events like node going offline.",
        "model": "llama3.1:8b",
        "system_prompt": "You are a system event handler. Analyze events and suggest actions.",
        "tools": [{"name": "query_database", "description": "Query health data", "config": {}}],
        "triggers": [
            {"type": "event", "event_type": "node_offline", "config": {"description": "When a node goes offline"}},
        ],
        "output_channels": ["telegram", "mqtt", "log"],
        "config": {},
        "max_concurrent": 1,
        "timeout_seconds": 60,
    },
}


def render() -> None:
    api = ElmerAPI()

    # Determine if editing an existing agent.
    editing_name = st.session_state.get("edit_agent")
    if editing_name:
        st.header(f"Edit Agent: {editing_name}")
        existing = api.get_agent(editing_name)
        if not existing:
            st.error(f"Agent '{editing_name}' not found.")
            if st.button("Back to Agents"):
                st.session_state.pop("edit_agent", None)
                st.rerun()
            return
    else:
        st.header("Agent Builder")

    # -- Template selector (only for new agents) ------------------------------

    if not editing_name:
        template_name = st.selectbox("Start from template", list(TEMPLATES.keys()))
        template = TEMPLATES[template_name]
    else:
        template = existing  # type: ignore[assignment]

    # -- Basic info -----------------------------------------------------------

    st.subheader("Basic Info")
    bc1, bc2 = st.columns(2)

    with bc1:
        if editing_name:
            st.text_input("Name (read-only)", value=editing_name, disabled=True)
            agent_name = editing_name
        else:
            agent_name = st.text_input(
                "Name",
                value="",
                help="Lowercase, hyphens only (e.g. my-agent)",
                placeholder="my-agent",
            )

    with bc2:
        display_name = st.text_input(
            "Display Name",
            value=template.get("display_name", ""),
        )

    description = st.text_area(
        "Description",
        value=template.get("description", ""),
        height=80,
    )

    mc1, mc2 = st.columns(2)
    with mc1:
        model = st.text_input("Model", value=template.get("model", "llama3.1:8b"))
    with mc2:
        max_concurrent = st.number_input(
            "Max Concurrent Runs",
            min_value=1, max_value=10,
            value=template.get("max_concurrent", 1),
        )

    timeout = st.number_input(
        "Timeout (seconds)",
        min_value=10, max_value=600,
        value=template.get("timeout_seconds", 120),
    )

    # -- System prompt --------------------------------------------------------

    st.subheader("System Prompt")
    system_prompt = st.text_area(
        "System Prompt",
        value=template.get("system_prompt", ""),
        height=200,
        label_visibility="collapsed",
    )

    # -- Tools ----------------------------------------------------------------

    st.subheader("Tools")

    available_tools = api.list_tools()
    tool_options = {t["name"]: t for t in available_tools} if available_tools else {}

    # Initialize tool state from template.
    if "builder_tools" not in st.session_state:
        st.session_state.builder_tools = list(template.get("tools", []))

    for i, tool in enumerate(st.session_state.builder_tools):
        with st.container(border=True):
            tc1, tc2 = st.columns([4, 1])
            with tc1:
                tool_name = st.selectbox(
                    f"Tool {i+1}",
                    options=[""] + list(tool_options.keys()),
                    index=(list(tool_options.keys()).index(tool["name"]) + 1
                           if tool.get("name") in tool_options else 0),
                    key=f"tool_name_{i}",
                )
                if tool_name:
                    st.session_state.builder_tools[i]["name"] = tool_name
                    desc = tool_options.get(tool_name, {}).get("description", "")
                    st.session_state.builder_tools[i]["description"] = desc
                    st.caption(desc)
            with tc2:
                if st.button("Remove", key=f"rm_tool_{i}"):
                    st.session_state.builder_tools.pop(i)
                    st.rerun()

    if st.button("+ Add Tool"):
        st.session_state.builder_tools.append({"name": "", "description": "", "config": {}})
        st.rerun()

    # -- Triggers -------------------------------------------------------------

    st.subheader("Triggers")

    if "builder_triggers" not in st.session_state:
        st.session_state.builder_triggers = list(template.get("triggers", []))

    for i, trigger in enumerate(st.session_state.builder_triggers):
        with st.container(border=True):
            hc1, hc2 = st.columns([4, 1])
            with hc2:
                if st.button("Remove", key=f"rm_trigger_{i}"):
                    st.session_state.builder_triggers.pop(i)
                    st.rerun()

            with hc1:
                t_type = st.selectbox(
                    f"Trigger {i+1} Type",
                    options=["api", "mqtt", "schedule", "event"],
                    index=["api", "mqtt", "schedule", "event"].index(
                        trigger.get("type", "api")
                    ),
                    key=f"trigger_type_{i}",
                )
                st.session_state.builder_triggers[i]["type"] = t_type

            if t_type == "mqtt":
                topic = st.text_input(
                    "MQTT Topic",
                    value=trigger.get("topic", ""),
                    key=f"trigger_topic_{i}",
                    placeholder="elmer/chat/my-topic",
                )
                st.session_state.builder_triggers[i]["topic"] = topic

                filter_str = st.text_input(
                    "Payload Filter (JSON, optional)",
                    value=json.dumps(trigger.get("payload_filter", {})) if trigger.get("payload_filter") else "",
                    key=f"trigger_filter_{i}",
                    placeholder='{"status": "offline"}',
                )
                if filter_str:
                    try:
                        st.session_state.builder_triggers[i]["payload_filter"] = json.loads(filter_str)
                    except json.JSONDecodeError:
                        st.warning("Invalid JSON for payload filter")

                debounce = st.number_input(
                    "Debounce (seconds)",
                    min_value=0, max_value=3600,
                    value=trigger.get("config", {}).get("debounce_seconds", 0),
                    key=f"trigger_debounce_{i}",
                )
                if debounce > 0:
                    st.session_state.builder_triggers[i].setdefault("config", {})["debounce_seconds"] = debounce

            elif t_type == "schedule":
                sched_mode = st.radio(
                    "Schedule Mode",
                    ["Cron", "Interval"],
                    key=f"sched_mode_{i}",
                    horizontal=True,
                )
                if sched_mode == "Cron":
                    cron = st.text_input(
                        "Cron Expression (5-part)",
                        value=trigger.get("cron", ""),
                        key=f"trigger_cron_{i}",
                        placeholder="0 8 * * *",
                    )
                    st.session_state.builder_triggers[i]["cron"] = cron
                    st.session_state.builder_triggers[i].pop("interval_seconds", None)
                else:
                    interval = st.number_input(
                        "Interval (seconds)",
                        min_value=10, max_value=86400,
                        value=trigger.get("interval_seconds", 300),
                        key=f"trigger_interval_{i}",
                    )
                    st.session_state.builder_triggers[i]["interval_seconds"] = interval
                    st.session_state.builder_triggers[i].pop("cron", None)

            elif t_type == "event":
                event_type = st.text_input(
                    "Event Type",
                    value=trigger.get("event_type", ""),
                    key=f"trigger_event_{i}",
                    placeholder="node_offline",
                )
                st.session_state.builder_triggers[i]["event_type"] = event_type

    if st.button("+ Add Trigger"):
        st.session_state.builder_triggers.append({"type": "api", "config": {}})
        st.rerun()

    # -- Output channels ------------------------------------------------------

    st.subheader("Output Channels")
    all_channels = ["log", "mqtt", "telegram"]
    current_channels = template.get("output_channels", ["log"])
    selected_channels = st.multiselect(
        "Output Channels",
        options=all_channels,
        default=[c for c in current_channels if c in all_channels],
        label_visibility="collapsed",
    )

    # -- Config (advanced) ----------------------------------------------------

    st.subheader("Advanced Config")
    config_str = st.text_area(
        "Agent Config (JSON)",
        value=json.dumps(template.get("config", {}), indent=2),
        height=100,
        label_visibility="collapsed",
    )
    try:
        agent_config = json.loads(config_str) if config_str.strip() else {}
    except json.JSONDecodeError:
        st.warning("Invalid JSON in config")
        agent_config = {}

    # -- YAML preview ---------------------------------------------------------

    st.subheader("YAML Preview")

    # Build the full agent definition dict.
    agent_def = {
        "name": agent_name,
        "display_name": display_name,
        "description": description,
        "model": model,
        "system_prompt": system_prompt,
        "tools": [t for t in st.session_state.builder_tools if t.get("name")],
        "triggers": st.session_state.builder_triggers,
        "output_channels": selected_channels,
        "config": agent_config,
        "enabled": True,
        "max_concurrent": max_concurrent,
        "timeout_seconds": timeout,
    }

    st.code(yaml.dump(agent_def, default_flow_style=False, sort_keys=False), language="yaml")

    # -- Save / Update --------------------------------------------------------

    st.divider()
    sc1, sc2, sc3 = st.columns(3)

    with sc1:
        if editing_name:
            if st.button("Save Changes", type="primary"):
                payload = {k: v for k, v in agent_def.items() if k != "name"}
                result = api.update_agent(editing_name, payload)
                if result:
                    st.success(f"Agent '{editing_name}' updated!")
                    _clear_builder_state()
                else:
                    st.error("Failed to update agent.")
        else:
            if st.button("Create Agent", type="primary"):
                if not agent_name:
                    st.error("Agent name is required.")
                else:
                    result = api.create_agent(agent_def)
                    if result:
                        st.success(f"Agent '{agent_name}' created!")
                        _clear_builder_state()
                    else:
                        st.error("Failed to create agent. Name may already exist.")

    with sc2:
        if editing_name:
            if st.button("Cancel"):
                st.session_state.pop("edit_agent", None)
                _clear_builder_state()
                st.rerun()

    with sc3:
        if st.button("Test Run", disabled=not editing_name):
            with st.spinner("Running agent..."):
                result = api.trigger_agent_run(editing_name)
            if result:
                st.success(f"Test run started (ID: {result.get('id')})")
            else:
                st.error("Failed to start test run.")


def _clear_builder_state() -> None:
    """Remove builder session state keys so next render starts fresh."""
    st.session_state.pop("builder_tools", None)
    st.session_state.pop("builder_triggers", None)
