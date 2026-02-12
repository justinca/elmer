"""System Status page — displays health of all Elmer services."""

import os

import httpx
import streamlit as st

st.set_page_config(page_title="System Status", page_icon="🔍")
st.title("System Status")

CORE_URL = f"http://{os.getenv('ELMER_CORE_HOST', 'localhost')}:{os.getenv('ELMER_CORE_PORT', '8100')}"


def check_health(url: str) -> str:
    """Check a service health endpoint."""
    try:
        resp = httpx.get(f"{url}/health", timeout=3.0)
        if resp.status_code == 200:
            return "ok"
    except httpx.RequestError:
        pass
    return "unreachable"


services = {
    "Core API": f"{CORE_URL}",
    "Worker": f"http://{os.getenv('ELMER_WORKER_HOST', 'localhost')}:{os.getenv('ELMER_WORKER_PORT', '8101')}",
}

for name, url in services.items():
    status = check_health(url)
    icon = "🟢" if status == "ok" else "🔴"
    st.markdown(f"{icon} **{name}** — `{status}`")
