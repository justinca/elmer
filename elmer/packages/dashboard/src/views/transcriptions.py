"""Transcriptions page — upload, browse, and search transcriptions."""

import streamlit as st

from api_client import ElmerAPI

MIME_MAP = {
    "wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4",
    "flac": "audio/flac", "ogg": "audio/ogg", "webm": "audio/webm",
}


def _format_duration(seconds) -> str:
    if seconds is None:
        return "-"
    seconds = float(seconds)
    m = int(seconds) // 60
    s = int(seconds) % 60
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def render() -> None:
    st.header("Transcriptions")

    api = ElmerAPI()

    # -- Upload section -------------------------------------------------------

    st.subheader("Upload Audio")
    uploaded = st.file_uploader(
        "Drag and drop an audio file",
        type=["wav", "mp3", "m4a", "flac", "ogg", "webm"],
        label_visibility="collapsed",
    )

    if uploaded is not None:
        suffix = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else "wav"
        mime = MIME_MAP.get(suffix, "application/octet-stream")

        if st.button("Transcribe", type="primary"):
            file_bytes = uploaded.read()
            if not file_bytes:
                st.error("File appears empty (0 bytes). Try re-uploading.")
            else:
                st.caption(f"Uploading {len(file_bytes) / 1_048_576:.1f} MB...")
                with st.spinner(f"Transcribing {uploaded.name}... This may take a few minutes."):
                    result = api.upload_transcription(
                        uploaded.name, file_bytes, mime,
                    )

                if result is None:
                    st.error("Transcription failed. Check dashboard container logs for details.")
                elif result.get("transcript"):
                    st.success("Transcription complete!")
                    duration = _format_duration(result.get("duration_seconds"))
                    lang = result.get("language") or ""
                    st.caption(f"Duration: {duration} \u00b7 Language: {lang}")
                    st.text_area(
                        "Transcript", result["transcript"],
                        height=200, disabled=True,
                    )
                else:
                    st.warning("No speech detected in the audio.")

    st.divider()

    # -- Status indicators ----------------------------------------------------

    col_worker, col_count = st.columns(2)

    with col_worker:
        nodes = api.get_nodes()
        worker = next(
            (n for n in nodes if n.get("node_type") == "worker"), None,
        )
        if worker and worker.get("status") == "online":
            st.success("Worker: Online (Whisper ready)")
        elif worker:
            st.warning(f"Worker: {worker.get('status', 'unknown')}")
        else:
            st.error("Worker: Not registered")

    with col_count:
        transcriptions = api.get_transcriptions(limit=200)
        st.metric("Total Transcriptions", len(transcriptions))

    st.divider()

    # -- Search ---------------------------------------------------------------

    st.subheader("Search Transcriptions")
    search_query = st.text_input(
        "Search",
        placeholder="Search within transcripts...",
        key="tsearch",
        label_visibility="collapsed",
    )

    if search_query:
        with st.spinner("Searching..."):
            results = api.search_transcriptions(search_query, limit=10)

        if not results:
            st.info(f'No results for "{search_query}".')
        else:
            for r in results:
                score = r.get("score", 0)
                audio = r.get("audio_file", "?")
                snippet = (r.get("transcript") or "")[:200].replace("\n", " ")
                tid = r.get("id")

                with st.container(border=True):
                    cols = st.columns([4, 1])
                    with cols[0]:
                        st.markdown(f"**{audio}** `#{tid}`")
                        st.caption(snippet)
                    with cols[1]:
                        st.metric("Score", f"{score:.0%}")

        st.divider()

    # -- Transcription list ---------------------------------------------------

    st.subheader("Recent Transcriptions")

    if not transcriptions:
        st.info("No transcriptions yet. Upload an audio file above.")
        return

    for t in transcriptions[:20]:
        tid = t.get("id")
        audio = t.get("audio_file", "?")
        duration = _format_duration(t.get("duration_seconds"))
        lang = t.get("language") or ""
        model = t.get("model") or ""
        created = (t.get("created_at") or "")[:16]
        snippet = (t.get("transcript") or "")[:100].replace("\n", " ")

        with st.container(border=True):
            cols = st.columns([4, 1, 1])
            with cols[0]:
                st.markdown(f"**{audio}**")
                st.caption(f"{snippet}...")
            with cols[1]:
                st.caption(f"Duration: {duration}")
                if lang:
                    st.caption(f"Language: {lang}")
            with cols[2]:
                st.caption(created)
                if model:
                    st.caption(model)

            with st.expander("Full transcript"):
                detail = api.get_transcription(tid)
                if detail:
                    transcript_text = detail.get("transcript", "")
                    st.text_area(
                        "Transcript text",
                        transcript_text,
                        height=200, disabled=True,
                        key=f"transcript_{tid}",
                        label_visibility="collapsed",
                    )

                    segments = detail.get("segments", [])
                    if segments:
                        st.caption(f"{len(segments)} segments")
                        for seg in segments[:50]:
                            start = seg.get("start", 0)
                            end = seg.get("end", 0)
                            text = seg.get("text", "")
                            st.caption(
                                f"[{_format_duration(start)} - "
                                f"{_format_duration(end)}] {text}"
                            )
                else:
                    st.warning("Could not load transcript details.")
