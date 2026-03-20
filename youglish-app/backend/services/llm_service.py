import os
import random

import anthropic
import asyncpg

from . import llm_cache_service

_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_MOCK = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")
_MODEL = "claude-haiku-4-5-20251001"

_MOCK_REPLIES = [
    "Das ist gut! Kannst du mir mehr erzählen?",
    "Sehr interessant! Wie war dein Tag?",
    "Super! Ich freue mich, das zu hören.",
    "Toll gemacht! Magst du das erklären?",
    "Wunderbar! Was denkst du darüber?",
]

_MOCK_CORRECTIONS = [
    [{"original": "ich bin gegangen", "corrected": "ich bin gegangen", "explanation": "Mock: correct usage of Perfekt."}],
    [{"original": "das Hund", "corrected": "der Hund", "explanation": "Mock: 'Hund' is masculine, use 'der'."}],
    [],
    [],
    [],
]

_MOCK_HINTS = {
    "intent_hint": "Try expressing that you used up or consumed something.",
    "anchor_hint": "Tipp: Denke an ein Verb, das mit 'ver' beginnt…",
    "example": "Ich habe gestern Abend mein ganzes Taschengeld verbraucht.",
}

_MOCK_OPENINGS = [
    "Hallo! Ich plane gerade ein Wochenendausflug und bin mir noch nicht sicher, wohin ich fahren soll. Hast du irgendwelche Empfehlungen?",
    "Hey! Ich war gerade im Café und habe einen wirklich interessanten Menschen getroffen. Was machst du so am Wochenende?",
    "Guten Tag! Ich bereite gerade ein Abendessen für Freunde vor — habt ihr ein Lieblingsrezept, das ich ausprobieren sollte?",
]

_SYSTEM = """\
You are a warm, encouraging German language tutor in a free-conversation practice app.
The learner is practising spoken German. Your job is twofold:
  1. Keep the conversation going naturally (reply in German).
  2. Quietly correct any language errors the learner made.

Rules:
- Reply conversationally in German. Be friendly, brief, and encouraging.
- If the user wrote in English, reply in English but gently nudge them to try in German.
- List ONLY genuine language errors (grammar, wrong word, spelling). Skip style preferences.
- If there are no errors, return an empty corrections array.
- You MUST call the evaluate_and_reply tool — never respond with raw text.
"""

_EVAL_TOOL: anthropic.types.ToolParam = {
    "name": "evaluate_and_reply",
    "description": "Produce a structured response: a conversational reply plus any corrections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "Your conversational reply.",
            },
            "language_detected": {
                "type": "string",
                "enum": ["de", "en", "mixed"],
                "description": "Dominant language of the user's message.",
            },
            "corrections": {
                "type": "array",
                "description": "Language errors found. Empty list if none.",
                "items": {
                    "type": "object",
                    "properties": {
                        "original":    {"type": "string"},
                        "corrected":   {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["original", "corrected", "explanation"],
                },
            },
        },
        "required": ["reply", "language_detected", "corrections"],
    },
}


# ---------------------------------------------------------------------------
# Guided chat — opener
# ---------------------------------------------------------------------------

_GUIDED_OPEN_TOOL: anthropic.types.ToolParam = {
    "name": "open_conversation",
    "description": "Generate the opening message of a guided conversation scenario.",
    "input_schema": {
        "type": "object",
        "properties": {
            "opening": {
                "type": "string",
                "description": "The opening message in the target language (2-3 sentences).",
            }
        },
        "required": ["opening"],
    },
}


async def guided_open(
    target_word: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> str:
    """
    Generate an opening scenario that naturally invites the target word without revealing it.
    Returns the opening message text.

    Cached permanently in llm_cache when pool is provided — the same
    word+language always produces a pedagogically valid opener.
    """
    if _MOCK:
        return random.choice(_MOCK_OPENINGS)

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "guided_open", _MODEL, {"target_word": target_word, "language": language}
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached["opening"]

    system = (
        f"You are a warm, engaging {language} conversation partner starting a role-play. "
        f"The hidden pedagogical goal is for the learner to eventually use the word/phrase "
        f'"{target_word}" naturally — but you must NOT use it yourself. '
        f"Create a brief, realistic social scene (café, travel plans, weekend talk, etc.) "
        f"that makes it natural to respond using that kind of vocabulary. "
        f"Write in {language}, 2–3 sentences, no hints that this is an exercise. "
        f"You MUST call the open_conversation tool."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=system,
        tools=[_GUIDED_OPEN_TOOL],
        tool_choice={"type": "tool", "name": "open_conversation"},
        messages=[{"role": "user", "content": "Start the conversation."}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    opening = tool_block.input["opening"]

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(
            pool, cache_key, "guided_open", _MODEL, {"opening": opening}
        )

    return opening


# ---------------------------------------------------------------------------
# Guided chat — progressive hints
# ---------------------------------------------------------------------------

_GUIDED_HINTS_TOOL: anthropic.types.ToolParam = {
    "name": "generate_hints",
    "description": "Generate three progressive learning hints for a target word/phrase.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent_hint": {
                "type": "string",
                "description": (
                    "One sentence in English describing the concept or action to express. "
                    "Must NOT name the target word, its direct translation, or a clear synonym. "
                    "Describes what kind of meaning the learner should convey."
                ),
            },
            "anchor_hint": {
                "type": "string",
                "description": (
                    "A short German clue — a related word, a prefix hint (e.g. 'beginnt mit ver…'), "
                    "or a closely related concept — that narrows the search without giving the full answer. "
                    "Must NOT be the target word itself."
                ),
            },
            "example": {
                "type": "string",
                "description": (
                    "A complete, natural German sentence that uses the target word in a realistic context. "
                    "The target word must appear exactly as-is or in a natural inflected form."
                ),
            },
        },
        "required": ["intent_hint", "anchor_hint", "example"],
    },
}


async def guided_hints(
    target_word: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> dict:
    """
    Generate three progressive hints for a guided-chat target word.

    Returns:
        {"intent_hint": str, "anchor_hint": str, "example": str}

    Cached permanently by (target_word, language) — the same word always gets
    the same hints, so re-opening a session is instant.
    """
    if _MOCK:
        return dict(_MOCK_HINTS)

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "guided_hints", _MODEL, {"target_word": target_word, "language": language}
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached

    system = (
        f'You are creating pedagogical hints for a language learner whose hidden target word/phrase is "{target_word}" in {language}.\n\n'
        f"Generate exactly three hints in order of increasing explicitness:\n"
        f"1. intent_hint — English only. Describe what concept or action to express WITHOUT naming the target or its translation.\n"
        f"2. anchor_hint — German only. Give a partial clue: a related word, a prefix hint, or a semantic neighbour. "
        f"Do NOT use the target word itself.\n"
        f"3. example — A full natural German sentence using the target word in a realistic everyday context.\n\n"
        f"You MUST call the generate_hints tool."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=system,
        tools=[_GUIDED_HINTS_TOOL],
        tool_choice={"type": "tool", "name": "generate_hints"},
        messages=[{"role": "user", "content": "Generate the hints now."}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = {
        "intent_hint": tool_block.input["intent_hint"],
        "anchor_hint":  tool_block.input["anchor_hint"],
        "example":      tool_block.input["example"],
    }

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(
            pool, cache_key, "guided_hints", _MODEL, result
        )

    return result


# ---------------------------------------------------------------------------
# Guided chat — per-turn evaluation + reply
# ---------------------------------------------------------------------------

_GUIDED_EVAL_TOOL: anthropic.types.ToolParam = {
    "name": "guided_evaluate",
    "description": "Evaluate the learner's message and produce a structured reply for guided practice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "Conversational follow-up in the target language.",
            },
            "language_detected": {
                "type": "string",
                "enum": ["de", "en", "mixed"],
                "description": "Dominant language of the user's message.",
            },
            "corrections": {
                "type": "array",
                "description": "Genuine language errors only. Empty list if none.",
                "items": {
                    "type": "object",
                    "properties": {
                        "original":    {"type": "string"},
                        "corrected":   {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["original", "corrected", "explanation"],
                },
            },
            "target_used": {
                "type": "boolean",
                "description": "True if the learner used the target word/phrase or a clear inflection of it.",
            },
            "target_counted": {
                "type": "boolean",
                "description": (
                    "True only if the usage is in natural, correct target-language context "
                    "and counts toward mastery. False if used in English, forced, or grammatically wrong."
                ),
            },
            "feedback_short": {
                "type": "string",
                "description": (
                    "One brief encouraging sentence about the target usage (e.g. 'Sehr gut, du hast X perfekt benutzt!'). "
                    "Empty string if the target was not used."
                ),
            },
            "naturalness": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Overall naturalness and quality of the learner's target-language usage in this turn.",
            },
        },
        "required": [
            "reply", "language_detected", "corrections",
            "target_used", "target_counted", "feedback_short", "naturalness",
        ],
    },
}


async def guided_evaluate(
    user_content: str,
    history: list[dict],
    target_word: str,
    language: str,
) -> dict:
    """
    Evaluate one user turn in a guided session.

    Returns:
        {
            reply: str,
            language_detected: "de" | "en" | "mixed",
            corrections: [...],
            target_used: bool,
            target_counted: bool,
            feedback_short: str,
            naturalness: "high" | "medium" | "low",
        }
    """
    if _MOCK:
        used = target_word.lower() in user_content.lower()
        return {
            "reply": random.choice(_MOCK_REPLIES),
            "language_detected": "de",
            "corrections": random.choice(_MOCK_CORRECTIONS),
            "target_used": used,
            "target_counted": used,
            "feedback_short": f"Sehr gut, du hast '{target_word}' verwendet!" if used else "",
            "naturalness": "medium",
        }

    system = (
        f"You are a warm, encouraging {language} conversation partner in a guided practice session. "
        f'The hidden target word/phrase is "{target_word}". '
        f"The learner should use it naturally — never reveal the target or ask them to use it.\n\n"
        f"Per turn:\n"
        f"1. Continue the conversation naturally (reply in {language}).\n"
        f"2. Correct ONLY genuine language errors (grammar, wrong word, spelling). Skip style preferences.\n"
        f"3. Evaluate whether the learner used the target word/phrase.\n\n"
        f"Rules:\n"
        f'- target_used: true if "{target_word}" or a clear inflected form appears.\n'
        f"- target_counted: true only if used in natural, correct {language}. "
        f"False if used in English, grammatically wrong, or clearly forced.\n"
        f"- feedback_short: one encouraging sentence if used; empty string otherwise.\n"
        f"- naturalness: overall quality of the {language} in this turn.\n"
        f"- If the user wrote mostly in English, reply in English and gently nudge toward {language}.\n"
        f"- You MUST call the guided_evaluate tool."
    )

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_content})

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        tools=[_GUIDED_EVAL_TOOL],
        tool_choice={"type": "tool", "name": "guided_evaluate"},
        messages=messages,
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = tool_block.input

    return {
        "reply":             result["reply"],
        "language_detected": result["language_detected"],
        "corrections":       result.get("corrections", []),
        "target_used":       result["target_used"],
        "target_counted":    result["target_counted"],
        "feedback_short":    result.get("feedback_short", ""),
        "naturalness":       result.get("naturalness", "medium"),
    }


# ---------------------------------------------------------------------------
# Free chat — evaluate and reply
# ---------------------------------------------------------------------------

async def evaluate_and_reply(
    user_content: str,
    history: list[dict],
) -> dict:
    """
    Returns:
        {
            reply: str,
            language_detected: "de" | "en" | "mixed",
            corrections: [{"original", "corrected", "explanation"}, ...],
            word_matches: [],   # reserved for phrase-matcher integration
        }
    """
    if _MOCK:
        return {
            "reply": random.choice(_MOCK_REPLIES),
            "language_detected": "de",
            "corrections": random.choice(_MOCK_CORRECTIONS),
            "word_matches": [],
        }

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_content})

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=_SYSTEM,
        tools=[_EVAL_TOOL],
        tool_choice={"type": "tool", "name": "evaluate_and_reply"},
        messages=messages,
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = tool_block.input

    return {
        "reply": result["reply"],
        "language_detected": result["language_detected"],
        "corrections": result.get("corrections", []),
        "word_matches": [],
    }
