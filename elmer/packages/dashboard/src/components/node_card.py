"""Reusable node status card component."""

from typing import Any

import streamlit as st

STATUS_INDICATORS = {
    "online": "🟢",
    "degraded": "🟡",
    "offline": "🔴",
    "unreachable": "🔴",
    "unknown": "⚪",
}


def render_node_card(node: dict[str, Any]) -> None:
    """Render a single node as a status card inside an st.container."""
    status = node.get("status", "unknown")
    indicator = STATUS_INDICATORS.get(status, "⚪")
    name = node.get("name", node.get("node_id", "?"))
    node_type = node.get("node_type", "unknown")
    host = node.get("host", "")
    metadata = node.get("metadata", {})
    last_seen = node.get("last_seen")

    with st.container(border=True):
        st.markdown(f"### {indicator} {name}")
        st.caption(f"{node_type} · {host or 'no address'}")

        # Key metrics
        cols = st.columns(3)

        cpu = metadata.get("cpu_percent")
        ram = metadata.get("ram_percent")
        temp = metadata.get("cpu_temp_c")

        cols[0].metric("CPU", f"{cpu}%" if cpu is not None else "—")
        cols[1].metric("RAM", f"{ram}%" if ram is not None else "—")

        gpu = metadata.get("gpu", {})
        gpu_temp = gpu.get("gpu_temp_c") if gpu else None
        if temp is not None:
            cols[2].metric("Temp", f"{temp}°C")
        elif gpu_temp is not None:
            cols[2].metric("GPU", f"{gpu_temp}°C")
        else:
            cols[2].metric("Temp", "—")

        # Last seen
        if last_seen:
            st.caption(f"Last seen: {last_seen}")
        else:
            st.caption("Last seen: never")

        # Services running on this node
        services = _services_for_node(node.get("node_id", ""))
        if services:
            st.caption(f"Services: {', '.join(services)}")

        # Expandable details
        with st.expander("Details"):
            if not metadata:
                st.info("No detailed metrics available.")
                return

            st.markdown(f"**Platform:** {metadata.get('platform', '—')}")
            st.markdown(f"**Hostname:** {metadata.get('hostname', '—')}")

            ram_used = metadata.get("ram_used_mb")
            ram_total = metadata.get("ram_total_mb")
            if ram_used and ram_total:
                st.markdown(f"**RAM:** {ram_used:,} / {ram_total:,} MB")

            disk_pct = metadata.get("disk_percent")
            if disk_pct is not None:
                disk_used = metadata.get("disk_used_gb", "?")
                disk_total = metadata.get("disk_total_gb", "?")
                st.markdown(
                    f"**Disk:** {disk_used} / {disk_total} GB ({disk_pct}%)"
                )

            if gpu:
                st.markdown("---")
                st.markdown(f"**GPU:** {gpu.get('name', '—')}")
                st.markdown(f"**GPU Util:** {gpu.get('gpu_percent', '—')}%")
                vram_used = gpu.get("vram_used_mb")
                vram_total = gpu.get("vram_total_mb")
                if vram_used and vram_total:
                    st.markdown(
                        f"**VRAM:** {vram_used:,.0f} / {vram_total:,.0f} MB"
                    )


# Map node IDs to the services they host.
_NODE_SERVICES: dict[str, list[str]] = {
    "core": ["Home Assistant", "Jellyfin", "Mosquitto"],
    "worker": ["Ollama", "Whisper"],
    "shackpi": ["AllStar"],
    "weatherpi": ["weewx", "Meshtastic"],
}


def _services_for_node(node_id: str) -> list[str]:
    return _NODE_SERVICES.get(node_id, [])
