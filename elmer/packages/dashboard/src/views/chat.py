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

    # -- Sidebar controls (model + history) -----------------------------------

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
                updated = (convo.get("updated_at") or "")[:16]
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

        with st.chat_message(role):
            st.markdown(content)
            if sources:
                source_names = _extract_source_names(sources)
                if source_names:
                    st.caption(
                        "Sources: " + ", ".join(source_names)
                    )

    # -- Chat input -----------------------------------------------------------

    prompt = st.chat_input("Ask Elmer anything...")

    if prompt:
        # Add user message to display.
        st.session_state.chat_messages.append({
            "role": "user", "content": prompt,
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        # Send to API.
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = api.chat(
                    message=prompt,
                    conversation_id=st.session_state.chat_conversation_id,
                    model=st.session_state.chat_model,
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

                # Update conversation ID.
                if new_cid is not None:
                    st.session_state.chat_conversation_id = new_cid

                # Display response.
                st.markdown(response_text)

                # Show sources.
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

                if error:
                    st.warning(f"Note: {error}")

                # Store in session.
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "sources": sources,
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
