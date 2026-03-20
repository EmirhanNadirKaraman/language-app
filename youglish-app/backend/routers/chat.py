import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    ChatMessageRead,
    ChatSendMessage,
    ChatSessionCreate,
    ChatSessionRead,
    GuidedSessionCreate,
    GuidedSessionRead,
    SendMessageResponse,
)
from ..services import chat_service, guided_chat_service, llm_service, usage_events_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await chat_service.create_session(pool, str(current_user["user_id"]), body.session_type)


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await chat_service.list_sessions(pool, str(current_user["user_id"]))


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_session(
    session_id: str,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await _require_session(pool, session_id, current_user)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def get_messages(
    session_id: str,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    await _require_session(pool, session_id, current_user)
    return await chat_service.get_messages(pool, session_id)


@router.post(
    "/guided-sessions",
    response_model=GuidedSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_guided_session(
    body: GuidedSessionCreate,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])

    target = await guided_chat_service.get_next_target(pool, user_id, body.language)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No vocabulary available for this language. Add some words first.",
        )

    session = await chat_service.create_session(
        pool, user_id, "guided",
        target_item_id=target["item_id"],
        target_item_type=target["item_type"],
    )

    opening_text = await llm_service.guided_open(target["word"], body.language, pool=pool)
    opening_msg = await chat_service.save_message(
        pool, session["session_id"], "assistant", opening_text
    )

    return GuidedSessionRead(
        session_id=session["session_id"],
        session_type="guided",
        target_item_id=target["item_id"],
        target_item_type=target["item_type"],
        target_word=target["word"],
        started_at=session["started_at"],
        opening_message=opening_msg,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    session_id: str,
    body: ChatSendMessage,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    session = await _require_session(pool, session_id, current_user)

    # Fetch recent history for context (last 20 turns)
    history = await chat_service.get_messages(pool, session_id)
    history = history[-20:]

    if session["session_type"] == "guided":
        return await _handle_guided_message(pool, session, history, body.content, current_user)

    # --- Free chat ---
    user_id = str(current_user["user_id"])
    user_msg = await chat_service.save_message(pool, session_id, "user", body.content)

    result = await llm_service.evaluate_and_reply(
        body.content,
        [{"role": m["role"], "content": m["content"]} for m in history],
    )

    assistant_msg = await chat_service.save_message(
        pool, session_id, "assistant", result["reply"],
        language_detected=result["language_detected"],
        corrections=result["corrections"],
        word_matches=result["word_matches"],
    )

    # Record a 'used' event for each matched word (fire-and-forget)
    for match in result.get("word_matches", []):
        if isinstance(match, dict) and "item_id" in match:
            asyncio.create_task(
                usage_events_service.record_event(
                    pool, user_id,
                    match["item_id"],
                    match.get("item_type", "word"),
                    context="free_chat",
                    outcome="used",
                )
            )

    return SendMessageResponse(user_message=user_msg, assistant_message=assistant_msg)


async def _handle_guided_message(
    pool, session: dict, history: list, content: str, current_user: dict
) -> SendMessageResponse:
    """Evaluate a guided-mode turn: rich eval, SRS update, then save messages."""
    session_id = session["session_id"]
    user_id    = str(current_user["user_id"])

    # Look up target word + language from word_table
    target_row = await pool.fetchrow(
        "SELECT word, language FROM word_table WHERE word_id = $1",
        session["target_item_id"],
    )
    if target_row is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Target word no longer in vocabulary.")

    target_word = target_row["word"]
    language    = target_row["language"]

    # Evaluate user turn (structured eval + reply in one LLM call)
    eval_result = await llm_service.guided_evaluate(
        content,
        [{"role": m["role"], "content": m["content"]} for m in history],
        target_word,
        language,
    )

    # Update passive/active progression for every guided turn
    await guided_chat_service.update_progress(
        pool, user_id,
        session["target_item_id"],
        session["target_item_type"],
        target_used=eval_result["target_used"],
        target_counted=eval_result["target_counted"],
    )

    # Record usage event (fire-and-forget)
    _guided_outcome = "correct" if eval_result["target_counted"] else (
        "used" if eval_result["target_used"] else "seen"
    )
    asyncio.create_task(
        usage_events_service.record_event(
            pool, user_id,
            session["target_item_id"],
            session["target_item_type"],
            context="guided_chat",
            outcome=_guided_outcome,
        )
    )

    # Persist user message with structured evaluation
    evaluation_snapshot = {
        "target_used":    eval_result["target_used"],
        "target_counted": eval_result["target_counted"],
        "feedback_short": eval_result["feedback_short"],
        "naturalness":    eval_result["naturalness"],
    }
    user_msg = await chat_service.save_message(
        pool, session_id, "user", content,
        evaluation=evaluation_snapshot,
    )

    # Persist assistant reply with corrections
    assistant_msg = await chat_service.save_message(
        pool, session_id, "assistant", eval_result["reply"],
        language_detected=eval_result["language_detected"],
        corrections=eval_result["corrections"],
        word_matches=[],
    )

    return SendMessageResponse(user_message=user_msg, assistant_message=assistant_msg)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _require_session(pool, session_id: str, current_user: dict) -> dict:
    """Fetch session and verify it belongs to the current user. Raises 404 otherwise."""
    session = await chat_service.get_session(pool, session_id)
    if not session or session["user_id"] != str(current_user["user_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session
