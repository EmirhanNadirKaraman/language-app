from fastapi import APIRouter, Depends, Query
from ..database import get_pool
from ..models.schemas import SearchResponse, SuggestionResult, VideoSentence
from ..services import search_service

router = APIRouter()


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
