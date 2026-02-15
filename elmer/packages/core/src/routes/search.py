"""Web search endpoints — standalone DuckDuckGo search for Elmer."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.web_search import get_service

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger("elmer.search")


# --- Request / Response models ---


class WebSearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=10)
    search_type: str = "text"  # "text" | "news"


class WebSearchResultModel(BaseModel):
    title: str
    url: str
    snippet: str
    body: str = ""


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResultModel]
    result_count: int


class FetchPageRequest(BaseModel):
    url: str
    max_chars: int = Field(default=8000, ge=100, le=50000)


class FetchPageResponse(BaseModel):
    url: str
    text: str
    char_count: int


# --- Endpoints ---


@router.post("/web", response_model=WebSearchResponse)
async def web_search(request: WebSearchRequest):
    """Search the web via DuckDuckGo."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Empty query")

    if request.search_type not in ("text", "news"):
        raise HTTPException(status_code=400, detail="search_type must be 'text' or 'news'")

    svc = get_service()
    if request.search_type == "news":
        results = await svc.search_news(request.query, max_results=request.max_results)
    else:
        results = await svc.search(request.query, max_results=request.max_results)

    return WebSearchResponse(
        query=request.query,
        results=[
            WebSearchResultModel(
                title=r.title, url=r.url, snippet=r.snippet, body=r.body,
            )
            for r in results
        ],
        result_count=len(results),
    )


@router.post("/fetch", response_model=FetchPageResponse)
async def fetch_page(request: FetchPageRequest):
    """Fetch a web page and extract readable text content."""
    if not request.url.strip():
        raise HTTPException(status_code=400, detail="Empty URL")

    svc = get_service()
    text = await svc.fetch_page(request.url, max_chars=request.max_chars)

    return FetchPageResponse(
        url=request.url,
        text=text,
        char_count=len(text),
    )
