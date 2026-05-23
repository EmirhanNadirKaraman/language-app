import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.deps import get_current_user, rate_limit_llm
from ..database import get_pool
from ..models.schemas import (
    ChatMessageRead,
    ChatSendMessage,
    ChatSessionCreate,
    ChatSessionRead,
    GuidedCompleteRequest,
    GuidedSessionCreate,
    GuidedSessionRead,
    GuidedSessionSummary,
    SendMessageResponse,
)
from ..services import chat_service, guided_chat_service, llm_service, progression_service, usage_events_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    # Stage 3: persist the requested target language so the LLM system
    # prompt + match_learning_words at message time honour the user's
    # actual target language instead of the pre-Stage-3 hardcoded 'de'.
    return await chat_service.create_session(
        pool, str(current_user["user_id"]), body.session_type,
        language=body.language,
    )


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
    dependencies=[Depends(rate_limit_llm)],
)
async def create_guided_session(
    body: GuidedSessionCreate,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])

    # Use caller-specified target (from prep view handoff) when provided
    target = None
    if body.target_item_id is not None and body.target_item_type is not None:
        target = await guided_chat_service.get_target_by_id(
            pool, body.target_item_id, body.target_item_type, body.language
        )

    if target is None:
        target = await guided_chat_service.get_next_target(pool, user_id, body.language)

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No vocabulary available for this language. Add some words first.",
        )

    session = await chat_service.create_session(
        pool, user_id, "guided",
        language=body.language,
        target_item_id=target["item_id"],
        target_item_type=target["item_type"],
    )

    # Generate opening + hints in parallel; hints failure is non-fatal
    opening_text, hints_raw = await asyncio.gather(
        llm_service.guided_open(target["word"], body.language, pool=pool),
        llm_service.guided_hints(target["word"], body.language, pool=pool),
        return_exceptions=True,
    )

    # If opening failed (an Exception), re-raise it; hints failure is silenced
    if isinstance(opening_text, BaseException):
        raise opening_text

    hints_data = None
    if not isinstance(hints_raw, BaseException):
        from ..models.schemas import GuidedHints
        hints_data = GuidedHints(**hints_raw)

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
        hints=hints_data,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_llm)],
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
    # Stage 3 (second-language plan): read the session's stored language
    # instead of hardcoding 'de'. Legacy rows (migration 031 added the
    # column nullable) fall back to "de" so pre-Stage-3 sessions keep
    # behaving identically.
    session_language = session.get("language") or "de"
    user_msg = await chat_service.save_message(pool, session_id, "user", body.content)

    result = await llm_service.evaluate_and_reply(
        body.content,
        [{"role": m["role"], "content": m["content"]} for m in history],
        session_language,
    )

    assistant_msg = await chat_service.save_message(
        pool, session_id, "assistant", result["reply"],
        language_detected=result["language_detected"],
        corrections=result["corrections"],
        word_matches=result["word_matches"],
    )

    # Server-side vocabulary matching. We ALWAYS scan the user's message for
    # target-language learning items the user is tracking — even when the LLM
    # labels the whole message "en". A learner who writes "Yesterday I bought
    # Brot" still produced the German learning word "Brot" and earns (passive)
    # credit for it; the old gate skipped matching entirely on an "en" label
    # and dropped that credit on the floor.
    #
    # `language_detected` now only decides whether the use ALSO earns active
    # production credit:
    #   == session_language     → free_chat_used_correctly (passive + active)
    #   else, but items matched → free_chat_mixed_lang     (passive only)
    #   else (nothing matched)  → no progression event
    #
    # Active credit is never granted for an "en" or "mixed" turn. Matching is
    # scoped to word_table/phrase_table in `session_language` AND the user's
    # own non-known items, so the only false-positive surface is a homograph
    # the user is actively learning (e.g. German "war"/"die" inside an English
    # sentence) — and that only ever yields passive credit.
    #
    # Cost note: match_learning_words runs spaCy phrase extraction, so it now
    # runs on every free-chat turn regardless of detected language (previously
    # skipped for pure-English turns). Free chat is one-message-at-a-time, so
    # the extra per-turn cost is acceptable.
    language_detected = result.get("language_detected", "en")
    matched = await chat_service.match_learning_words(
        pool, user_id, body.content, session_language,
    )
    if matched:
        target_language_turn = language_detected == session_language
        _event = "free_chat_used_correctly" if target_language_turn else "free_chat_mixed_lang"
        _analytics_outcome = "used" if target_language_turn else "seen"
        for match in matched:
            # Progression update — awaited; these are primary knowledge-state changes
            await progression_service.apply_progression(
                pool, user_id, match["item_id"], match["item_type"], _event,
            )
            # Analytics — fire-and-forget; logging failure must not fail the request
            asyncio.create_task(
                usage_events_service.record_event(
                    pool, user_id,
                    match["item_id"], match["item_type"],
                    context="free_chat",
                    outcome=_analytics_outcome,
                )
            )

    return SendMessageResponse(user_message=user_msg, assistant_message=assistant_msg)


async def _handle_guided_message(
    pool, session: dict, history: list, content: str, current_user: dict
) -> SendMessageResponse:
    """Evaluate a guided-mode turn: rich eval, SRS update, then save messages."""
    session_id = session["session_id"]
    user_id    = str(current_user["user_id"])

    target_word, language = await _fetch_target_word(pool, session)

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


@router.post(
    "/guided-sessions/{session_id}/complete",
    response_model=GuidedSessionSummary,
    dependencies=[Depends(rate_limit_llm)],
)
async def complete_guided_session(
    session_id: str,
    body: GuidedCompleteRequest,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Complete a guided session and return a result summary.

    Computes deterministic signals (target_used, sentence_quality, etc.) from the
    stored per-turn evaluation data, then calls the LLM once for concise feedback.
    No new DB state is written — all progression updates already happened per-turn.
    """
    session = await _require_session(pool, session_id, current_user)
    if session["session_type"] != "guided":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session is not a guided session.",
        )

    target_word, language = await _fetch_target_word(pool, session)
    messages = await chat_service.get_messages(pool, session_id)

    # --- Deterministic signals from stored per-turn evaluations ---
    user_messages = [m for m in messages if m["role"] == "user"]
    evaluations   = [m["evaluation"] for m in user_messages if m.get("evaluation")]

    target_used         = any(e.get("target_used")    for e in evaluations)
    target_counted      = any(e.get("target_counted") for e in evaluations)
    target_counted_count = sum(1 for e in evaluations if e.get("target_counted"))
    total_turns         = len(user_messages)

    naturalness_list = [e["naturalness"] for e in evaluations if e.get("naturalness")]
    sentence_quality = _compute_sentence_quality(naturalness_list)

    # Aggregate corrections from all messages (both user and assistant carry them)
    all_corrections: list[dict] = []
    for m in messages:
        if m.get("corrections"):
            all_corrections.extend(m["corrections"])

    # --- LLM feedback (one call) ---
    feedback = await llm_service.guided_summarize(
        target_word=target_word,
        language=language,
        target_used=target_used,
        target_counted=target_counted,
        sentence_quality=sentence_quality,
        all_corrections=all_corrections,
        total_turns=total_turns,
    )

    return GuidedSessionSummary(
        session_id=session_id,
        target_word=target_word,
        target_item_id=session["target_item_id"],
        target_item_type=session["target_item_type"],
        target_used=target_used,
        target_counted=target_counted,
        target_counted_count=target_counted_count,
        total_turns=total_turns,
        hint_level=body.hint_level,
        sentence_quality=sentence_quality,
        what_went_well=feedback["what_went_well"],
        what_to_improve=feedback["what_to_improve"],
        corrective_note=feedback["corrective_note"],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _require_session(pool, session_id: str, current_user: dict) -> dict:
    """Fetch session and verify it belongs to the current user. Raises 404 otherwise."""
    session = await chat_service.get_session(pool, session_id)
    if not session or session["user_id"] != str(current_user["user_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _fetch_target_word(pool, session: dict) -> tuple[str, str]:
    """Return (word, language) for the session's target item. Raises 422 if not found."""
    target_row = await pool.fetchrow(
        "SELECT word, language FROM word_table WHERE word_id = $1",
        session["target_item_id"],
    )
    if target_row is None and session.get("target_item_type") == "phrase":
        target_row = await pool.fetchrow(
            "SELECT surface_form AS word, language FROM phrase_table WHERE phrase_id = $1",
            session["target_item_id"],
        )
    if target_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target item no longer in vocabulary.",
        )
    return target_row["word"], target_row["language"]


def _compute_sentence_quality(naturalness_list: list[str]) -> str:
    """
    Deterministic quality label from per-turn naturalness scores.
    ≥60% 'high' → excellent, ≥50% 'low' → needs_work, else good.
    """
    if not naturalness_list:
        return "needs_work"
    n = len(naturalness_list)
    highs = naturalness_list.count("high")
    lows  = naturalness_list.count("low")
    if highs >= n * 0.6:
        return "excellent"
    if lows >= n * 0.5:
        return "needs_work"
    return "good"
