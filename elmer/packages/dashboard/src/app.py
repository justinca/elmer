"""Elmer Dashboard — Main Streamlit application."""

import streamlit as st

st.set_page_config(
    page_title="Elmer Dashboard",
    page_icon="📡",
    layout="wide",
)

st.title("Elmer — Home Lab Dashboard")
st.markdown(
    "Central monitoring and control for your amateur radio station, "
    "home automation, and self-hosted services."
)

st.markdown("---")
st.markdown("Navigate using the sidebar to view system status and controls.")
