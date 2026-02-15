"""Search decision engine — decides whether a chat message needs web search."""

import logging
from dataclasses import dataclass

import httpx

from ..config import settings

logger = logging.getLogger("elmer.search_decision")

_CLASSIFIER_SYSTEM_PROMPT = """\
You are a search classifier. Given a user question, decide if it needs \
a web search for current/real-time information.

Respond with ONLY one of:
YES:<search query>
NO

Say YES only for: current events, today's weather/conditions, live data, \
recent news, prices, scores, schedules, new product releases, or specific \
facts you likely don't know.

Say NO for: general knowledge, coding help, personal questions, greetings, \
opinions, math, how-to, amateur radio theory, antenna design, the user's \
own systems/equipment, or anything answerable from memory or local notes.

Be conservative — when in doubt, say NO.\
"""

_CLASSIFIER_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

_TRIVIAL_PREFIXES = (
    "hi", "hello", "hey", "thanks", "thank you", "ok", "bye",
    "good morning", "good afternoon", "good evening", "good night",
    "what's up", "how are you", "who are you", "what are you",
)


@dataclass
class SearchDecision:
    """Result of the search decision engine."""

    should_search: bool
    search_query: str = ""
    reason: str = ""


class SearchDecisionEngine:
    """Determines whether a user message warrants web search."""

    async def decide(
        self,
        message: str,
        mode: str = "auto",
        top_local_score: float = 0.0,
    ) -> SearchDecision:
        """Decide whether to web-search for this message.

        Args:
            message: The user's chat message.
            mode: "auto" (LLM classifier), "force", or "off".
            top_local_score: Best similarity score from local knowledge search.
        """
        if mode == "off":
            return SearchDecision(should_search=False, reason="off")

        if mode == "force":
            query = _extract_search_query(message)
            return SearchDecision(
                should_search=True, search_query=query, reason="forced",
            )

        # --- AUTO mode ---

        # Fast-path: high-confidence local results make search unnecessary.
        if top_local_score >= 0.85:
            return SearchDecision(
                should_search=False,
                reason=f"high_local_confidence ({top_local_score:.2f})",
            )

        # Fast-path: trivial/conversational messages.
        if _is_trivial(message):
            return SearchDecision(should_search=False, reason="heuristic_skip")

        # LLM classifier.
        try:
            return await self._classify(message, top_local_score)
        except Exception as exc:
            logger.warning("Search classifier failed (%s), defaulting to no search", exc)
            return SearchDecision(should_search=False, reason="classifier_error")

    async def _classify(
        self, message: str, top_local_score: float,
    ) -> SearchDecision:
        """Call Ollama with the classifier prompt."""
        user_content = message
        if top_local_score < 0.6:
            user_content = (
                "(Note: local knowledge has no strong match for this)\n"
                + message
            )

        messages = [
            {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        payload = {
            "model": "llama3.1:8b",
            "messages": messages,
            "stream": False,
            "options": {"num_predict": 50},
        }

        response_text = await _call_ollama_short(payload)
        response_text = response_text.strip()

        if response_text.upper().startswith("YES:"):
            query = response_text[4:].strip()
            return SearchDecision(
                should_search=True,
                search_query=query or message,
                reason="classifier",
            )
        if response_text.upper().startswith("YES"):
            return SearchDecision(
                should_search=True, search_query=message, reason="classifier",
            )

        return SearchDecision(should_search=False, reason="classifier")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_trivial(message: str) -> bool:
    """Heuristic check for trivial/conversational messages."""
    msg = message.strip().lower()
    if len(msg) < 10:
        return True
    return any(msg.startswith(p) for p in _TRIVIAL_PREFIXES)


def _extract_search_query(message: str) -> str:
    """Strip /websearch prefix or [search] tag from message."""
    msg = message.strip()
    for prefix in ("/websearch ", "/websearch"):
        if msg.lower().startswith(prefix):
            msg = msg[len(prefix):].strip()
    msg = msg.replace("[search]", "").strip()
    return msg or message.strip()


async def _call_ollama_short(payload: dict) -> str:
    """Quick Ollama call for the classifier (worker → direct fallback)."""
    # Try worker first.
    worker_url = f"{settings.worker_base_url}/llm/chat"
    try:
        async with httpx.AsyncClient(timeout=_CLASSIFIER_TIMEOUT) as client:
            resp = await client.post(worker_url, json=payload)
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            msg = data.get("message", {})
            if msg and msg.get("content"):
                return msg["content"]
    except (httpx.RequestError, RuntimeError) as exc:
        logger.debug("Classifier via worker failed (%s), trying Ollama direct", exc)

    # Fall back to direct Ollama.
    ollama_url = f"{settings.ollama_base_url}/api/chat"
    async with httpx.AsyncClient(timeout=_CLASSIFIER_TIMEOUT) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    msg = data.get("message", {})
    return msg.get("content", "")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: SearchDecisionEngine | None = None


def get_engine() -> SearchDecisionEngine:
    """Return the shared SearchDecisionEngine instance."""
    global _engine
    if _engine is None:
        _engine = SearchDecisionEngine()
    return _engine
