"""
First-class grammar rule support.

grammar_rule_table stores a curated set of language-specific grammar rules
that are linked to phrases via the phrase_type field.  This lets the prep
view surface relevant grammar context without requiring per-phrase annotation.

Linkage strategy
----------------
Each rule carries an `applicable_phrase_types` TEXT[] column.  When fetching
grammar rules for a phrase, we query:

    WHERE $phrase_type = ANY(applicable_phrase_types) AND language = $lang

This means:
  - reflexive_verb phrases  → 'reflexive-verbs' rule
  - verb_pattern phrases    → 'verb-preposition-case' rule
  - collocation phrases     → no rule (too generic)

The mapping is deterministic and requires no join table.

Seeding
-------
Call seed_rules(pool, language) at startup (main.py lifespan).
ON CONFLICT (slug, language) DO NOTHING makes it idempotent.

Future hooks
------------
Grammar rules intentionally have no progress tracking in v1.  When wanted:
  - enrich_grammar_rules() mirrors enrich_phrases() to add user knowledge data
  - get_prioritized_items(item_type='grammar_rule') already works once knowledge
    rows exist in user_word_knowledge
"""
from __future__ import annotations

import asyncpg


# ---------------------------------------------------------------------------
# Seed data — curated German grammar rules (v1)
# ---------------------------------------------------------------------------

_GERMAN_RULES: list[dict] = [
    {
        "slug": "reflexive-verbs",
        "title": "Reflexive Verbs",
        "rule_type": "reflexive_verb",
        "short_explanation": (
            "Reflexive verbs require a reflexive pronoun (mich / dich / sich / uns / euch) "
            "that refers back to the subject. The pronoun agrees with the subject in person "
            "and number and is typically placed directly after the conjugated verb."
        ),
        "pattern_hint": "sich + Verb (sich freuen, sich erinnern, sich beeilen)",
        "applicable_phrase_types": ["reflexive_verb"],
        "applicable_lemmas": [],
    },
    {
        "slug": "verb-preposition-case",
        "title": "Verb + Preposition + Case",
        "rule_type": "verb_preposition_case",
        "short_explanation": (
            "Many German verbs require a specific preposition followed by a fixed grammatical "
            "case (accusative or dative). These combinations must be memorised — the case is "
            "not predictable from the preposition alone."
        ),
        "pattern_hint": "Verb + Präp + Kasus (warten auf + Akk, träumen von + Dat)",
        "applicable_phrase_types": ["verb_pattern"],
        "applicable_lemmas": [],
    },
    {
        "slug": "dative-verbs",
        "title": "Verbs that Govern the Dative",
        "rule_type": "verb_preposition_case",
        "short_explanation": (
            "Some verbs take a dative object directly (without a preposition): helfen, "
            "gefallen, gehören, folgen, glauben, danken. The dative case applies even "
            "though no preposition is present — a common source of errors."
        ),
        "pattern_hint": "Verb + jdm. (Dativ) — helfen, gefallen, gehören",
        "applicable_phrase_types": ["verb_pattern"],
        "applicable_lemmas": [
            "helfen", "gefallen", "gehören", "folgen", "glauben", "danken",
            "fehlen", "schmecken", "passen", "begegnen",
        ],
    },
    {
        "slug": "separable-verbs",
        "title": "Separable Verbs (Trennbare Verben)",
        "rule_type": "separable_verb",
        "short_explanation": (
            "Separable verbs have a detachable prefix (an-, ab-, auf-, mit-, …). "
            "In the present tense the prefix moves to the very end of the main clause. "
            "In subordinate clauses, in the infinitive, and with modal verbs the verb "
            "stays together."
        ),
        "pattern_hint": "Präfix + Verb → Verb … Präfix (anfangen → ich fange an)",
        "applicable_phrase_types": [],
        "applicable_lemmas": [
            "anfangen", "aufhören", "aufmachen", "zumachen", "ankommen", "abfahren",
            "einkaufen", "ausgehen", "anrufen", "aufstehen", "mitkommen", "fernsehen",
            "vorhaben", "zuhören",
        ],
    },
    {
        "slug": "modal-verbs",
        "title": "Modal Verbs (Modalverben)",
        "rule_type": "tense_auxiliary",
        "short_explanation": (
            "The six modal verbs — können, müssen, wollen, sollen, dürfen, mögen — "
            "express ability, necessity, desire, obligation, or permission. They are "
            "conjugated in position 2 and push the main verb as an infinitive to the "
            "end of the clause."
        ),
        "pattern_hint": "Modal (konj.) + … + Infinitiv am Ende",
        "applicable_phrase_types": [],
        "applicable_lemmas": ["können", "müssen", "wollen", "sollen", "dürfen", "mögen"],
    },
    {
        "slug": "perfekt-sein-haben",
        "title": "Perfekt: sein vs. haben",
        "rule_type": "tense_auxiliary",
        "short_explanation": (
            "In the Perfekt (conversational past) most verbs use 'haben' as their auxiliary, "
            "but verbs expressing motion toward a destination (fahren, gehen, fliegen) or a "
            "change of state (einschlafen, aufwachen, werden) use 'sein'. "
            "The past participle always goes to the end."
        ),
        "pattern_hint": "haben/sein (konj.) + … + Partizip II",
        "applicable_phrase_types": [],
        "applicable_lemmas": [
            "fahren", "gehen", "fliegen", "kommen", "laufen", "schwimmen",
            "sterben", "passieren", "werden", "einschlafen", "aufwachen", "aufstehen",
        ],
    },
    {
        "slug": "verb-second-word-order",
        "title": "Verb-Second Word Order (V2)",
        "rule_type": "word_order",
        "short_explanation": (
            "In German main clauses the conjugated verb is always the second element. "
            "If anything other than the subject starts the sentence — an adverb, object, "
            "or adverbial clause — the subject and verb swap positions (subject inversion)."
        ),
        "pattern_hint": "Feld₁ → Verb (konj.) → Subjekt/Rest … (Heute fahre ich …)",
        "applicable_phrase_types": [],
        "applicable_lemmas": [],
    },
    {
        "slug": "verb-final-subordinate",
        "title": "Verb-Final in Subordinate Clauses",
        "rule_type": "word_order",
        "short_explanation": (
            "Subordinate clauses introduced by weil, dass, obwohl, wenn, als, ob, etc. "
            "send the conjugated verb to the very end. When an auxiliary (haben, sein, werden) "
            "is present it follows the participle or infinitive."
        ),
        "pattern_hint": "Konnektor + Subjekt + … + Verb (am Ende)",
        "applicable_phrase_types": [],
        "applicable_lemmas": [],
    },
    {
        "slug": "two-way-prepositions",
        "title": "Two-Way Prepositions (Wechselpräpositionen)",
        "rule_type": "verb_preposition_case",
        "short_explanation": (
            "The prepositions an, auf, hinter, in, neben, über, unter, vor, zwischen "
            "take the accusative for movement toward a goal (Wohin?) and the dative for "
            "location or state (Wo?). Choosing the wrong case is one of the most common "
            "errors for learners."
        ),
        "pattern_hint": "Wohin? → Akk | Wo? → Dat  (Ich lege es auf den Tisch. Es liegt auf dem Tisch.)",
        "applicable_phrase_types": [],
        "applicable_lemmas": [
            "an", "auf", "hinter", "in", "neben", "über", "unter", "vor", "zwischen",
        ],
    },
    {
        "slug": "adjective-declension",
        "title": "Adjective Endings (Adjektivdeklination)",
        "rule_type": "adjective_declension",
        "short_explanation": (
            "German adjectives change their endings based on grammatical gender, case, "
            "and the type of determiner that precedes them. There are three declension "
            "patterns: weak (after definite articles), mixed (after indefinite articles), "
            "and strong (no article). The endings encode the same case/gender information "
            "that the article already provides."
        ),
        "pattern_hint": "Adj-Endung ~ Art. + Genus + Kasus (der gute Mann, ein guter Mann)",
        "applicable_phrase_types": [],
        "applicable_lemmas": [],
    },
]

_RULES_BY_LANGUAGE: dict[str, list[dict]] = {
    "de": _GERMAN_RULES,
}


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

async def seed_rules(
    pool: asyncpg.Pool,
    language: str = "de",
) -> int:
    """
    Populate grammar_rule_table with the curated rule set for *language*.

    ON CONFLICT (slug, language) DO NOTHING makes this idempotent on every
    startup.  Returns the count of newly inserted rows.
    """
    rules = _RULES_BY_LANGUAGE.get(language, [])
    if not rules:
        return 0

    inserted = 0
    async with pool.acquire() as conn:
        for rule in rules:
            result = await conn.execute(
                """
                INSERT INTO grammar_rule_table
                    (slug, title, rule_type, short_explanation, language,
                     pattern_hint, applicable_phrase_types, applicable_lemmas)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (slug, language) DO UPDATE SET
                    applicable_lemmas = EXCLUDED.applicable_lemmas
                """,
                rule["slug"],
                rule["title"],
                rule["rule_type"],
                rule["short_explanation"],
                language,
                rule.get("pattern_hint"),
                rule["applicable_phrase_types"],
                rule.get("applicable_lemmas", []),
            )
            if result.endswith(" 1"):
                inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

async def get_rules_for_phrase_type(
    pool: asyncpg.Pool,
    phrase_type: str,
    language: str,
) -> list[dict]:
    """
    Return grammar rules whose applicable_phrase_types include *phrase_type*.

    Used by insights_service.get_prep_data() when item_type='phrase'.
    Returns an empty list for phrase types with no linked rules (e.g. 'collocation').
    """
    rows = await pool.fetch(
        """
        SELECT rule_id, slug, title, rule_type, short_explanation,
               language, pattern_hint
        FROM grammar_rule_table
        WHERE language = $1
          AND $2 = ANY(applicable_phrase_types)
        ORDER BY rule_id
        """,
        language, phrase_type,
    )
    return [dict(r) for r in rows]


async def get_rules_for_lemma(
    pool: asyncpg.Pool,
    lemma: str,
    language: str,
) -> list[dict]:
    """
    Return grammar rules whose applicable_lemmas include *lemma*.

    Used by insights_service.get_prep_data() when item_type='word'.
    Returns an empty list for lemmas with no linked rules.
    """
    rows = await pool.fetch(
        """
        SELECT rule_id, slug, title, rule_type, short_explanation,
               language, pattern_hint
        FROM grammar_rule_table
        WHERE language = $1
          AND $2 = ANY(applicable_lemmas)
        ORDER BY rule_id
        """,
        language, lemma,
    )
    return [dict(r) for r in rows]


async def get_rule_by_slug(
    pool: asyncpg.Pool,
    slug: str,
    language: str,
) -> dict | None:
    """Return a single grammar rule by slug, or None if not found."""
    row = await pool.fetchrow(
        """
        SELECT rule_id, slug, title, rule_type, short_explanation,
               language, pattern_hint
        FROM grammar_rule_table
        WHERE slug = $1 AND language = $2
        """,
        slug, language,
    )
    return dict(row) if row else None
