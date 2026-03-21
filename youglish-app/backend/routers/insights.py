from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    GenerateExamplesRequest,
    GenerateExamplesResponse,
    InsightCardsResponse,
    PrepViewData,
)
from ..services import insights_service, llm_service

router = APIRouter(prefix="/insights", tags=["insights"])

_VALID_ITEM_TYPES = {"word", "phrase"}


@router.get("/cards", response_model=InsightCardsResponse)
async def get_cards(
    language: str = Query(...),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Return two insight cards for the home-screen Insights section.

    Card 1 (frequent_unknowns): items the user keeps encountering but hasn't learned.
    Card 2 (recent_mistakes):   items the user got wrong most recently.

    Each card includes up to 3 items ranked by combined priority score.
    Refreshes on every request — no server-side TTL cache (responses are fast).
    """
    return await insights_service.get_insight_cards(
        pool, str(current_user["user_id"]), language
    )


@router.get("/prep", response_model=PrepViewData)
async def get_prep(
    item_id: int = Query(...),
    item_type: str = Query(...),
    language: str = Query(...),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Return prep view data for a single vocabulary item.

    Always returns translation + grammar explanation (loaded from LLM cache
    or generated on first visit).  Examples/templates are returned only if
    already cached; otherwise has_examples=False signals the frontend to show
    a "Generate examples" button.
    """
    if item_type not in _VALID_ITEM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"item_type must be one of {sorted(_VALID_ITEM_TYPES)}",
        )
    result = await insights_service.get_prep_data(
        pool, str(current_user["user_id"]), item_id, item_type, language
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.post("/prep/generate-examples", response_model=GenerateExamplesResponse)
async def generate_examples(
    body: GenerateExamplesRequest,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate and cache example sentence + templates for an item.

    Called only when the user clicks "Generate examples" in the prep view.
    Subsequent calls for the same item hit the LLM cache instantly.
    """
    if body.item_type not in _VALID_ITEM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"item_type must be one of {sorted(_VALID_ITEM_TYPES)}",
        )

    display_text = await insights_service.get_item_display_text(
        pool, str(current_user["user_id"]), body.item_id, body.item_type, body.language
    )
    if display_text is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return await llm_service.prep_generate_examples(
        display_text, body.item_type, body.language, pool=pool
    )
