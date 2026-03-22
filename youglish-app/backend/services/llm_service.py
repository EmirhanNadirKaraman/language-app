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
# Prep view — item info (translation + grammar explanation)
# ---------------------------------------------------------------------------

_PREP_INFO_TOOL: anthropic.types.ToolParam = {
    "name": "item_prep_info",
    "description": "Provide structured language-learning prep information for a vocabulary item.",
    "input_schema": {
        "type": "object",
        "properties": {
            "translation": {
                "type": "string",
                "description": "Concise English translation. For verbs include the base form (e.g. 'to spend (time)').",
            },
            "grammar_structure": {
                "type": "string",
                "description": (
                    "The core grammatical pattern in compact form. "
                    "Examples: 'verbringen + Akkusativ', 'sich freuen + über + Akkusativ', "
                    "'Nomen (der/die/das)'. Keep it under 60 characters."
                ),
            },
            "grammar_explanation": {
                "type": "string",
                "description": (
                    "2–4 sentences covering: (1) meaning and grammatical role, "
                    "(2) required case/preposition/reflexive structure, "
                    "(3) one common learner mistake to avoid."
                ),
            },
        },
        "required": ["translation", "grammar_structure", "grammar_explanation"],
    },
}


async def prep_item_info(
    display_text: str,
    item_type: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> dict:
    """
    Return {translation, grammar_structure, grammar_explanation} for a vocabulary item.

    Cached permanently in llm_cache by (display_text, item_type, language).
    Called as part of GET /insights/prep — always loads, never deferred.
    """
    if _MOCK:
        return {
            "translation": "to spend (time)",
            "grammar_structure": f"{display_text} + Akkusativ",
            "grammar_explanation": (
                f"Mock: '{display_text}' is a common {language} {item_type}. "
                f"It typically requires the accusative case. "
                f"Common mistake: confusing it with a similar-sounding word."
            ),
        }

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "prep_item_info", _MODEL,
            {"display_text": display_text, "item_type": item_type, "language": language},
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached

    system = (
        f"You are a concise {language} language learning assistant. "
        f"Provide structured prep information for a {item_type} the learner is about to practise. "
        f"Be precise, practical, and production-oriented. "
        f"You MUST call the item_prep_info tool."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=system,
        tools=[_PREP_INFO_TOOL],
        tool_choice={"type": "tool", "name": "item_prep_info"},
        messages=[{
            "role": "user",
            "content": f"Provide prep information for the {language} {item_type}: \"{display_text}\"",
        }],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = {
        "translation":         tool_block.input["translation"],
        "grammar_structure":   tool_block.input["grammar_structure"],
        "grammar_explanation": tool_block.input["grammar_explanation"],
    }

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(pool, cache_key, "prep_item_info", _MODEL, result)

    return result


# ---------------------------------------------------------------------------
# Prep view — examples + templates (on-demand)
# ---------------------------------------------------------------------------

_PREP_EXAMPLES_TOOL: anthropic.types.ToolParam = {
    "name": "item_examples",
    "description": "Generate a usage example and two reusable production templates for a vocabulary item.",
    "input_schema": {
        "type": "object",
        "properties": {
            "example": {
                "type": "string",
                "description": "One clear, natural sentence in the target language using the item in a realistic context.",
            },
            "templates": {
                "type": "array",
                "description": (
                    "Exactly 2 reusable sentence templates for production practice. "
                    "Use [square bracket slots] for variable parts (e.g. [Zeit], [Person], [Ort]). "
                    "Each template should be a complete sentence skeleton."
                ),
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "required": ["example", "templates"],
    },
}


async def prep_generate_examples(
    display_text: str,
    item_type: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> dict:
    """
    Return {example: str, templates: [str, str]}.
    Cached permanently by (display_text, item_type, language).
    Called only when the user explicitly requests example generation.
    """
    if _MOCK:
        return {
            "example": f"Ich verwende '{display_text}' in einem Beispielsatz.",
            "templates": [
                f"Ich [Verb] {display_text} [Ergänzung].",
                f"[Person] hat {display_text} [Kontext] [Verb].",
            ],
        }

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "prep_examples", _MODEL,
            {"display_text": display_text, "item_type": item_type, "language": language},
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached

    system = (
        f"You are a {language} language learning assistant focused on production practice. "
        f"Generate a usage example and two reusable sentence templates for a {language} {item_type}. "
        f"Templates use [square bracket slots] for variable parts. "
        f"Favour everyday, naturalistic contexts. You MUST call the item_examples tool."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=system,
        tools=[_PREP_EXAMPLES_TOOL],
        tool_choice={"type": "tool", "name": "item_examples"},
        messages=[{
            "role": "user",
            "content": f"Generate an example and templates for the {language} {item_type}: \"{display_text}\"",
        }],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    result = {
        "example":   tool_block.input["example"],
        "templates": tool_block.input["templates"][:2],
    }

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(pool, cache_key, "prep_examples", _MODEL, result)

    return result


async def get_examples_if_cached(
    display_text: str,
    item_type: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> dict | None:
    """
    Return cached examples/templates without generating.
    Returns None if not in cache — the caller shows a "Generate examples" button.
    """
    if pool is None:
        return None
    cache_key = llm_cache_service.make_cache_key(
        "prep_examples", _MODEL,
        {"display_text": display_text, "item_type": item_type, "language": language},
    )
    return await llm_cache_service.get_cached(pool, cache_key)


# ---------------------------------------------------------------------------
# Guided chat — post-session summary
# ---------------------------------------------------------------------------

_GUIDED_SUMMARY_TOOL: anthropic.types.ToolParam = {
    "name": "guided_session_summary",
    "description": "Generate concise post-session feedback for a completed guided practice session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "what_went_well": {
                "type": "string",
                "description": "One specific sentence about what the learner did well.",
            },
            "what_to_improve": {
                "type": "string",
                "description": (
                    "One sentence on the single most important thing to improve. "
                    "Empty string if there is nothing significant."
                ),
            },
            "corrective_note": {
                "type": "string",
                "description": (
                    "A direct corrective comment on the most critical grammar or usage error observed. "
                    "Format: 'Use X instead of Y because...' "
                    "Empty string if no significant errors were observed."
                ),
            },
        },
        "required": ["what_went_well", "what_to_improve", "corrective_note"],
    },
}


async def guided_summarize(
    target_word: str,
    language: str,
    target_used: bool,
    target_counted: bool,
    sentence_quality: str,
    all_corrections: list[dict],
    total_turns: int,
) -> dict:
    """
    Generate concise post-session feedback after a guided chat session ends.

    Returns:
        {
            what_went_well: str,
            what_to_improve: str,   # empty string = nothing significant
            corrective_note: str,   # empty string = no corrections
        }
    """
    if _MOCK:
        if target_counted:
            return {
                "what_went_well": f"You used '{target_word}' naturally and correctly — well done.",
                "what_to_improve": "",
                "corrective_note": "",
            }
        elif target_used:
            return {
                "what_went_well": "You engaged with the topic confidently.",
                "what_to_improve": f"Make sure to use '{target_word}' in correct, natural {language} next time.",
                "corrective_note": "",
            }
        else:
            return {
                "what_went_well": "You kept the conversation going.",
                "what_to_improve": f"Try to work '{target_word}' into your response.",
                "corrective_note": "",
            }

    # Deduplicate corrections by original form, cap at 4 for prompt brevity
    seen: set[str] = set()
    unique_corrections: list[dict] = []
    for c in all_corrections:
        key = c.get("original", "")
        if key and key not in seen:
            seen.add(key)
            unique_corrections.append(c)
            if len(unique_corrections) >= 4:
                break

    corrections_text = "\n".join(
        f'  • "{c["original"]}" → "{c["corrected"]}": {c["explanation"]}'
        for c in unique_corrections
    ) or "  (none)"

    if target_counted:
        target_status = "used correctly in natural context"
    elif target_used:
        target_status = "used but not in correct/natural target-language context"
    else:
        target_status = "not used"

    system = (
        f"You are a concise, critical {language} language tutor writing a post-session summary.\n"
        f"Session details:\n"
        f"  Target word/phrase: \"{target_word}\"\n"
        f"  Target usage: {target_status}\n"
        f"  Overall sentence quality: {sentence_quality}\n"
        f"  Turns taken: {total_turns}\n"
        f"  Corrections observed:\n{corrections_text}\n\n"
        f"Write direct, honest, specific feedback. One sentence per field. "
        f"Be encouraging but critical — no empty praise.\n"
        f"You MUST call the guided_session_summary tool."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=384,
        system=system,
        tools=[_GUIDED_SUMMARY_TOOL],
        tool_choice={"type": "tool", "name": "guided_session_summary"},
        messages=[{"role": "user", "content": "Generate the session summary now."}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    return {
        "what_went_well":  tool_block.input.get("what_went_well", ""),
        "what_to_improve": tool_block.input.get("what_to_improve", ""),
        "corrective_note": tool_block.input.get("corrective_note", ""),
    }


# ---------------------------------------------------------------------------
# Grammar rule — long explanation (on-demand, cached permanently)
# ---------------------------------------------------------------------------

_GRAMMAR_EXPLAIN_TOOL: anthropic.types.ToolParam = {
    "name": "grammar_rule_explanation",
    "description": "Generate a detailed, learner-friendly explanation of a grammar rule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "long_explanation": {
                "type": "string",
                "description": (
                    "3–5 sentences covering: (1) what the rule is and why it matters, "
                    "(2) how it works with concrete examples, "
                    "(3) the most common learner mistake and how to avoid it. "
                    "Write directly for an intermediate language learner. "
                    "Include at least two example sentences in the target language."
                ),
            },
        },
        "required": ["long_explanation"],
    },
}


async def grammar_rule_explanation(
    slug: str,
    title: str,
    short_explanation: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> str:
    """
    Generate and cache a detailed explanation for a grammar rule.

    Returns the long_explanation string.
    Cached permanently by (slug, language) — grammar rules don't change.
    Called only when the user explicitly clicks "Learn more" in the UI.
    """
    if _MOCK:
        return (
            f"Mock: {title} is an important {language} grammar rule. "
            f"{short_explanation} "
            f"Example: 'Ich freue mich über das Geschenk.' "
            f"Common mistake: forgetting the reflexive pronoun or using the wrong case."
        )

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "grammar_rule_explanation", _MODEL, {"slug": slug, "language": language}
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached["long_explanation"]

    system = (
        f"You are a concise {language} grammar tutor writing learner-friendly rule explanations. "
        f"Be specific, practical, and include real example sentences. "
        f"You MUST call the grammar_rule_explanation tool."
    )

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=system,
        tools=[_GRAMMAR_EXPLAIN_TOOL],
        tool_choice={"type": "tool", "name": "grammar_rule_explanation"},
        messages=[{
            "role": "user",
            "content": (
                f"Explain the {language} grammar rule '{title}'.\n"
                f"Short summary: {short_explanation}"
            ),
        }],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    long_explanation: str = tool_block.input["long_explanation"]

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(
            pool, cache_key, "grammar_rule_explanation", _MODEL,
            {"long_explanation": long_explanation},
        )

    return long_explanation


async def get_grammar_explanation_if_cached(
    slug: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> str | None:
    """
    Return the cached long_explanation for a grammar rule without generating it.
    Returns None if not in cache — the caller surfaces a "Learn more" button.
    """
    if pool is None:
        return None
    cache_key = llm_cache_service.make_cache_key(
        "grammar_rule_explanation", _MODEL, {"slug": slug, "language": language}
    )
    cached = await llm_cache_service.get_cached(pool, cache_key)
    return cached["long_explanation"] if cached else None


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
