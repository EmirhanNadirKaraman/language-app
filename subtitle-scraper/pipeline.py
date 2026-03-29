"""
Pipeline that merges channels from channels.json and subscribed_channels.txt,
fetches video transcripts, and inserts them into the database.

Channels in channels.json have a known language.
Channels in subscribed_channels.txt are language-detected automatically.
"""

import json
import os
import sys
import time

import psycopg2
import yt_dlp
from scrapetube import scrapetube
import spacy
from langdetect import detect, LangDetectException
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# phrase_finder.py loads data/final_result.txt relative to CWD — point it at the project root
_cwd = os.getcwd()
os.chdir(Path(__file__).parent.parent)
sys.path.insert(0, str(Path(__file__).parent))
from phrase_finder import extract_german_logic
from transcript_fetcher import fetch_with_retries
os.chdir(_cwd)


# VIDEOS_PER_CHANNEL = 5
# MAX_CHANNELS = 5

LANG_MODEL_MAP = {
    "en": "en_core_web_sm",
    "de": "de_core_news_md",
    "fr": "fr_core_news_sm",
    "es": "es_core_news_sm",
    "it": "it_core_news_sm",
    "pt": "pt_core_news_sm",
    "ru": "ru_core_news_sm",
    "ja": "ja_core_news_sm",
    "ko": "ko_core_news_sm",
}

LANG_TRANSCRIPT_CODES = {
    "en": ["en-GB", "en", "en-US"],
    "de": ["de", "de-DE", "de-AT"],
    "fr": ["fr", "fr-FR", "fr-CA"],
    "es": ["es", "es-ES", "es-MX", "es-419"],
    "it": ["it", "it-IT"],
    "pt": ["pt", "pt-PT", "pt-BR"],
    "ru": ["ru", "ru-RU", "ru-UA"],
    "ja": ["ja", "ja-JP"],
    "ko": ["ko", "ko-KR"],
}

NO_MORPH_LANGS = {"ja", "ko"}
POS_LIST = {"VERB", "ADJ", "NOUN", "ADV", "PRON"}


def connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_channels(cursor) -> list[dict]:
    """Load active channels from the database."""
    cursor.execute(
        "SELECT youtube_channel_id, channel_name, language FROM channel WHERE active = TRUE"
    )
    return [
        {"id": row[0], "name": row[1] or row[0], "language": row[2]}
        for row in cursor.fetchall()
    ]


def upsert_channel(cursor, channel_id: str, channel_name: str, language: str | None) -> int:
    """Insert or update a channel row, keeping existing name if already set.
    Returns the internal channel.id (integer PK)."""
    cursor.execute(
        """
        INSERT INTO channel (youtube_channel_id, channel_name, language)
        VALUES (%s, %s, %s)
        ON CONFLICT (youtube_channel_id) DO UPDATE
            SET channel_name = CASE
                    WHEN channel.channel_name = '' THEN EXCLUDED.channel_name
                    ELSE channel.channel_name
                END,
                language = COALESCE(channel.language, EXCLUDED.language)
        RETURNING id
        """,
        (channel_id, channel_name, language),
    )
    return cursor.fetchone()[0]


def get_transcript(video_id, language=None):
    """
    Fetch a transcript for a video via yt-dlp with caching and retries.
    - If language is given, look for that language specifically.
    - If language is None, auto-detect from any available transcript.
    Returns (snippets, detected_lang, actual_language_code, transcript_source)
    or (None, None, None, None).
    """
    try:
        if language and language in LANG_TRANSCRIPT_CODES:
            snippets, actual_code, source = fetch_with_retries(
                video_id, LANG_TRANSCRIPT_CODES[language]
            )
            return snippets, language, actual_code, source

        # Auto-detect: try each known language in order
        for lang_code, codes in LANG_TRANSCRIPT_CODES.items():
            try:
                snippets, actual_code, source = fetch_with_retries(video_id, codes)
                sample = " ".join(s["text"] for s in snippets[:20])
                try:
                    detected = detect(sample)
                    if detected in LANG_MODEL_MAP:
                        return snippets, detected, actual_code, source
                except LangDetectException:
                    return snippets, lang_code, actual_code, source
            except ValueError:
                continue  # no subtitles for this language, try next

    except ValueError as e:
        print(f"  No subtitles for {video_id}: {e}")
        return None, None, None, None  # permanent — no subtitles exist

    except Exception as e:
        print(f"  Error fetching transcript for {video_id}: {e}")
        raise  # transient — let caller decide whether to blacklist


def fetch_video_metadata(video_id: str) -> dict | None:
    """
    Fetch channel_id, channel_name, title, thumbnail_url, and category
    for a video in a single yt-dlp call.
    Returns None on failure.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            categories = info.get("categories") or []
            category = categories[0] if categories else (info.get("genre") or "other").strip() or "other"
            return {
                "channel_id":   (info.get("channel_id") or "").strip(),
                "channel_name": (info.get("channel") or info.get("uploader") or "").strip(),
                "title":        info.get("title", ""),
                "thumbnail_url": info.get("thumbnail", ""),
                "category":     category,
            }
    except Exception as e:
        print(f"  [yt-dlp] Could not fetch metadata for {video_id}: {e}")
    return None


def fetch_channel_name(channel_id: str) -> str:
    """Fetch a channel's display name from its channel page via yt-dlp."""
    url = f"https://www.youtube.com/channel/{channel_id}"
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlist_items": "1",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return (info.get("channel") or info.get("uploader") or info.get("title") or "").strip()
    except Exception as e:
        print(f"  [yt-dlp] Could not fetch channel name for {channel_id}: {e}")
    return ""


def fetch_category(video_id: str) -> str:
    """
    Use yt-dlp to extract the category of a YouTube video.
    Returns the first entry in `categories`, falling back to `genre`,
    then to 'other' if nothing is found or an error occurs.
    """
    meta = fetch_video_metadata(video_id)
    return meta["category"] if meta else "other"


def insert_phrases(cursor, sentence_ids, docs):
    # Phase 1: collect all phrases and unique blueprints across all sentences
    all_phrase_data = []  # [(sid, phrases_list), ...]
    unique_blueprints = set()
    for sid, doc in zip(sentence_ids, docs):
        phrases = extract_german_logic(doc)
        if not phrases:
            continue
        all_phrase_data.append((sid, phrases))
        for phrase in phrases:
            unique_blueprints.add(phrase["dictionary_entry"])

    if not all_phrase_data:
        return

    # Phase 2: batch INSERT all blueprints, then batch SELECT to resolve IDs
    # (replaces the per-phrase INSERT + SELECT loop — now 2 round trips total)
    blueprint_list = list(unique_blueprints)
    bp_args = b",".join(cursor.mogrify("(%s,%s)", (bp, bp)) for bp in blueprint_list)
    cursor.execute(
        b"INSERT INTO phrase_blueprint (lookup_key, blueprint) VALUES "
        + bp_args
        + b" ON CONFLICT (lookup_key) DO NOTHING"
    )
    placeholders = ",".join(["%s"] * len(blueprint_list))
    cursor.execute(
        f"SELECT lookup_key, blueprint_id FROM phrase_blueprint WHERE lookup_key IN ({placeholders})",
        blueprint_list,
    )
    blueprint_id_map = {row[0]: row[1] for row in cursor.fetchall()}

    # Phase 3: build and batch INSERT all sentence_to_phrase rows
    rows = []
    for sid, phrases in all_phrase_data:
        for phrase in phrases:
            blueprint_id = blueprint_id_map.get(phrase["dictionary_entry"])
            if blueprint_id is None:
                continue
            rows.append((
                sid,
                blueprint_id,
                " ".join(phrase["sentence_phrase"]),
                phrase["logic"],
                phrase["match_type"],
                phrase["indices"],
            ))

    if rows:
        args = b",".join(cursor.mogrify("(%s,%s,%s,%s,%s,%s)", r) for r in rows)
        cursor.execute(
            b"INSERT INTO sentence_to_phrase "
            b"(sentence_id, blueprint_id, surface_form, logic, match_type, indices) VALUES "
            + args
        )


def clean_sentence(text):
    text = text.replace("\n", " ").replace("\xa0", " ").replace("\u00a0", " ")
    return " ".join(text.split())


def populate(cursor, connection, db_words, video_id, title, thumbnail_url,
             transcript, language, dialect, nlp, sentence_types,
             category="other", channel_id: int | None = None,
             transcript_source: str = "auto"):
    # Skip if video already exists
    cursor.execute("SELECT 1 FROM video WHERE video_id = %s", (video_id,))
    if cursor.fetchone():
        return

    last = transcript[-1]
    duration = last["start"] + last["duration"]
    cursor.execute(
        "INSERT INTO video (video_id, title, thumbnail_url, duration, language, dialect, category, channel_id, transcript_source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (video_id, title, thumbnail_url, duration, language, dialect, category, channel_id, transcript_source),
    )

    # Process sentences via nlp.pipe for efficiency
    texts = [s["text"] for s in transcript]
    sentence_rows = []
    all_tokens = []

    docs = list(nlp.pipe(texts))
    for index, doc in enumerate(docs):
        tokens = [
            (t.text, t.pos_, t.lemma_, t.tag_)
            for t in doc
            if t.pos_ != "PUNCT" and t.text.strip()
        ]
        sentence_rows.append((
            video_id,
            transcript[index]["start"],
            transcript[index]["duration"],
            clean_sentence(transcript[index]["text"]),
            [t[0] for t in tokens],
        ))
        all_tokens.append(tokens)

    args_str = b",".join(cursor.mogrify("(%s,%s,%s,%s,%s)", x) for x in sentence_rows)
    cursor.execute(
        b"INSERT INTO sentence (video_id, start_time, duration, content, tokens) VALUES "
        + args_str
        + b" RETURNING sentence_id"
    )
    sentence_ids = [row[0] for row in cursor.fetchall()]

    # Grammar rules (morphological analysis)
    if language not in NO_MORPH_LANGS:
        types = []
        for idx, doc in enumerate(docs):
            sid = sentence_ids[idx]
            for token in doc:
                if token.pos_ in POS_LIST:
                    for prop, val in token.morph.to_dict().items():
                        rule = token.pos_ + prop + str(val)
                        key = language + "_" + rule
                        rule_id = sentence_types.get(key)
                        if rule_id is None:
                            cursor.execute(
                                "INSERT INTO grammar_rule (rule, language) VALUES (%s,%s) RETURNING rule_id",
                                (rule, language),
                            )
                            rule_id = cursor.fetchone()[0]
                            sentence_types[key] = rule_id
                        types.append((sid, rule_id))

        if types:
            type_str = b",".join(cursor.mogrify("(%s,%s)", x) for x in types)
            cursor.execute(
                b"INSERT INTO sentence_to_grammar_rule (sentence_id, rule_id) VALUES "
                + type_str
                + b" ON CONFLICT DO NOTHING"
            )

    # Insert new words
    video_word_set = {token for tokens in all_tokens for token in tokens}
    new_words = video_word_set - db_words
    db_words.update(new_words)

    if new_words:
        word_tup = [(w[0], language, w[1], w[2], w[3]) for w in new_words]
        word_str = b",".join(cursor.mogrify("(%s,%s,%s,%s,%s)", x) for x in word_tup)
        cursor.execute(
            b"INSERT INTO word_table (word, language, pos, lemma, tag) VALUES "
            + word_str
            + b" ON CONFLICT DO NOTHING"
        )

    connection.commit()

    # word_to_sentence links — single batch lookup instead of one query per token
    unique_word_keys = list({(t[0], t[1]) for tokens in all_tokens for t in tokens})
    if unique_word_keys:
        placeholders = ",".join(["(%s,%s)"] * len(unique_word_keys))
        flat_keys = [val for k in unique_word_keys for val in k]
        cursor.execute(
            f"SELECT word_id, word, pos FROM word_table WHERE language = %s AND (word, pos) IN ({placeholders})",
            [language] + flat_keys,
        )
        word_id_map = {(r[1], r[2]): r[0] for r in cursor.fetchall()}
    else:
        word_id_map = {}

    w2s = [
        (word_id_map[(t[0], t[1])], sentence_ids[idx])
        for idx, tokens in enumerate(all_tokens)
        for t in tokens
        if (t[0], t[1]) in word_id_map
    ]

    if w2s:
        w2s_str = b",".join(cursor.mogrify("(%s,%s)", x) for x in w2s)
        cursor.execute(
            b"INSERT INTO word_to_sentence (word_id, sentence_id) VALUES "
            + w2s_str
            + b" ON CONFLICT DO NOTHING"
        )

    if language == "de":
        insert_phrases(cursor, sentence_ids, docs)

    connection.commit()


def _notify_user(cursor, connection, request_id: int, notif_type: str, payload: dict) -> None:
    """Insert a notification row for the user who submitted this request."""
    cursor.execute(
        """
        INSERT INTO notification (user_id, type, payload)
        SELECT user_id, %s, %s
        FROM   content_request
        WHERE  request_id = %s AND user_id IS NOT NULL
        """,
        (notif_type, json.dumps(payload), request_id),
    )
    connection.commit()


def _mark_request(cursor, connection, request_id: int, status: str, error: str | None = None) -> None:
    cursor.execute(
        "UPDATE content_request SET status = %s, error = %s, updated_at = NOW() WHERE request_id = %s",
        (status, error, request_id),
    )
    connection.commit()


def _scan_channel_videos(  # noqa: PLR0913
    cursor, connection,
    youtube_channel_id: str, internal_channel_id: int, language: str | None,
    nlp_cache: dict, sentence_types: dict, db_words: set,
    processed_videos: set, blacklist: set,
    skip_video_id: str | None = None,
) -> int:
    """Iterate a channel's videos and process any that haven't been seen yet.

    skip_video_id: video already processed by the caller — skip without counting.
    Returns the number of newly added videos.
    """
    added = 0
    for candidate in scrapetube.get_channel(youtube_channel_id):
        vid_id = candidate["videoId"]
        if vid_id == skip_video_id:
            continue
        if vid_id in processed_videos or vid_id in blacklist:
            continue

        title     = candidate["title"]["runs"][0]["text"]
        thumbnail = candidate["thumbnail"]["thumbnails"][-1]["url"]

        try:
            fetched, detected_lang, language_code, transcript_source = get_transcript(vid_id, language)
        except Exception:
            continue  # transient — retry next run
        if fetched is None:
            blacklist.add(vid_id)
            cursor.execute(
                "INSERT INTO video_blacklist (video_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (vid_id,),
            )
            connection.commit()
            continue

        if detected_lang not in nlp_cache:
            if detected_lang not in LANG_MODEL_MAP:
                continue
            try:
                nlp_cache[detected_lang] = spacy.load(LANG_MODEL_MAP[detected_lang])
                nlp_cache[detected_lang].select_pipes(
                    enable=["tok2vec", "tagger", "attribute_ruler", "lemmatizer"]
                )
            except Exception:
                continue

        populate(
            cursor=cursor,
            connection=connection,
            db_words=db_words,
            video_id=vid_id,
            title=title,
            thumbnail_url=thumbnail,
            transcript=fetched,
            language=detected_lang,
            dialect=language_code,
            nlp=nlp_cache[detected_lang],
            sentence_types=sentence_types,
            category=fetch_category(vid_id),
            channel_id=internal_channel_id,
            transcript_source=transcript_source,
        )
        processed_videos.add(vid_id)
        added += 1
        print(f"    [{added}] {title} ({detected_lang})")

    return added


def _process_channel_request(  # noqa: PLR0913
    cursor, connection, youtube_channel_id: str, request_id: int,
    nlp_cache: dict, sentence_types: dict, db_words: set,
    processed_videos: set, blacklist: set,
) -> None:
    """Ensure the channel is in the DB, then scan and process any new videos."""
    cursor.execute(
        "SELECT id, channel_name, language FROM channel WHERE youtube_channel_id = %s",
        (youtube_channel_id,),
    )
    row = cursor.fetchone()
    if row:
        internal_channel_id, channel_name, language = row
        channel_name = channel_name or youtube_channel_id
        print(f"  [request] channel already known: {channel_name}")
    else:
        channel_name = fetch_channel_name(youtube_channel_id)
        cursor.execute(
            """
            INSERT INTO channel (youtube_channel_id, channel_name)
            VALUES (%s, %s)
            ON CONFLICT (youtube_channel_id) DO UPDATE
                SET channel_name = CASE
                        WHEN channel.channel_name = '' THEN EXCLUDED.channel_name
                        ELSE channel.channel_name
                    END
            RETURNING id
            """,
            (youtube_channel_id, channel_name),
        )
        internal_channel_id = cursor.fetchone()[0]
        connection.commit()
        language = None
        print(f"  [request] added new channel: {channel_name or youtube_channel_id}")

    print(f"  [request] scanning {channel_name or youtube_channel_id} for new videos…")
    added = _scan_channel_videos(
        cursor, connection,
        youtube_channel_id, internal_channel_id, language,
        nlp_cache, sentence_types, db_words, processed_videos, blacklist,
    )
    print(f"  [request] done — {added} new video(s) added")
    _mark_request(cursor, connection, request_id, "done")
    _notify_user(cursor, connection, request_id, "channel_done", {
        "youtube_channel_id": youtube_channel_id,
        "channel_name":       channel_name or youtube_channel_id,
        "videos_added":       added,
    })


def _process_video_request(  # noqa: PLR0913
    cursor, connection, video_id: str, request_id: int,
    nlp_cache: dict, sentence_types: dict, db_words: set,
    processed_videos: set, blacklist: set,
) -> None:
    """Process a single requested video."""
    if video_id in blacklist:
        _mark_request(cursor, connection, request_id, "failed", "video is blacklisted")
        print(f"  [request] video {video_id} is blacklisted")
        return

    if video_id in processed_videos:
        _mark_request(cursor, connection, request_id, "done")
        print(f"  [request] video {video_id} already in DB")
        return

    meta = fetch_video_metadata(video_id)
    if not meta or not meta["channel_id"]:
        _mark_request(cursor, connection, request_id, "failed", "could not fetch video metadata")
        print(f"  [request] could not fetch metadata for {video_id}")
        return

    internal_channel_id = upsert_channel(cursor, meta["channel_id"], meta["channel_name"], None)

    try:
        fetched, detected_lang, language_code, transcript_source = get_transcript(video_id)
    except Exception:
        _mark_request(cursor, connection, request_id, "failed", "transcript fetch error (transient)")
        print(f"  [request] transient error fetching transcript for {video_id}, will retry")
        return
    if fetched is None:
        blacklist.add(video_id)
        cursor.execute(
            "INSERT INTO video_blacklist (video_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (video_id,),
        )
        _mark_request(cursor, connection, request_id, "failed", "no transcript available")
        connection.commit()
        print(f"  [request] no transcript for {video_id}")
        return

    if detected_lang not in nlp_cache:
        if detected_lang not in LANG_MODEL_MAP:
            _mark_request(cursor, connection, request_id, "failed", f"unsupported language: {detected_lang}")
            return
        try:
            nlp_cache[detected_lang] = spacy.load(LANG_MODEL_MAP[detected_lang])
            nlp_cache[detected_lang].select_pipes(
                enable=["tok2vec", "tagger", "attribute_ruler", "lemmatizer"]
            )
        except Exception as e:
            _mark_request(cursor, connection, request_id, "failed", f"spacy load error: {e}")
            return

    populate(
        cursor=cursor, connection=connection, db_words=db_words,
        video_id=video_id, title=meta["title"], thumbnail_url=meta["thumbnail_url"],
        transcript=fetched, language=detected_lang, dialect=language_code,
        nlp=nlp_cache[detected_lang], sentence_types=sentence_types,
        category=meta["category"], channel_id=internal_channel_id,
        transcript_source=transcript_source,
    )
    processed_videos.add(video_id)
    print(f"  [request] processed video: {meta['title']} ({detected_lang})")
    _mark_request(cursor, connection, request_id, "done")
    _notify_user(cursor, connection, request_id, "video_done", {
        "video_id": video_id,
        "title":    meta["title"],
    })


def process_pending_requests(
    cursor, connection,
    nlp_cache: dict, sentence_types: dict, db_words: set,
    processed_videos: set, blacklist: set,
) -> None:
    cursor.execute(
        "SELECT request_id, request_type, content_id FROM content_request WHERE status = 'pending'"
    )
    pending = cursor.fetchall()
    if not pending:
        return

    print(f"\nProcessing {len(pending)} pending content request(s)...")
    for request_id, request_type, content_id in pending:
        try:
            if request_type == "channel":
                _process_channel_request(
                    cursor, connection, content_id, request_id,
                    nlp_cache, sentence_types, db_words, processed_videos, blacklist,
                )
            else:
                _process_video_request(
                    cursor, connection, content_id, request_id,
                    nlp_cache, sentence_types, db_words, processed_videos, blacklist,
                )
        except Exception as e:
            _mark_request(cursor, connection, request_id, "failed", str(e))
            print(f"  [request] error processing {request_type} {content_id}: {e}")


def main():
    connection = connect()
    cursor = connection.cursor()

    channels = load_channels(cursor)
    print(f"Loaded {len(channels)} channels total")

    cursor.execute("SELECT video_id FROM video")
    processed_videos = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT video_id FROM video_blacklist")
    blacklist = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT language || '_' || rule, rule_id FROM grammar_rule")
    sentence_types = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT word, pos, lemma FROM word_table")
    db_words = {(r[0], r[1], r[2]) for r in cursor.fetchall()}

    nlp_cache = {}

    process_pending_requests(
        cursor, connection, nlp_cache, sentence_types, db_words, processed_videos, blacklist
    )

    # Reload channels in case a channel request just added new ones
    channels = load_channels(cursor)

    # Build one lazy iterator per channel
    channel_iters = [
        (ch, iter(scrapetube.get_channel(ch["id"])))
        for ch in channels
    ]
    print(f"Active channels: {len(channel_iters)}")

    total = 0
    while channel_iters:
        next_round = []
        for channel, vid_iter in channel_iters:
            channel_id   = channel["id"]
            channel_name = channel["name"] or channel_id
            language     = channel["language"]
            internal_channel_id = upsert_channel(cursor, channel_id, channel_name, language)

            # Advance to next unprocessed, non-blacklisted video for this channel
            video = None
            while True:
                try:
                    candidate = next(vid_iter)
                except StopIteration:
                    print(f"\nChannel exhausted this run: {channel_name}")
                    break
                vid_id = candidate["videoId"]
                if vid_id in blacklist or vid_id in processed_videos:
                    continue
                video = candidate
                break

            if video is None:
                continue  # channel exhausted — not added to next_round

            video_id = video["videoId"]
            try:
                fetched, detected_lang, language_code, transcript_source = get_transcript(video_id, language)
            except Exception:
                next_round.append((channel, vid_iter))  # transient — retry next run
                continue

            if fetched is None:
                blacklist.add(video_id)
                cursor.execute(
                    "INSERT INTO video_blacklist (video_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (video_id,),
                )
                connection.commit()
                next_round.append((channel, vid_iter))
                continue

            if detected_lang not in nlp_cache:
                try:
                    nlp_cache[detected_lang] = spacy.load(LANG_MODEL_MAP[detected_lang])
                    nlp_cache[detected_lang].select_pipes(
                        enable=["tok2vec", "tagger", "attribute_ruler", "lemmatizer"]
                    )
                except Exception:
                    print(f"  No spacy model for '{detected_lang}', skipping video")
                    next_round.append((channel, vid_iter))
                    continue

            title = video["title"]["runs"][0]["text"]
            thumbnail = video["thumbnail"]["thumbnails"][-1]["url"]

            category = fetch_category(video_id)

            populate(
                cursor=cursor,
                connection=connection,
                db_words=db_words,
                video_id=video_id,
                title=title,
                thumbnail_url=thumbnail,
                transcript=fetched,
                language=detected_lang,
                dialect=language_code,
                nlp=nlp_cache[detected_lang],
                sentence_types=sentence_types,
                category=category,
                channel_id=internal_channel_id,
                transcript_source=transcript_source,
            )

            processed_videos.add(video_id)
            total += 1
            print(f"  [{total}] {channel_name}: {title} ({detected_lang})")
            next_round.append((channel, vid_iter))

        channel_iters = next_round

    print("\nDone.")


def run_pending_requests_only() -> None:
    """Process only pending content_request rows, then exit."""
    connection = connect()
    cursor = connection.cursor()

    cursor.execute("SELECT video_id FROM video")
    processed_videos = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT video_id FROM video_blacklist")
    blacklist = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT language || '_' || rule, rule_id FROM grammar_rule")
    sentence_types = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT word, pos, lemma FROM word_table")
    db_words = {(r[0], r[1], r[2]) for r in cursor.fetchall()}

    nlp_cache: dict = {}
    process_pending_requests(
        cursor, connection, nlp_cache, sentence_types, db_words, processed_videos, blacklist
    )
    connection.close()
    print("\nDone.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests-only", action="store_true",
                        help="Process pending content requests and exit (skip channel loop)")
    args = parser.parse_args()

    if args.requests_only:
        run_pending_requests_only()
    else:
        main()
