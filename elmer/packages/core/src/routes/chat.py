"""Chat endpoints — RAG-powered conversation with Elmer."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import conversation as convo
from ..services import rag_chat

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("elmer.chat")


# --- Request / Response models ---


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    model: str = "llama3.1:8b"
    web_search: str = "auto"  # "auto" | "force" | "off"


class SourceUsed(BaseModel):
    source: str
    source_path: str | None = None
    score: float = 0.0
    snippet: str = ""


class WebSource(BaseModel):
    title: str
    url: str
    snippet: str


class ChatResponseModel(BaseModel):
    response: str
    conversation_id: int
    model: str
    sources_used: list[SourceUsed] = Field(default_factory=list)
    error: str | None = None
    web_search_performed: bool = False
    web_search_query: str = ""
    web_sources: list[WebSource] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: int
    agent_id: int | None = None
    channel: str | None = None
    message_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ConversationDetail(BaseModel):
    id: int
    agent_id: int | None = None
    channel: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class ClearResponse(BaseModel):
    conversation_id: int
    cleared: bool


class DeleteResponse(BaseModel):
    conversation_id: int
    deleted: bool


# --- Endpoints ---


@router.post("", response_model=ChatResponseModel)
async def send_message(request: ChatRequest):
    """Send a message to Elmer and get a RAG-augmented response."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")

    if request.web_search not in ("auto", "force", "off"):
        raise HTTPException(status_code=400, detail="web_search must be 'auto', 'force', or 'off'")

    result = await rag_chat.chat(
        message=request.message,
        conversation_id=request.conversation_id,
        model=request.model,
        web_search=request.web_search,
    )

    return ChatResponseModel(
        response=result.response,
        conversation_id=result.conversation_id,
        model=result.model,
        sources_used=[
            SourceUsed(
                source=s.source,
                source_path=s.source_path,
                score=s.score,
                snippet=s.snippet,
            )
            for s in result.sources_used
        ],
        error=result.error,
        web_search_performed=result.web_search_performed,
        web_search_query=result.web_search_query,
        web_sources=[WebSource(**ws) for ws in result.web_sources],
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(channel: str | None = None, limit: int = 20):
    """List recent conversations."""
    rows = await convo.list_conversations(channel=channel, limit=limit)
    return [ConversationSummary(**r) for r in rows]


@router.get("/conversation/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: int):
    """Get full conversation with all messages."""
    record = await convo.get_conversation(conversation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(**record)


@router.delete("/conversation/{conversation_id}", response_model=DeleteResponse)
async def delete_conversation(conversation_id: int):
    """Delete a conversation."""
    deleted = await convo.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return DeleteResponse(conversation_id=conversation_id, deleted=True)


@router.post("/conversation/{conversation_id}/clear", response_model=ClearResponse)
async def clear_conversation(conversation_id: int):
    """Clear message history but keep the conversation record."""
    cleared = await convo.clear_history(conversation_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ClearResponse(conversation_id=conversation_id, cleared=True)
