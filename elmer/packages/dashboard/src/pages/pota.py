"""POTA — live spots, park search, activation planner, nearby parks."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("POTA")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    tab_spots, tab_nearby, tab_search, tab_planner = st.tabs(
        ["Live Spots", "Nearby Parks", "Park Search", "Activation Planner"]
    )

    with tab_spots:
        _render_spots(api)

    with tab_nearby:
        _render_nearby(api)

    with tab_search:
        _render_search(api)

    with tab_planner:
        _render_planner(api)


# ── Live Spots ───────────────────────────────────────────────────────────


def _render_spots(api: ElmerAPI) -> None:
    """Current POTA activator spots with filters."""
    spots = api.get_pota_spots()

    if not spots:
        st.info("No active POTA spots right now.")
        return

    # Filters.
    f1, f2, f3 = st.columns(3)

    all_bands = sorted({_freq_to_band(s.get("frequency", "")) for s in spots} - {""})
    with f1:
        band_filter = st.selectbox("Band", ["All"] + all_bands, key="pota_spot_band")

    all_states = sorted({s.get("location_desc", "") for s in spots if s.get("location_desc")})
    with f2:
        state_filter = st.selectbox("Location", ["All"] + all_states, key="pota_spot_state")

    with f3:
        mode_filter = st.selectbox(
            "Mode", ["All"] + sorted({s.get("mode", "") for s in spots if s.get("mode")}),
            key="pota_spot_mode",
        )

    filtered = spots
    if band_filter != "All":
        filtered = [s for s in filtered if _freq_to_band(s.get("frequency", "")) == band_filter]
    if state_filter != "All":
        filtered = [s for s in filtered if s.get("location_desc") == state_filter]
    if mode_filter != "All":
        filtered = [s for s in filtered if s.get("mode") == mode_filter]

    st.caption(f"{len(filtered)} active spots")

    # Column headers.
    hdr = st.columns([1.2, 1.5, 1.5, 1, 1, 2.5, 1.5])
    hdr[0].markdown("**Time**")
    hdr[1].markdown("**Activator**")
    hdr[2].markdown("**Park**")
    hdr[3].markdown("**Freq**")
    hdr[4].markdown("**Mode**")
    hdr[5].markdown("**Park Name**")
    hdr[6].markdown("**Location**")

    for s in filtered[:60]:
        activator = s.get("activator", "?")
        ref = s.get("reference", "")
        park = s.get("park_name", "")
        freq = s.get("frequency", "")
        mode = s.get("mode", "")
        loc = s.get("location_desc", "")
        comments = s.get("comments", "")
        spot_time = (s.get("spot_time", "") or "")[:19]
        time_display = spot_time[11:16] if len(spot_time) > 11 else spot_time

        cols = st.columns([1.2, 1.5, 1.5, 1, 1, 2.5, 1.5])
        cols[0].caption(time_display)
        cols[1].markdown(f"**{activator}**")
        cols[2].caption(ref)
        cols[3].caption(f"{freq} kHz")
        cols[4].caption(mode)
        cols[5].caption(park[:35])
        cols[6].caption(loc)


# ── Nearby Parks ─────────────────────────────────────────────────────────


def _render_nearby(api: ElmerAPI) -> None:
    """Parks near home grid with distance and activation counts."""
    col_grid, col_radius = st.columns(2)
    with col_grid:
        grid = st.text_input("Grid square", value="DN70", key="pota_nearby_grid")
    with col_radius:
        radius = st.slider("Radius (miles)", 10, 200, 50, key="pota_nearby_radius")

    parks = api.get_pota_nearby_parks(grid=grid or None, radius=radius)

    if not parks:
        st.info("No parks found. Check the grid square and try a larger radius.")
        return

    st.caption(f"{len(parks)} parks within {radius} miles")

    # Park type breakdown chart.
    types: dict[str, int] = {}
    for p in parks:
        pt = p.get("park_type", "Other") or "Other"
        types[pt] = types.get(pt, 0) + 1

    if types:
        fig = go.Figure(data=[go.Bar(
            x=list(types.keys()),
            y=list(types.values()),
            marker_color="#636EFA",
            text=list(types.values()),
            textposition="outside",
        )])
        fig.update_layout(
            height=220,
            margin=dict(l=40, r=20, t=20, b=30),
            xaxis_title="Park Type",
            yaxis_title="Count",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Park list.
    hdr = st.columns([1.5, 3, 1.5, 1.5])
    hdr[0].markdown("**Reference**")
    hdr[1].markdown("**Park Name**")
    hdr[2].markdown("**Distance**")
    hdr[3].markdown("**Activations**")

    for p in parks[:40]:
        ref = p.get("reference", "")
        name = p.get("name", "")
        dist = p.get("distance_miles")
        activations = p.get("activations", 0)
        park_type = p.get("park_type", "")

        dist_str = f"{dist:.1f} mi" if dist is not None else "—"
        type_str = f" ({park_type})" if park_type else ""

        cols = st.columns([1.5, 3, 1.5, 1.5])
        cols[0].markdown(f"**{ref}**")
        cols[1].caption(f"{name}{type_str}")
        cols[2].caption(dist_str)
        cols[3].caption(str(activations))


# ── Park Search ──────────────────────────────────────────────────────────


def _render_search(api: ElmerAPI) -> None:
    """Search parks by state and name."""
    col_state, col_name = st.columns(2)
    with col_state:
        state = st.text_input("Location code", value="US-CO", key="pota_search_state",
                              placeholder="e.g. US-CO, VE-AB")
    with col_name:
        name = st.text_input("Park name", key="pota_search_name",
                             placeholder="e.g. Rocky Mountain")

    if not state and not name:
        st.caption("Enter a location code and/or park name to search.")
        return

    parks = api.search_pota_parks(state=state or None, name=name or None)

    if not parks:
        st.info("No parks found matching criteria.")
        return

    st.caption(f"{len(parks)} parks found")

    for p in parks[:50]:
        ref = p.get("reference", "")
        pname = p.get("name", "")
        park_type = p.get("park_type", "")
        activations = p.get("activations", 0)
        active = p.get("active", True)

        status = "" if active else " (inactive)"

        with st.container(border=True):
            cols = st.columns([1.5, 3, 1.5, 1])
            with cols[0]:
                st.markdown(f"**{ref}**")
            with cols[1]:
                st.caption(f"{pname} ({park_type}){status}")
            with cols[2]:
                dist = p.get("distance_miles")
                if dist is not None:
                    st.caption(f"{dist:.1f} mi")
            with cols[3]:
                st.caption(f"{activations} act.")


# ── Activation Planner ───────────────────────────────────────────────────


def _render_planner(api: ElmerAPI) -> None:
    """Full activation plan for a specific park."""
    park_ref = st.text_input("Park reference", key="pota_plan_ref",
                             placeholder="e.g. US-1228")

    if not park_ref:
        st.caption("Enter a park reference to plan an activation.")
        return

    if st.button("Plan Activation", type="primary", key="pota_plan_btn"):
        with st.spinner("Building activation plan..."):
            plan = api.get_pota_plan(park_ref)

        if not plan:
            st.error(f"Could not find park '{park_ref}'. Check the reference.")
            return

        park = plan.get("park", {})

        # Park info header.
        st.subheader(f"{park.get('reference', '')} — {park.get('name', '')}")

        # Metrics row.
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Distance", f"{plan.get('distance_miles', 0)} mi")
        with m2:
            st.metric("Bearing", f"{plan.get('bearing', 0):.0f}\u00b0")
        with m3:
            st.metric("Activations", park.get("activations", 0))
        with m4:
            st.metric("Total QSOs", f"{park.get('contacts', 0):,}")

        st.caption(
            f"Grid: {park.get('grid4', '')} | "
            f"Type: {park.get('park_type', '')} | "
            f"Access: {park.get('access_methods', 'Unknown')}"
        )

        if park.get("website"):
            st.caption(f"Website: {park['website']}")

        # Band recommendations.
        recs = plan.get("band_recommendations", [])
        if recs:
            st.subheader("Band Recommendations")
            for r in recs:
                cond = r.get("condition", "?")
                cond_colors = {"Good": "#00CC96", "Fair": "#FFA15A", "Poor": "#EF553B"}
                color = cond_colors.get(cond, "#636EFA")
                st.markdown(
                    f'<span style="color:{color};font-weight:bold;">'
                    f'{r.get("band", "?")} {r.get("mode", "")}</span>'
                    f' ({r.get("time_window", "")}) — {cond} — '
                    f'<em>{r.get("rationale", "")}</em>',
                    unsafe_allow_html=True,
                )

        # Nearby parks for multi-park activation.
        nearby = plan.get("nearby_parks", [])
        if nearby:
            st.subheader(f"Nearby Parks ({len(nearby)} within 30 mi)")
            for n in nearby[:8]:
                dist = n.get("distance_miles")
                dist_str = f"{dist:.1f} mi" if dist is not None else "—"
                st.caption(
                    f"**{n.get('reference', '')}** {n.get('name', '')} — "
                    f"{dist_str} ({n.get('activations', 0)} activations)"
                )

        # Active spots at this park.
        park_spots = plan.get("current_spots_at_park", [])
        if park_spots:
            st.subheader("Active Spots at This Park")
            for s in park_spots:
                st.caption(
                    f"{s.get('activator', '?')} on {s.get('frequency', '?')} kHz "
                    f"{s.get('mode', '')}"
                )

        # Notes.
        notes = plan.get("notes", [])
        if notes:
            st.subheader("Notes")
            for note in notes:
                st.caption(f"- {note}")


# ── Helpers ──────────────────────────────────────────────────────────────


def _freq_to_band(freq_str: str) -> str:
    """Convert a frequency string (kHz) to a band name."""
    try:
        freq = float(freq_str)
    except (ValueError, TypeError):
        return ""

    if 1800 <= freq <= 2000:
        return "160m"
    elif 3500 <= freq <= 4000:
        return "80m"
    elif 5330 <= freq <= 5410:
        return "60m"
    elif 7000 <= freq <= 7300:
        return "40m"
    elif 10100 <= freq <= 10150:
        return "30m"
    elif 14000 <= freq <= 14350:
        return "20m"
    elif 18068 <= freq <= 18168:
        return "17m"
    elif 21000 <= freq <= 21450:
        return "15m"
    elif 24890 <= freq <= 24990:
        return "12m"
    elif 28000 <= freq <= 29700:
        return "10m"
    elif 50000 <= freq <= 54000:
        return "6m"
    elif 144000 <= freq <= 148000:
        return "2m"
    return ""
