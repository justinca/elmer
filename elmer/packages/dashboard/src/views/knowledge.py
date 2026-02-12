"""Knowledge Base page — search, sources, and ingestion management."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("Knowledge Base")

    api = ElmerAPI()
    sources = api.knowledge_sources()

    # -- Summary cards --------------------------------------------------------

    total_docs = sum(s.get("doc_count", 0) for s in sources
                     if s.get("source") not in ("obsidian",))
    total_notes = sum(s.get("doc_count", 0) for s in sources
                      if s.get("source") in ("obsidian",))
    transcriptions = api.get_transcriptions(limit=1)
    # Get total count by fetching a large offset.
    all_transcriptions = api.get_transcriptions(limit=200)
    total_transcriptions = len(all_transcriptions)

    latest_update = ""
    for s in sources:
        ts = s.get("latest_update", "")
        if ts and ts > latest_update:
            latest_update = ts

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documents", total_docs)
    c2.metric("Notes", total_notes)
    c3.metric("Transcriptions", total_transcriptions)
    c4.metric("Last Sync", latest_update[:16] if latest_update else "Never")

    # -- Source breakdown pie chart -------------------------------------------

    if sources:
        col_chart, col_sources = st.columns([1, 1])

        with col_chart:
            st.subheader("Sources Breakdown")
            labels = [s.get("source", "?") for s in sources]
            values = [s.get("doc_count", 0) for s in sources]
            fig = go.Figure(data=[go.Pie(
                labels=labels, values=values,
                hole=0.4,
                textinfo="label+value",
                marker=dict(colors=[
                    "#636EFA", "#EF553B", "#00CC96", "#AB63FA",
                    "#FFA15A", "#19D3F3", "#FF6692", "#B6E880",
                ]),
            )])
            fig.update_layout(
                showlegend=False,
                margin=dict(l=20, r=20, t=20, b=20),
                height=300,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_sources:
            _render_source_management(api, sources)
    else:
        st.info("No knowledge sources found. Ingest some documents to get started.")

    st.divider()

    # -- Semantic search ------------------------------------------------------

    st.subheader("Semantic Search")
    query = st.text_input(
        "Search query",
        placeholder="e.g. antenna setup, network config, radio frequencies",
        label_visibility="collapsed",
    )

    if query:
        with st.spinner("Searching..."):
            result = api.knowledge_search(query, limit=8, threshold=0.2)

        if result is None:
            st.error("Could not reach the knowledge service.")
        else:
            results = result.get("results", [])
            if not results:
                st.info(f'No results for "{query}".')
            else:
                st.caption(f"{len(results)} results")
                for i, r in enumerate(results):
                    score = r.get("score", 0)
                    source = r.get("source", "?")
                    content = r.get("content", "")
                    snippet = content[:200].replace("\n", " ")
                    rid = r.get("id", "")
                    meta = r.get("metadata", {})

                    score_pct = f"{score:.0%}"
                    bar_len = round(score * 10)
                    bar = "\u2588" * bar_len + "\u2591" * (10 - bar_len)

                    with st.container(border=True):
                        cols = st.columns([1, 6])
                        with cols[0]:
                            st.markdown(f"**{score_pct}**")
                            st.caption(bar)
                        with cols[1]:
                            st.markdown(f"**{source}** #{rid}")
                            st.caption(snippet)
                            with st.expander("Full content"):
                                st.text(content[:3000])


def _render_source_management(api: ElmerAPI, sources: list[dict]) -> None:
    """Source list with management buttons."""
    st.subheader("Source Management")

    for s in sources:
        name = s.get("source", "?")
        count = s.get("doc_count", 0)
        updated = (s.get("latest_update") or "")[:16]

        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(f"**{name}**")
                st.caption(f"{count} chunks \u00b7 {updated}")
            with cols[1]:
                if st.button("Re-ingest", key=f"reingest_{name}", type="secondary"):
                    with st.spinner("Ingesting..."):
                        result = api.knowledge_ingest_directory(
                            "/data/docs", name, ["*.md"],
                        )
                    if result:
                        ingested = result.get("ingested", 0)
                        st.success(f"Done: {ingested} files")
                    else:
                        st.error("Ingest failed")
            with cols[2]:
                if st.button("Delete", key=f"delete_{name}", type="secondary"):
                    result = api.knowledge_delete_source(name)
                    if result:
                        deleted = result.get("deleted_count", 0)
                        st.success(f"Deleted {deleted} chunks")
                        st.rerun()
                    else:
                        st.error("Delete failed")
