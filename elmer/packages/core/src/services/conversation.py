"""Conversation manager — CRUD for chat conversations in elmer.conversations."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import db

logger = logging.getLogger("elmer.conversation")

# Max messages to keep in the rolling window sent to the LLM.
DEFAULT_HISTORY_LIMIT = 10


async def create_conversation(channel: str = "api", agent_id: int | None = None) -> int:
    """Create a new conversation and return its ID."""
    row = await db.fetch_one(
        """
        INSERT INTO elmer.conversations (agent_id, channel, messages, updated_at)
        VALUES ($1, $2, '[]'::jsonb, now())
        RETURNING id
        """,
        agent_id, channel,
    )
    cid = row["id"]
    logger.info("Created conversation %d (channel=%s)", cid, channel)
    return cid


async def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    """Return full conversation record or None."""
    row = await db.fetch_one(
        "SELECT * FROM elmer.conversations WHERE id = $1", conversation_id,
    )
    if row is None:
        return None
    return _row_to_dict(row)


async def add_message(
    conversation_id: int,
    role: str,
    content: str,
    context_used: list[dict[str, Any]] | None = None,
) -> None:
    """Append a message to a conversation's JSONB messages array."""
    msg = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if context_used:
        msg["context_used"] = context_used

    await db.execute(
        """
        UPDATE elmer.conversations
        SET messages = messages || $2::jsonb,
            updated_at = now()
        WHERE id = $1
        """,
        conversation_id, json.dumps([msg]),
    )


async def get_history(
    conversation_id: int,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Return the last N messages from a conversation."""
    row = await db.fetch_one(
        "SELECT messages FROM elmer.conversations WHERE id = $1",
        conversation_id,
    )
    if row is None:
        return []

    messages = _parse_messages(row["messages"])
    # Return last `limit` messages.
    return messages[-limit:] if limit else messages


async def list_conversations(
    channel: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List conversations, optionally filtered by channel."""
    if channel:
        rows = await db.fetch_all(
            """
            SELECT id, agent_id, channel, created_at, updated_at,
                   jsonb_array_length(messages) AS message_count
            FROM elmer.conversations
            WHERE channel = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            channel, limit,
        )
    else:
        rows = await db.fetch_all(
            """
            SELECT id, agent_id, channel, created_at, updated_at,
                   jsonb_array_length(messages) AS message_count
            FROM elmer.conversations
            ORDER BY updated_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [
        {
            "id": r["id"],
            "agent_id": r["agent_id"],
            "channel": r["channel"],
            "message_count": r["message_count"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


async def delete_conversation(conversation_id: int) -> bool:
    """Delete a conversation. Returns True if it existed."""
    result = await db.execute(
        "DELETE FROM elmer.conversations WHERE id = $1", conversation_id,
    )
    count = int(result.split()[-1])
    return count > 0


async def clear_history(conversation_id: int) -> bool:
    """Clear messages but keep the conversation record."""
    result = await db.execute(
        """
        UPDATE elmer.conversations
        SET messages = '[]'::jsonb, updated_at = now()
        WHERE id = $1
        """,
        conversation_id,
    )
    return "UPDATE 1" in result


# --- Internal ---

def _parse_messages(raw: Any) -> list[dict[str, Any]]:
    """Parse the messages JSONB column into a Python list."""
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, list):
        return raw
    return []


def _row_to_dict(row) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict with parsed messages."""
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "channel": row["channel"],
        "messages": _parse_messages(row["messages"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
