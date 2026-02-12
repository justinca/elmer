"""System Status page — overview of all Elmer nodes."""

import streamlit as st

from api_client import ElmerAPI
from components.node_card import render_node_card

STATUS_ICON = {
    "online": "🟢",
    "ok": "🟢",
    "degraded": "🟡",
    "offline": "🔴",
    "unreachable": "🔴",
    "unknown": "⚪",
}


def render() -> None:
    st.header("System Status")

    api = ElmerAPI()
    health = api.get_health()
    nodes = api.get_nodes()

    core_status = health.get("status", "unknown")
    online_count = sum(1 for n in nodes if n.get("status") == "online")
    total_count = len(nodes)

    # -- Summary cards --------------------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Nodes Online", f"{online_count} / {total_count}")

    with c2:
        icon = STATUS_ICON.get(core_status, "⚪")
        st.metric("Core API", f"{icon} {core_status}")

    with c3:
        worker = next(
            (n for n in nodes if n.get("node_type") == "worker"), None
        )
        if worker:
            w_status = worker.get("status", "unknown")
            w_icon = STATUS_ICON.get(w_status, "⚪")
            gpu = worker.get("metadata", {}).get("gpu", {})
            gpu_temp = gpu.get("gpu_temp_c") if gpu else None
            label = f"{w_icon} {w_status}"
            if gpu_temp is not None:
                label += f" · GPU {gpu_temp}°C"
            st.metric("Worker", label)
        else:
            st.metric("Worker", "⚪ not registered")

    with c4:
        # MQTT connectivity is inferred from Core being up (Core connects to
        # the broker on startup and would report degraded if it couldn't).
        if core_status in ("ok", "online"):
            st.metric("MQTT Broker", "🟢 connected")
        else:
            st.metric("MQTT Broker", "⚪ unknown")

    st.divider()

    # -- Node grid ------------------------------------------------------------

    if not nodes:
        st.warning("No nodes found. Is Elmer Core running?")
        return

    cols_per_row = 3
    for i in range(0, len(nodes), cols_per_row):
        row = st.columns(cols_per_row)
        for j, col in enumerate(row):
            idx = i + j
            if idx < len(nodes):
                with col:
                    render_node_card(nodes[idx])
