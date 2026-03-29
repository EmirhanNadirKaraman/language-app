import asyncio
import datetime
from random import randint
from typing import Any

import asyncpg

from .nlp_service import NLPService

POINTS_PER_CLOZE = 3

_TATOEBA_LANG_MAP: dict[str, str] = {
    "en": "eng",
    "de": "deu",
    "fr": "fra",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "ja": "jpn",
    "ru": "rus",
    "ko": "kor",
    "tr": "tur",
    "pl": "pol",
    "sv": "swe",
}


class SRSScheduler:
    """Computes next due-date and strength for spaced-repetition reviews."""

    DEFAULT_MINS: list[int] = [1, 10]
    EASE_FACTOR: float = 2.5
    MINS_IN_DAY: int = 1440
    MAX_STRENGTH: int = 8

    def _fuzz(self, number: float) -> float:
        return number * (randint(100, 124) / 100)

    def calculate_due_date(
        self, strength: int, current_due_date: datetime.datetime
    ) -> datetime.datetime:
        now = datetime.datetime.now()
        if strength == self.MAX_STRENGTH:
            return now + datetime.timedelta(days=365 * 10)
        if strength <= len(self.DEFAULT_MINS):
            return now + datetime.timedelta(
                minutes=self._fuzz(self.DEFAULT_MINS[strength - 1])
            )
        days_past = (now - current_due_date).days
        added_days = (
            pow(self.EASE_FACTOR, strength - len(self.DEFAULT_MINS) - 1)
            + days_past / 2
        )
        return now + datetime.timedelta(minutes=self._fuzz(added_days * self.MINS_IN_DAY))


_scheduler = SRSScheduler()


def _translate_language(language: str) -> str:
    if language not in _TATOEBA_LANG_MAP:
        raise ValueError(f"Language not supported: {language!r}")
    return _TATOEBA_LANG_MAP[language]


def _build_cloze_results(
    rows: list, target_lang: str, target_language: str
) -> list[dict[str, Any]]:
    """Sync: apply NLP word-removal to each cloze row. Run in a thread pool."""
    result = []
    if target_lang == "eng":
        for row in rows:
            removed = NLPService.remove_word(target_language, row[1], row[0], pos=row[3])
            result.append(
                {
                    "word": row[0],
                    "target_sentence": row[1],
                    "translation": row[2],
                    "removed": removed,
                    "word_id": row[4],
                }
            )
    else:
        for row in rows:
            removed = NLPService.remove_word(target_language, row[1], row[0])
            result.append(
                {
                    "word": row[0],
                    "target_sentence": row[1],
                    "translation": row[2],
                    "removed": removed,
                    "word_id": row[3],
                }
            )
    return result


async def check_answer(
    pool: asyncpg.Pool, uid: str, word_id: int, correct: bool
) -> None:
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", uid)
        if user is None:
            raise ValueError("User does not exist")

        row = await conn.fetchrow(
            "SELECT word_id, strength, due_date FROM word_strength "
            "WHERE uid = $1 AND word_id = $2",
            uid,
            word_id,
        )
        if row is None:
            raise ValueError("Word does not exist in user vocab")

        strength: int = row["strength"]
        due_date: datetime.datetime = row["due_date"]

        if strength == SRSScheduler.MAX_STRENGTH:
            raise ValueError("Word is already mastered")

        new_strength = strength + 1 if correct else 1
        new_due_date = _scheduler.calculate_due_date(new_strength, due_date)

        async with conn.transaction():
            await conn.execute(
                "UPDATE word_strength SET strength = $1, due_date = $2 "
                "WHERE uid = $3 AND word_id = $4",
                new_strength,
                new_due_date,
                uid,
                word_id,
            )
            if correct:
                await conn.execute(
                    "UPDATE user_stat_table "
                    "SET cloze_count = user_stat_table.cloze_count + 1"
                )
                lang_row = await conn.fetchrow(
                    "SELECT language FROM word_table WHERE word_id = $1", word_id
                )
                if lang_row:
                    await conn.execute(
                        "UPDATE leaderboard SET score = leaderboard.score + $1 "
                        "WHERE uid = $2 AND language = $3",
                        POINTS_PER_CLOZE,
                        uid,
                        lang_row["language"],
                    )


async def get_magic_sentences(
    pool: asyncpg.Pool,
    uid: str,
    word_id: int,
    language: str,
    full_sentence: bool,
    page: int,
    rows_per_page: int,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        lang_row = await conn.fetchrow(
            "SELECT regex, is_learnable FROM language_table WHERE language = $1",
            language,
        )
        if lang_row is None:
            raise ValueError(f"Language with code = {language!r} does not exist")
        if not lang_row["is_learnable"]:
            raise ValueError(f"Language with code = {language!r} is not learnable")

        regex = lang_row["regex"] if full_sentence else "^(.*)"

        rows = await conn.fetch(
            """
            WITH sentences_with_word AS (
                SELECT S.sentence_id, S.content, row_to_json(V) AS video
                FROM sentence S, video V
                WHERE EXISTS (
                    SELECT 1 FROM word_to_sentence WTS
                    WHERE WTS.word_id = $1 AND S.sentence_id = WTS.sentence_id
                )
                AND S.video_id = V.video_id AND V.language = $2
            ),
            word_count AS (
                SELECT count(*) AS cnt, sentence_id
                FROM word_to_sentence
                WHERE EXISTS (
                    SELECT 1 FROM sentences_with_word
                    WHERE sentences_with_word.sentence_id = word_to_sentence.sentence_id
                )
                GROUP BY sentence_id
            ),
            known_words AS (
                SELECT count(*) AS cnt, WTS.sentence_id
                FROM word_to_sentence WTS
                INNER JOIN word_strength WS ON WS.word_id = WTS.word_id AND WS.uid = $3
                WHERE strength = 8
                GROUP BY sentence_id
            ),
            distinct_sentences AS (
                SELECT DISTINCT ON (SWW.content)
                    SWW.content, SWW.sentence_id, SWW.video,
                    word_count.cnt - COALESCE(known_words.cnt, 0) AS unknown_count
                FROM sentences_with_word SWW
                INNER JOIN word_count ON SWW.sentence_id = word_count.sentence_id
                LEFT JOIN known_words ON word_count.sentence_id = known_words.sentence_id
                WHERE SWW.content ~ $4
                ORDER BY SWW.content
                OFFSET (($5 - 1) * $6) ROWS
                LIMIT $7
            )
            SELECT * FROM distinct_sentences ORDER BY unknown_count
            """,
            word_id,
            language,
            uid,
            regex,
            page,
            rows_per_page,
            rows_per_page,
        )

        sentences = [
            {
                "content": r["content"],
                "sentence_id": r["sentence_id"],
                "video_properties": r["video"],
                "unknown_count": r["unknown_count"],
            }
            for r in rows
        ]

        total_count = await conn.fetchval(
            """
            SELECT count(*)
            FROM word_to_sentence WTS, sentence S
            WHERE WTS.sentence_id = S.sentence_id
              AND WTS.word_id = $1
              AND S.content ~ $2
            """,
            word_id,
            regex,
        )

        return {"sentences": sentences, "total_count": total_count}


async def get_cloze_questions(
    pool: asyncpg.Pool,
    uid: str,
    native_language: str,
    target_language: str,
    is_exact: bool,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        word_rows = await conn.fetch(
            """
            SELECT WT.word, WT.pos
            FROM word_strength WS, word_table WT
            WHERE WS.word_id = WT.word_id
              AND uid = $1
              AND language = $2
              AND due_date < $3
            """,
            uid,
            target_language,
            datetime.datetime.now(),
        )

        if not word_rows:
            return []

        word_arr = [{"word": r["word"], "pos": r["pos"]} for r in word_rows]

        native_lang = _translate_language(native_language)
        target_lang = _translate_language(target_language)

        query_parts: list[str] = []
        params: list[Any] = []
        p = 1

        if target_lang == "eng":
            for word in word_arr:
                query_parts.append(
                    f"(SELECT WTS.word, TS2.sentence, TS1.sentence, WTS.pos, WT.word_id"
                    f" FROM tatoeba_sentence_pairs SP,"
                    f"      tatoeba_sentence TS1, tatoeba_sentence TS2,"
                    f"      tatoeba_word_to_sentence WTS, word_table WT"
                    f" WHERE WT.word = ${p} AND WT.pos = ${p+1}"
                    f"   AND WTS.sentence_id = TS2.sentence_id"
                    f"   AND SP.second_id = TS2.sentence_id AND TS2.language = ${p+2}"
                    f"   AND SP.first_id = TS1.sentence_id AND TS1.language = ${p+3}"
                    f"   AND WT.word = WTS.word AND WT.pos = WTS.pos"
                    f" ORDER BY random() LIMIT 1)"
                )
                params.extend([word["word"], word["pos"] or "", target_lang, native_lang])
                p += 4

                query_parts.append(
                    f"(SELECT WTS.word, TS1.sentence, TS2.sentence, WTS.pos, WT.word_id"
                    f" FROM tatoeba_sentence_pairs SP,"
                    f"      tatoeba_sentence TS1, tatoeba_sentence TS2,"
                    f"      tatoeba_word_to_sentence WTS, word_table WT"
                    f" WHERE WTS.sentence_id = TS1.sentence_id"
                    f"   AND WT.word = ${p} AND WT.pos = ${p+1}"
                    f"   AND SP.first_id = TS1.sentence_id AND TS1.language = ${p+2}"
                    f"   AND SP.second_id = TS2.sentence_id AND TS2.language = ${p+3}"
                    f"   AND WT.word = WTS.word AND WT.pos = WTS.pos"
                    f" ORDER BY random() LIMIT 1)"
                )
                params.extend([word["word"], word["pos"] or "", target_lang, native_lang])
                p += 4
        else:
            for word in word_arr:
                query_parts.append(
                    f"(SELECT WTS.word, TS2.sentence, TS1.sentence, WT.word_id"
                    f" FROM tatoeba_sentence_pairs SP,"
                    f"      tatoeba_sentence TS1, tatoeba_sentence TS2,"
                    f"      tatoeba_word_to_sentence WTS, word_table WT"
                    f" WHERE WT.word = ${p}"
                    f"   AND WTS.sentence_id = TS2.sentence_id"
                    f"   AND SP.second_id = TS2.sentence_id AND TS2.language = ${p+1}"
                    f"   AND SP.first_id = TS1.sentence_id AND TS1.language = ${p+2}"
                    f"   AND WT.word = WTS.word"
                    f" ORDER BY random() LIMIT 1)"
                )
                params.extend([word["word"], target_lang, native_lang])
                p += 3

                query_parts.append(
                    f"(SELECT WTS.word, TS1.sentence, TS2.sentence, WT.word_id"
                    f" FROM tatoeba_sentence_pairs SP,"
                    f"      tatoeba_sentence TS1, tatoeba_sentence TS2,"
                    f"      tatoeba_word_to_sentence WTS, word_table WT"
                    f" WHERE WTS.sentence_id = TS1.sentence_id"
                    f"   AND WT.word = ${p}"
                    f"   AND SP.first_id = TS1.sentence_id AND TS1.language = ${p+1}"
                    f"   AND SP.second_id = TS2.sentence_id AND TS2.language = ${p+2}"
                    f"   AND WT.word = WTS.word"
                    f" ORDER BY random() LIMIT 1)"
                )
                params.extend([word["word"], target_lang, native_lang])
                p += 3

        union_query = " UNION ".join(query_parts)
        final_query = (
            f"SELECT DISTINCT ON (result.word) * FROM ({union_query}) AS result"
        )

        rows = await conn.fetch(final_query, *params)
        if not rows:
            return []

        # Convert Records to plain tuples before handing off to the thread pool
        plain_rows = [tuple(r) for r in rows]

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _build_cloze_results, plain_rows, target_lang, target_language
    )
