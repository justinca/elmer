"""Knowledge Base page — search, sources, and ingestion management."""

import streamlit as st
import plotly.graph_objects as go

from api_client import ElmerAPI


def render() -> None:
    st.header("Knowledge Base")
    _render_data()


@st.fragment
def _render_data() -> None:
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

    # -- Tabs: Semantic Search / Web Search -----------------------------------

    tab_semantic, tab_web = st.tabs([
        "\U0001f50d Semantic Search",
        "\U0001f310 Web Search",
    ])

    with tab_semantic:
        _render_semantic_search(api)

    with tab_web:
        _render_web_search(api)


def _render_semantic_search(api: ElmerAPI) -> None:
    """Semantic search across the knowledge base."""
    query = st.text_input(
        "Search query",
        placeholder="e.g. antenna setup, network config, radio frequencies",
        label_visibility="collapsed",
        key="kb_semantic_query",
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


def _render_web_search(api: ElmerAPI) -> None:
    """Web search interface with option to save results to knowledge base."""
    query = st.text_input(
        "Web search query",
        placeholder="e.g. IC-7300 operating manual, solar flux forecast",
        label_visibility="collapsed",
        key="kb_web_query",
    )

    if "web_results" not in st.session_state:
        st.session_state.web_results = []

    col_search, col_type = st.columns([3, 1])
    with col_type:
        search_type = st.selectbox(
            "Type", ["text", "news"], label_visibility="collapsed",
            key="kb_web_type",
        )

    if query:
        with st.spinner("\U0001f310 Searching the web..."):
            data = api.web_search(query, max_results=5, search_type=search_type)

        if data is None:
            st.error("Web search failed.")
            return

        results = data.get("results", [])
        st.session_state.web_results = results

        if not results:
            st.info(f'No web results for "{query}".')
            return

        st.caption(f"{len(results)} results")

        for i, r in enumerate(results):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            snippet = r.get("snippet", "")

            with st.container(border=True):
                st.markdown(f"**{i + 1}. {title}**")
                if url:
                    st.markdown(f"[{url}]({url})")
                if snippet:
                    st.caption(snippet)

                # Action buttons.
                btn_cols = st.columns([1, 1, 3])
                with btn_cols[0]:
                    if st.button(
                        "Fetch Page",
                        key=f"fetch_{i}",
                        type="secondary",
                    ):
                        with st.spinner("Fetching..."):
                            page_text = api.web_fetch_page(url)
                        if page_text:
                            st.session_state[f"fetched_{i}"] = page_text
                            st.rerun()
                        else:
                            st.warning("Could not fetch page content.")

                with btn_cols[1]:
                    fetched = st.session_state.get(f"fetched_{i}", "")
                    if fetched and st.button(
                        "Save to KB",
                        key=f"save_{i}",
                        type="primary",
                    ):
                        with st.spinner("Saving..."):
                            result = api.knowledge_ingest_text(
                                text=fetched,
                                title=title,
                                source="web",
                            )
                        if result:
                            chunks = result.get("chunks_stored", 0)
                            st.success(
                                f"Saved \"{title}\" ({chunks} chunks)"
                            )
                        else:
                            st.error("Failed to save to knowledge base.")

                # Show fetched content if available.
                fetched = st.session_state.get(f"fetched_{i}", "")
                if fetched:
                    with st.expander(
                        f"Page content ({len(fetched):,} chars)", expanded=False,
                    ):
                        st.text(fetched[:5000])
                        if len(fetched) > 5000:
                            st.caption(
                                f"... {len(fetched) - 5000:,} more characters"
                            )


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
