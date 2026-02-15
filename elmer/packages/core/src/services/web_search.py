"""Web search service — DuckDuckGo search with caching and rate limiting."""

import asyncio
import functools
import logging
import re
import time
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("elmer.web_search")

_FETCH_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_USER_AGENT = "Mozilla/5.0 (compatible; Elmer/1.0)"


@dataclass
class WebSearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    body: str = ""


class WebSearchService:
    """DuckDuckGo web search with rate limiting and caching."""

    _CACHE_TTL = 900.0  # 15 minutes
    _RATE_LIMIT = 2.0  # seconds between DDG API calls

    def __init__(self) -> None:
        self._cache: dict[str, tuple[list[WebSearchResult], float]] = {}
        self._last_search_time: float = 0.0
        self._rate_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self, query: str, max_results: int = 5,
    ) -> list[WebSearchResult]:
        """Text search via DuckDuckGo."""
        return await self._cached_search(query, "text", max_results)

    async def search_news(
        self, query: str, max_results: int = 5,
    ) -> list[WebSearchResult]:
        """News search via DuckDuckGo."""
        return await self._cached_search(query, "news", max_results)

    async def fetch_page(self, url: str, max_chars: int = 8000) -> str:
        """Fetch a web page and extract readable text content."""
        try:
            async with httpx.AsyncClient(
                timeout=_FETCH_TIMEOUT, follow_redirects=True,
            ) as client:
                resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return ""
                html = resp.text[:200_000]  # cap raw HTML read
        except Exception as exc:
            logger.debug("fetch_page failed for %s: %s", url, exc)
            return ""

        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            # Collapse multiple blank lines.
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text[:max_chars]
        except Exception as exc:
            logger.debug("HTML parse failed for %s: %s", url, exc)
            return ""

    async def search_and_fetch(
        self, query: str, max_results: int = 3,
    ) -> list[WebSearchResult]:
        """Search then fetch page content for richer context."""
        results = await self.search(query, max_results=max_results)
        if not results:
            return results

        async def _fetch_body(result: WebSearchResult) -> None:
            body = await self.fetch_page(result.url)
            if body:
                result.body = body

        await asyncio.gather(
            *[_fetch_body(r) for r in results],
            return_exceptions=True,
        )
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _cached_search(
        self, query: str, search_type: str, max_results: int,
    ) -> list[WebSearchResult]:
        """Check cache, then run search with rate limiting."""
        self._prune_cache()

        key = self._cache_key(query, search_type)
        cached = self._cache.get(key)
        if cached is not None:
            results, _ = cached
            logger.debug("Cache hit for %s:%s (%d results)", search_type, query, len(results))
            return results[:max_results]

        await self._rate_limit()

        try:
            loop = asyncio.get_running_loop()
            if search_type == "news":
                raw = await loop.run_in_executor(
                    None, functools.partial(self._sync_news, query, max_results),
                )
            else:
                raw = await loop.run_in_executor(
                    None, functools.partial(self._sync_search, query, max_results),
                )
        except Exception as exc:
            logger.warning("DuckDuckGo %s search failed: %s", search_type, exc)
            return []

        results = self._parse_results(raw, search_type)
        self._cache[key] = (results, time.monotonic())
        logger.info("Web search (%s) for '%s': %d results", search_type, query, len(results))
        return results[:max_results]

    @staticmethod
    def _sync_search(query: str, max_results: int) -> list[dict]:
        """Synchronous DuckDuckGo text search (runs in executor)."""
        from ddgs import DDGS

        ddgs = DDGS()
        return list(ddgs.text(query, max_results=max_results))

    @staticmethod
    def _sync_news(query: str, max_results: int) -> list[dict]:
        """Synchronous DuckDuckGo news search (runs in executor)."""
        from ddgs import DDGS

        ddgs = DDGS()
        return list(ddgs.news(query, max_results=max_results))

    @staticmethod
    def _parse_results(
        raw: list[dict], search_type: str,
    ) -> list[WebSearchResult]:
        """Convert raw DDG results to WebSearchResult list."""
        results: list[WebSearchResult] = []
        for item in raw:
            if search_type == "news":
                results.append(WebSearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("body", ""),
                ))
            else:
                results.append(WebSearchResult(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=item.get("body", ""),
                ))
        return results

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between DDG API calls."""
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_search_time
            if elapsed < self._RATE_LIMIT:
                await asyncio.sleep(self._RATE_LIMIT - elapsed)
            self._last_search_time = time.monotonic()

    def _prune_cache(self) -> None:
        """Remove expired cache entries."""
        now = time.monotonic()
        expired = [
            k for k, (_, ts) in self._cache.items()
            if now - ts > self._CACHE_TTL
        ]
        for k in expired:
            del self._cache[k]

    @staticmethod
    def _cache_key(query: str, search_type: str) -> str:
        return f"{search_type}:{query.strip().lower()}"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: WebSearchService | None = None


def get_service() -> WebSearchService:
    """Return the shared WebSearchService instance."""
    global _service
    if _service is None:
        _service = WebSearchService()
    return _service
