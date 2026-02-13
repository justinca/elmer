"""POTA page — live spots, nearby parks, search, activation planner."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("POTA")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    tab_spots, tab_nearby, tab_search, tab_plan = st.tabs(
        ["Live Spots", "Nearby Parks", "Park Search", "Activation Planner"]
    )

    with tab_spots:
        _render_spots(api)

    with tab_nearby:
        _render_nearby(api)

    with tab_search:
        _render_search(api)

    with tab_plan:
        _render_planner(api)


def _render_spots(api: ElmerAPI) -> None:
    """Current POTA activator spots."""
    spots = api.get_pota_spots()

    if not spots:
        st.info("No active POTA spots right now.")
        return

    # Band filter.
    all_bands = sorted({s.get("frequency", "")[:2] for s in spots if s.get("frequency")})
    band_filter = st.selectbox("Filter by frequency", ["All"] + all_bands, key="pota_spot_band")

    filtered = spots
    if band_filter != "All":
        filtered = [s for s in spots if s.get("frequency", "").startswith(band_filter)]

    st.caption(f"{len(filtered)} active spots")

    for s in filtered[:50]:
        activator = s.get("activator", "?")
        ref = s.get("reference", "")
        park = s.get("park_name", "")
        freq = s.get("frequency", "")
        mode = s.get("mode", "")
        loc = s.get("location_desc", "")
        spotter = s.get("spotter", "")
        comments = s.get("comments", "")
        spot_time = (s.get("spot_time", "") or "")[:19]

        with st.container(border=True):
            cols = st.columns([2, 2, 3, 1])
            with cols[0]:
                st.markdown(f"**{activator}** @ {ref}")
            with cols[1]:
                st.caption(f"{freq} kHz {mode} ({loc})")
            with cols[2]:
                st.caption(f"{park}")
                if comments:
                    st.caption(f"_{comments[:60]}_")
            with cols[3]:
                st.caption(spot_time[11:] if len(spot_time) > 11 else spot_time)


def _render_nearby(api: ElmerAPI) -> None:
    """Parks near home grid."""
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
        )])
        fig.update_layout(
            height=200,
            margin=dict(l=40, r=20, t=20, b=30),
            xaxis_title="Park Type",
            yaxis_title="Count",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig, use_container_width=True)

    for p in parks[:30]:
        ref = p.get("reference", "")
        name = p.get("name", "")
        dist = p.get("distance_miles")
        activations = p.get("activations", 0)
        park_type = p.get("park_type", "")
        grid4 = p.get("grid4", "")

        dist_str = f"{dist:.1f} mi" if dist is not None else ""

        with st.container(border=True):
            cols = st.columns([1.5, 3, 1.5, 1])
            with cols[0]:
                st.markdown(f"**{ref}**")
            with cols[1]:
                st.caption(f"{name} ({park_type})")
            with cols[2]:
                st.caption(f"{dist_str} — {grid4}")
            with cols[3]:
                st.caption(f"{activations} activations")


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
        grid4 = p.get("grid4", "")
        activations = p.get("activations", 0)
        active = p.get("active", True)

        status = "" if active else " (inactive)"

        with st.container(border=True):
            cols = st.columns([1.5, 3, 1, 1])
            with cols[0]:
                st.markdown(f"**{ref}**")
            with cols[1]:
                st.caption(f"{pname} ({park_type}){status}")
            with cols[2]:
                st.caption(grid4)
            with cols[3]:
                st.caption(f"{activations} act.")


def _render_planner(api: ElmerAPI) -> None:
    """Activation planner for a specific park."""
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

        # Park info.
        st.subheader(f"{park.get('reference', '')} — {park.get('name', '')}")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Distance", f"{plan.get('distance_miles', 0)} mi")
        with c2:
            st.metric("Bearing", f"{plan.get('bearing', 0):.0f}\u00b0")
        with c3:
            st.metric("Activations", park.get("activations", 0))
        with c4:
            st.metric("Total QSOs", park.get("contacts", 0))

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
                color = {"Good": "green", "Fair": "orange"}.get(cond, "red")
                st.markdown(
                    f"**{r.get('band', '?')} {r.get('mode', '')}** "
                    f"({r.get('time_window', '')}) — "
                    f":{color}_circle: {cond} — "
                    f"_{r.get('rationale', '')}_"
                )

        # Nearby parks.
        nearby = plan.get("nearby_parks", [])
        if nearby:
            st.subheader(f"Nearby Parks ({len(nearby)} within 30 mi)")
            for n in nearby[:5]:
                dist = n.get("distance_miles")
                dist_str = f"{dist:.1f} mi" if dist is not None else ""
                st.caption(
                    f"**{n.get('reference', '')}** {n.get('name', '')} — "
                    f"{dist_str} ({n.get('activations', 0)} activations)"
                )

        # Current spots at this park.
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
