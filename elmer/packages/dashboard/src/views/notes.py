"""Obsidian Notes page — browse and sync notes from the knowledge base."""

import streamlit as st

from api_client import ElmerAPI


def render() -> None:
    st.header("Obsidian Notes")
    _render_data()


@st.fragment
def _render_data() -> None:
    api = ElmerAPI()

    # -- Sync controls --------------------------------------------------------

    st.subheader("Sync")
    col_sync, col_status = st.columns([1, 2])

    with col_sync:
        if st.button("Sync Docs", type="primary"):
            with st.spinner("Syncing documents..."):
                result = api.knowledge_ingest_directory(
                    "/data/docs", "elmer-docs", ["*.md"],
                )
            if result:
                ingested = result.get("ingested", 0)
                skipped = result.get("skipped", 0)
                errors = result.get("errors", [])
                if errors:
                    st.warning(
                        f"Done: {ingested} ingested, {skipped} skipped, "
                        f"{len(errors)} errors"
                    )
                else:
                    st.success(
                        f"Done: {ingested} ingested, {skipped} skipped"
                    )
            else:
                st.error("Sync failed. Is Core API running?")

    with col_status:
        sources = api.knowledge_sources()
        obsidian_src = next(
            (s for s in sources if s.get("source") == "obsidian"), None,
        )
        docs_src = next(
            (s for s in sources if s.get("source") == "elmer-docs"), None,
        )

        if obsidian_src:
            count = obsidian_src.get("doc_count", 0)
            updated = (obsidian_src.get("latest_update") or "")[:16]
            st.caption(f"Obsidian: {count} chunks (last sync: {updated})")

        if docs_src:
            count = docs_src.get("doc_count", 0)
            updated = (docs_src.get("latest_update") or "")[:16]
            st.caption(f"Elmer Docs: {count} chunks (last sync: {updated})")

        if not obsidian_src and not docs_src:
            st.caption("No notes synced yet.")

    st.divider()

    # -- Notes browser --------------------------------------------------------

    st.subheader("Notes Browser")

    # Fetch notes from the knowledge search (notes source).
    # We search with a broad query to list notes.
    notes = api.get_notes(limit=50)

    if not notes:
        # Fallback: search knowledge base for notes source.
        result = api.knowledge_search("", limit=20, threshold=0.0,
                                       sources=["notes"])
        if result:
            notes_results = result.get("results", [])
        else:
            notes_results = []

        if notes_results:
            st.caption(f"{len(notes_results)} notes found via search")
            _render_search_notes(notes_results)
        else:
            st.info(
                "No notes found. Notes appear here when Obsidian sync "
                "is configured and has run at least once."
            )
        _render_docs_section(api)
        return

    # Extract unique tags for filtering.
    all_tags: dict[str, int] = {}
    for n in notes:
        tags = n.get("tags") or n.get("metadata", {}).get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                all_tags[tag] = all_tags.get(tag, 0) + 1

    # Filter controls.
    col_filter, col_count = st.columns([3, 1])

    with col_filter:
        if all_tags:
            tag_options = ["All"] + sorted(all_tags.keys())
            selected_tag = st.selectbox("Filter by tag", tag_options)
        else:
            selected_tag = "All"

    with col_count:
        st.metric("Total Notes", len(notes))

    # Apply tag filter.
    if selected_tag != "All":
        notes = [
            n for n in notes
            if selected_tag in (
                n.get("tags") or n.get("metadata", {}).get("tags", [])
            )
        ]

    # Render notes list.
    for n in notes:
        title = n.get("title", "Untitled")
        nid = n.get("id", "?")
        modified = (n.get("updated_at") or n.get("created_at") or "")[:16]
        tags = n.get("tags") or n.get("metadata", {}).get("tags", [])
        content_preview = (n.get("content") or "")[:150].replace("\n", " ")

        with st.container(border=True):
            cols = st.columns([4, 1])
            with cols[0]:
                st.markdown(f"**{title}** `#{nid}`")
                if tags and isinstance(tags, list):
                    tag_str = " ".join(f"`{t}`" for t in tags[:5])
                    st.caption(tag_str)
                if content_preview:
                    st.caption(content_preview)
            with cols[1]:
                st.caption(modified)

            with st.expander("View note"):
                detail = api.get_note(nid) if isinstance(nid, int) else None
                if detail:
                    st.markdown(detail.get("content", "No content"))
                elif content_preview:
                    st.text(n.get("content", "Content not available"))
                else:
                    st.info("Could not load note content.")

    # -- Tag cloud ------------------------------------------------------------

    if all_tags:
        st.divider()
        st.subheader("Tags")
        # Simple tag cloud using varying markdown sizes.
        max_count = max(all_tags.values()) if all_tags else 1
        tag_parts = []
        for tag, count in sorted(all_tags.items()):
            # Scale from small to large based on relative frequency.
            tag_parts.append(f"`{tag}` ({count})")
        st.markdown(" \u00b7 ".join(tag_parts))

    # -- Docs section ---------------------------------------------------------

    _render_docs_section(api)


def _render_search_notes(results: list[dict]) -> None:
    """Render notes from search results."""
    for r in results:
        content = r.get("content", "")
        source = r.get("source", "")
        rid = r.get("id", "?")
        snippet = content[:200].replace("\n", " ")

        with st.container(border=True):
            st.markdown(f"**{source}** `#{rid}`")
            st.caption(snippet)
            with st.expander("Full content"):
                st.text(content[:3000])


def _render_docs_section(api: ElmerAPI) -> None:
    """Show documents from the knowledge base as a browsable list."""
    st.divider()
    st.subheader("Ingested Documents")

    sources = api.knowledge_sources()
    doc_sources = [s for s in sources if s.get("source") != "obsidian"]

    if not doc_sources:
        st.info("No documents ingested yet.")
        return

    for s in doc_sources:
        name = s.get("source", "?")
        count = s.get("doc_count", 0)
        updated = (s.get("latest_update") or "")[:16]
        st.caption(f"**{name}**: {count} chunks (updated {updated})")
