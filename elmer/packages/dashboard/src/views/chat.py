"""Chat with Elmer page — RAG-powered conversation interface."""

import streamlit as st

from api_client import ElmerAPI


def render() -> None:
    st.header("Chat with Elmer")

    api = ElmerAPI()

    # -- Initialize session state ---------------------------------------------

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_conversation_id" not in st.session_state:
        st.session_state.chat_conversation_id = None
    if "chat_model" not in st.session_state:
        st.session_state.chat_model = "llama3.1:8b"
    if "chat_web_search" not in st.session_state:
        st.session_state.chat_web_search = "Auto"

    # -- Sidebar controls (model + web search + history) ----------------------

    with st.sidebar:
        st.divider()
        st.markdown("### Chat Settings")

        # Model selector.
        models_data = api.get_llm_models()
        model_names = [m.get("name", "") for m in models_data] if models_data else []
        if not model_names:
            model_names = ["llama3.1:8b"]

        current = st.session_state.chat_model
        if current not in model_names:
            model_names.insert(0, current)

        selected_model = st.selectbox(
            "Model",
            model_names,
            index=model_names.index(current),
        )
        st.session_state.chat_model = selected_model

        # Web search toggle.
        search_options = ["Auto", "On", "Off"]
        current_search = st.session_state.chat_web_search
        if current_search not in search_options:
            current_search = "Auto"

        selected_search = st.radio(
            "\U0001f310 Web Search",
            search_options,
            index=search_options.index(current_search),
            horizontal=True,
        )
        st.session_state.chat_web_search = selected_search

        # New conversation button.
        if st.button("New Conversation", use_container_width=True):
            st.session_state.chat_messages = []
            st.session_state.chat_conversation_id = None
            st.rerun()

        # Conversation history.
        st.markdown("### History")
        conversations = api.list_conversations(limit=10)

        if conversations:
            for convo in conversations:
                cid = convo.get("id")
                msg_count = convo.get("message_count", 0)
                is_current = cid == st.session_state.chat_conversation_id

                label = f"{'> ' if is_current else ''}#{cid} ({msg_count} msgs)"
                if st.button(
                    label, key=f"convo_{cid}",
                    use_container_width=True,
                    type="primary" if is_current else "secondary",
                ):
                    _load_conversation(api, cid)
                    st.rerun()
        else:
            st.caption("No conversations yet.")

    # -- Chat display ---------------------------------------------------------

    # Display existing messages.
    for msg in st.session_state.chat_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        sources = msg.get("sources", [])
        web_searched = msg.get("web_search_performed", False)
        web_sources = msg.get("web_sources", [])

        with st.chat_message(role):
            # Show web search indicator on messages that used it.
            if web_searched and role == "assistant":
                st.caption("\U0001f310 Used web search")

            st.markdown(content)

            if sources:
                source_names = _extract_source_names(sources)
                if source_names:
                    st.caption(
                        "Sources: " + ", ".join(source_names)
                    )

            # Show web sources in collapsible section.
            if web_sources:
                with st.expander("\U0001f310 Web Sources"):
                    for ws in web_sources:
                        title = ws.get("title", "")
                        url = ws.get("url", "")
                        snippet = ws.get("snippet", "")
                        st.markdown(f"**{title}**")
                        if url:
                            st.markdown(f"[{url}]({url})")
                        if snippet:
                            st.caption(snippet)
                        st.divider()

    # -- Chat input -----------------------------------------------------------

    prompt = st.chat_input("Ask Elmer anything...")

    if prompt:
        # Add user message to display.
        st.session_state.chat_messages.append({
            "role": "user", "content": prompt,
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        # Map search toggle to API parameter.
        search_mode_map = {"Auto": "auto", "On": "force", "Off": "off"}
        web_search = search_mode_map.get(
            st.session_state.chat_web_search, "auto",
        )

        # Send to API.
        with st.chat_message("assistant"):
            spinner_text = (
                "\U0001f50d Searching the web..."
                if web_search == "force"
                else "Thinking..."
            )
            with st.spinner(spinner_text):
                result = api.chat(
                    message=prompt,
                    conversation_id=st.session_state.chat_conversation_id,
                    model=st.session_state.chat_model,
                    web_search=web_search,
                )

            if result is None:
                response_text = (
                    "Sorry, I couldn't connect to the chat service. "
                    "Is Elmer Core running?"
                )
                st.markdown(response_text)
                st.session_state.chat_messages.append({
                    "role": "assistant", "content": response_text,
                })
            else:
                response_text = result.get("response", "No response.")
                sources = result.get("sources_used", [])
                new_cid = result.get("conversation_id")
                error = result.get("error")
                web_searched = result.get("web_search_performed", False)
                web_sources = result.get("web_sources", [])

                # Update conversation ID.
                if new_cid is not None:
                    st.session_state.chat_conversation_id = new_cid

                # Web search indicator.
                if web_searched:
                    st.caption("\U0001f310 Used web search")

                # Display response.
                st.markdown(response_text)

                # Show knowledge sources.
                source_names = _extract_source_names(sources)
                if source_names:
                    st.caption(
                        "Sources: " + ", ".join(source_names)
                    )

                if sources:
                    with st.expander("Source details"):
                        for s in sources:
                            path = s.get("source_path") or s.get("source", "?")
                            score = s.get("score", 0)
                            snippet = s.get("snippet", "")
                            st.markdown(f"**{path}** ({score:.0%})")
                            if snippet:
                                st.caption(snippet)

                # Show web sources.
                if web_sources:
                    with st.expander("\U0001f310 Web Sources"):
                        for ws in web_sources:
                            title = ws.get("title", "")
                            url = ws.get("url", "")
                            snippet = ws.get("snippet", "")
                            st.markdown(f"**{title}**")
                            if url:
                                st.markdown(f"[{url}]({url})")
                            if snippet:
                                st.caption(snippet)
                            st.divider()

                if error:
                    st.warning(f"Note: {error}")

                # Store in session.
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "sources": sources,
                    "web_search_performed": web_searched,
                    "web_sources": web_sources,
                })


def _load_conversation(api: ElmerAPI, cid: int) -> None:
    """Load a conversation from the API into session state."""
    data = api.get_conversation(cid)
    if data is None:
        return

    st.session_state.chat_conversation_id = cid
    st.session_state.chat_messages = []

    messages = data.get("messages", [])
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        st.session_state.chat_messages.append({
            "role": role,
            "content": content,
            "sources": msg.get("context_used", []),
        })


def _extract_source_names(sources: list[dict]) -> list[str]:
    """Extract unique short filenames from source citations."""
    names = []
    for s in sources:
        path = s.get("source_path") or s.get("source") or ""
        name = path.rsplit("/", 1)[-1].split("#")[0] if "/" in path else path.split("#")[0]
        if name and name not in names:
            names.append(name)
    return names[:5]
