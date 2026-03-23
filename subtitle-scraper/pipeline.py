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
from scrapetube import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

yt_api = YouTubeTranscriptApi()
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


def load_channels():
    with open("merged_channels.json") as f:
        return json.load(f)


def get_transcript(video_id, language=None):
    """
    Fetch a manual transcript for a video.
    - If language is given, look for that language specifically.
    - If language is None, find any manual transcript and detect its language.
    Returns (transcript_obj, language_code) or (None, None).
    """
    try:
        transcript_list = yt_api.list(video_id)

        if language and language in LANG_TRANSCRIPT_CODES:
            t = transcript_list.find_manually_created_transcript(LANG_TRANSCRIPT_CODES[language])
            return t, language

        # Auto-detect: use first available manual transcript
        for t in transcript_list:
            if not t.is_generated:
                fetched = t.fetch()
                sample = " ".join(s.text for s in fetched[:20])
                try:
                    detected = detect(sample)
                    if detected in LANG_MODEL_MAP:
                        return t, detected
                except LangDetectException:
                    pass

    except NoTranscriptFound:
        pass
    except TranscriptsDisabled:
        pass
    except Exception as e:
        print(f"  Error fetching transcript for {video_id}: {e}")

    return None, None


def insert_phrases(cursor, sentence_ids, texts):
    for sid, text in zip(sentence_ids, texts):
        phrases = extract_german_logic(text)
        if not phrases:
            continue

        rows = []
        for phrase in phrases:
            blueprint = phrase["dictionary_entry"]

            cursor.execute(
                "INSERT INTO phrase_blueprint (lookup_key, blueprint) VALUES (%s, %s) "
                "ON CONFLICT (lookup_key) DO NOTHING",
                (blueprint, blueprint),
            )
            cursor.execute(
                "SELECT blueprint_id FROM phrase_blueprint WHERE lookup_key = %s",
                (blueprint,),
            )
            blueprint_id = cursor.fetchone()[0]

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
             transcript, language, dialect, nlp, sentence_types):
    # Skip if video already exists
    cursor.execute("SELECT 1 FROM video WHERE video_id = %s", (video_id,))
    if cursor.fetchone():
        return

    last = transcript[-1]
    duration = last.start + last.duration
    cursor.execute(
        "INSERT INTO video (video_id, title, thumbnail_url, duration, language, dialect) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (video_id, title, thumbnail_url, duration, language, dialect),
    )

    # Process sentences via nlp.pipe for efficiency
    texts = [s.text for s in transcript]
    sentence_rows = []
    all_tokens = []

    for index, doc in enumerate(nlp.pipe(texts)):
        tokens = [
            (t.text, t.pos_, t.lemma_, t.tag_)
            for t in doc
            if t.pos_ != "PUNCT" and t.text.strip()
        ]
        sentence_rows.append((
            video_id,
            transcript[index].start,
            transcript[index].duration,
            clean_sentence(transcript[index].text),
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
        for idx, doc in enumerate(nlp.pipe(texts)):
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

    # word_to_sentence links
    w2s = []
    for idx, tokens in enumerate(all_tokens):
        sid = sentence_ids[idx]
        for token in tokens:
            cursor.execute(
                "SELECT word_id FROM word_table WHERE word=%s AND language=%s AND pos=%s",
                (token[0], language, token[1]),
            )
            row = cursor.fetchone()
            if row:
                w2s.append((row[0], sid))

    if w2s:
        w2s_str = b",".join(cursor.mogrify("(%s,%s)", x) for x in w2s)
        cursor.execute(
            b"INSERT INTO word_to_sentence (word_id, sentence_id) VALUES "
            + w2s_str
            + b" ON CONFLICT DO NOTHING"
        )

    if language == "de":
        insert_phrases(cursor, sentence_ids, texts)

    connection.commit()


def main():
    connection = connect()
    cursor = connection.cursor()

    channels = load_channels()
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
            channel_id = channel["id"]
            channel_name = channel["name"] or channel_id
            language = channel["language"]

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
            transcript_obj, detected_lang = get_transcript(video_id, language)

            if transcript_obj is None:
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

            fetched = None
            for attempt in range(3):
                try:
                    fetched = transcript_obj.fetch()
                    break
                except Exception as e:
                    print(f"  Fetch attempt {attempt + 1}/3 failed for {video_id}: {e}")
                    time.sleep(2 ** attempt)

            if fetched is None:
                print(f"  Skipping {video_id} after 3 failed attempts (not blacklisted)")
                next_round.append((channel, vid_iter))
                continue

            populate(
                cursor=cursor,
                connection=connection,
                db_words=db_words,
                video_id=video_id,
                title=title,
                thumbnail_url=thumbnail,
                transcript=fetched,
                language=detected_lang,
                dialect=transcript_obj.language_code,
                nlp=nlp_cache[detected_lang],
                sentence_types=sentence_types,
            )

            processed_videos.add(video_id)
            total += 1
            print(f"  [{total}] {channel_name}: {title} ({detected_lang})")
            next_round.append((channel, vid_iter))

        channel_iters = next_round

    print("\nDone.")


if __name__ == "__main__":
    main()
