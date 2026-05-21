"""
Search / corpus endpoints.

Audit #7 / 2026-05-21: these endpoints expose the scraped video + sentence
corpus, suggestions, and word-form expansions. They are now authenticated
— logged-out users see nothing about the corpus. Truly public routes
(auth/register, auth/login, /privacy static, client-error reporter) are
intentionally not gated and live elsewhere.

The `/api/languages` and `/api/categories` endpoints leak less, but they
also exist purely to feed authenticated UIs (SettingsPanel, channel-prefs).
They're gated too so the policy is uniform: "no token, no corpus".
"""
from fastapi import APIRouter, Depends, Query
from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import SearchResponse, SuggestionResult, VideoSentence
from ..services import search_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    language: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    pool=Depends(get_pool),
):
    results, total = await search_service.search(pool, q, language, limit, offset)
    return SearchResponse(query=q, results=results, total=total)


@router.get("/suggest", response_model=list[SuggestionResult])
async def suggest(
    q: str = Query(..., min_length=1),
    language: str | None = Query(default=None),
    pool=Depends(get_pool),
):
    return await search_service.suggest(pool, q, language)


@router.get("/video-sentences", response_model=list[VideoSentence])
async def video_sentences(
    video_id: str = Query(...),
    pool=Depends(get_pool),
):
    return await search_service.get_video_sentences(pool, video_id)


@router.get("/word-forms", response_model=list[str])
async def word_forms(
    q: str = Query(..., min_length=1),
    pool=Depends(get_pool),
):
    terms = q.strip().split()
    return await search_service.get_word_forms(pool, terms)


@router.get("/languages", response_model=list[str])
async def languages(pool=Depends(get_pool)):
    return await search_service.get_languages(pool)


@router.get("/categories", response_model=list[str])
async def categories(pool=Depends(get_pool)):
    return await search_service.get_categories(pool)
