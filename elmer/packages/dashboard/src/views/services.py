"""Services page — lists all services across Elmer nodes."""

import streamlit as st

from api_client import ElmerAPI

STATUS_ICON = {
    "online": "🟢",
    "ok": "🟢",
    "degraded": "🟡",
    "offline": "🔴",
    "unreachable": "🔴",
    "unknown": "⚪",
}

# Static service catalog — maps service names to their expected node.
SERVICE_CATALOG = [
    {
        "name": "AllStar",
        "node": "shackpi",
        "description": "Amateur radio link node",
    },
    {
        "name": "Home Assistant",
        "node": "core",
        "description": "Home automation hub (NUC)",
    },
    {
        "name": "Jellyfin",
        "node": "core",
        "description": "Media server (NUC)",
    },
    {
        "name": "Mosquitto",
        "node": "core",
        "description": "MQTT broker (NUC)",
    },
    {
        "name": "Ollama",
        "node": "worker",
        "description": "Local LLM inference",
    },
    {
        "name": "Whisper",
        "node": "worker",
        "description": "Speech-to-text",
    },
    {
        "name": "weewx",
        "node": "weatherpi",
        "description": "Weather station software",
    },
    {
        "name": "Meshtastic",
        "node": "weatherpi",
        "description": "LoRa mesh networking",
    },
]


def render() -> None:
    st.header("Services")

    api = ElmerAPI()
    nodes = api.get_nodes()
    node_map = {n.get("node_id", ""): n for n in nodes}

    # Fetch LLM models for the Ollama row.
    llm_models = api.get_llm_models()

    for svc in SERVICE_CATALOG:
        node_id = svc["node"]
        node = node_map.get(node_id)
        node_status = node.get("status", "unknown") if node else "unknown"
        metadata = node.get("metadata", {}) if node else {}
        icon = STATUS_ICON.get(node_status, "⚪")

        with st.container(border=True):
            cols = st.columns([3, 2, 4])

            with cols[0]:
                st.markdown(f"**{icon} {svc['name']}**")
                st.caption(svc["description"])

            with cols[1]:
                display_node = (
                    node.get("name", node_id) if node else node_id
                )
                st.markdown(f"Node: **{display_node}**")
                st.caption(f"Status: {node_status}")

            with cols[2]:
                _render_service_details(svc["name"], metadata, llm_models)


def _render_service_details(
    service_name: str,
    metadata: dict,
    llm_models: list[dict],
) -> None:
    """Render service-specific detail column."""
    if service_name == "Ollama" and llm_models:
        model_names = [m.get("name", "?") for m in llm_models[:5]]
        st.markdown(f"**Models:** {', '.join(model_names)}")
        gpu = metadata.get("gpu", {})
        if gpu:
            vram_used = gpu.get("vram_used_mb", 0)
            vram_total = gpu.get("vram_total_mb", 0)
            if vram_total:
                st.caption(
                    f"VRAM: {vram_used:,.0f} / {vram_total:,.0f} MB"
                )
    elif service_name == "Whisper":
        gpu = metadata.get("gpu", {})
        if gpu:
            st.caption(f"GPU: {gpu.get('name', '—')}")
        else:
            st.caption("Waiting for worker metrics")
    elif service_name == "Mosquitto":
        st.caption("Core connects on startup")
    elif service_name == "AllStar":
        st.caption("Radio link node")
    elif service_name == "Meshtastic":
        st.caption("LoRa mesh radio")
    else:
        cpu = metadata.get("cpu_percent")
        ram = metadata.get("ram_percent")
        if cpu is not None:
            st.caption(f"CPU: {cpu}% · RAM: {ram or '?'}%")
