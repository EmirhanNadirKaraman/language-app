-- ============================================================
-- RESET (uncomment to wipe everything and start fresh)
-- ============================================================
/*
drop index if exists fuzzy_word_search_index_gin;
drop index if exists wts_sentence_id_index;
drop index if exists sentence_video_id_idx;
drop index if exists video_idx;
drop index if exists video_idx_video_id;
drop index if exists user_learned_language_cognito;
drop index if exists user_grammar_cognito;
drop index if exists grammar_rule_language_idx;

drop sequence if exists sentence_id_seq cascade;
drop sequence if exists video_id_seq cascade;

drop table if exists sentence_to_phrase cascade;
drop table if exists phrase_blueprint cascade;
drop table if exists sentence_to_grammar_rule cascade;
drop table if exists word_to_sentence cascade;
drop table if exists word_strength cascade;
drop table if exists sentence cascade;
drop table if exists video cascade;
drop table if exists video_blacklist cascade;
drop table if exists video_category cascade;
drop table if exists word_table cascade;
drop table if exists grammar_rule cascade;
drop table if exists processed_channel cascade;
drop table if exists most_frequent_words cascade;
drop table if exists user_grammar cascade;
drop table if exists user_learned_language cascade;
drop table if exists user_stat_table cascade;
drop table if exists user_table cascade;
drop table if exists leaderboard cascade;
drop table if exists user_video_category cascade;
drop table if exists language_table cascade;
*/

-- ============================================================
-- EXTENSIONS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- SEQUENCES
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS sentence_id_seq;
CREATE SEQUENCE IF NOT EXISTS video_id_seq;

-- ============================================================
-- CORE CONTENT TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS language_table (
    language              TEXT    NOT NULL,
    iso_code              CHAR(3) NOT NULL,
    regex                 TEXT    DEFAULT '^[A-Z](.*)[!?.]$',
    is_learnable          BOOLEAN NOT NULL DEFAULT TRUE,
    is_interface_language BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (language)
);

INSERT INTO language_table (language, iso_code) VALUES ('de', 'deu') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code) VALUES ('fr', 'fra') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code) VALUES ('es', 'spa') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code) VALUES ('it', 'ita') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code) VALUES ('pt', 'por') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code) VALUES ('pl', 'pol') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code) VALUES ('sv', 'swe') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code, regex) VALUES ('ru', 'rus', '^[А-Я](.*)[!?.]$') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code, regex) VALUES ('ja', 'jpn', '^.*$') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code, regex) VALUES ('ko', 'kor', '^.*$') ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code, regex, is_interface_language) VALUES ('en', 'eng', '^[A-Z](.*)[!?.]$', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO language_table (language, iso_code, regex, is_learnable, is_interface_language) VALUES ('tr', 'tur', NULL, FALSE, TRUE) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS video_category (
    category TEXT NOT NULL,
    PRIMARY KEY (category)
);

INSERT INTO video_category (category) VALUES
    ('other'),
    ('Film & Animation'),
    ('Autos & Vehicles'),
    ('Music'),
    ('Pets & Animals'),
    ('Sports'),
    ('Short Movies'),
    ('Travel & Events'),
    ('Gaming'),
    ('Videoblogging'),
    ('People & Blogs'),
    ('Comedy'),
    ('Entertainment'),
    ('News & Politics'),
    ('Howto & Style'),
    ('Education'),
    ('Science & Technology'),
    ('Nonprofits & Activism')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS channel (
    id                 SERIAL PRIMARY KEY,
    youtube_channel_id TEXT   NOT NULL UNIQUE,
    channel_name       TEXT   NOT NULL DEFAULT '',
    language           TEXT   REFERENCES language_table(language),
    active             BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_channel_language ON channel (language);
CREATE INDEX IF NOT EXISTS idx_channel_active   ON channel (active);

CREATE TABLE IF NOT EXISTS video (
    video_id      TEXT    DEFAULT nextval('video_id_seq') PRIMARY KEY,
    title         TEXT    NOT NULL,
    thumbnail_url TEXT    NOT NULL,
    duration      FLOAT8  NOT NULL,
    language      TEXT    NOT NULL,
    dialect       TEXT    NOT NULL,
    category      TEXT    NOT NULL DEFAULT 'other',
    channel_id    INTEGER,
    CONSTRAINT fk_video_category FOREIGN KEY (category)   REFERENCES video_category (category),
    CONSTRAINT fk_video_channel  FOREIGN KEY (channel_id) REFERENCES channel        (id)
);

CREATE INDEX IF NOT EXISTS idx_video_channel_id ON video (channel_id);

CREATE TABLE IF NOT EXISTS video_blacklist (
    video_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS sentence (
    sentence_id INT DEFAULT nextval('sentence_id_seq') PRIMARY KEY,
    video_id    TEXT   NOT NULL,
    start_time  FLOAT8 NOT NULL,
    duration    FLOAT8 NOT NULL,
    content     TEXT   NOT NULL,
    tokens      TEXT[] NOT NULL,
    token_ids   INT[],
    CONSTRAINT fk_sentence_video FOREIGN KEY (video_id) REFERENCES video (video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS word_table (
    word_id  SERIAL PRIMARY KEY,
    word     TEXT NOT NULL,
    language TEXT NOT NULL,
    pos      TEXT NOT NULL,
    tag      TEXT NOT NULL,
    lemma    TEXT NOT NULL,
    UNIQUE (word, language, pos)
);

CREATE TABLE IF NOT EXISTS word_to_sentence (
    word_id     INT NOT NULL,
    sentence_id INT NOT NULL,
    PRIMARY KEY (word_id, sentence_id),
    CONSTRAINT fk_wts_word     FOREIGN KEY (word_id)     REFERENCES word_table (word_id) ON DELETE CASCADE,
    CONSTRAINT fk_wts_sentence FOREIGN KEY (sentence_id) REFERENCES sentence (sentence_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS grammar_rule (
    rule_id  SERIAL PRIMARY KEY,
    rule     TEXT NOT NULL,
    language TEXT NOT NULL,
    UNIQUE (rule, language)
);

CREATE TABLE IF NOT EXISTS sentence_to_grammar_rule (
    sentence_id INT NOT NULL,
    rule_id     INT NOT NULL,
    PRIMARY KEY (sentence_id, rule_id),
    CONSTRAINT fk_stgr_sentence FOREIGN KEY (sentence_id) REFERENCES sentence (sentence_id) ON DELETE CASCADE,
    CONSTRAINT fk_stgr_rule     FOREIGN KEY (rule_id)     REFERENCES grammar_rule (rule_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS most_frequent_words (
    word_id INT NOT NULL,
    PRIMARY KEY (word_id),
    CONSTRAINT fk_mfw_word FOREIGN KEY (word_id) REFERENCES word_table (word_id) ON DELETE CASCADE
);

-- ============================================================
-- PHRASE TABLES (phrase_finder.py)
-- ============================================================

-- Dictionary entries loaded from data/final_result.txt
-- e.g., lookup_key='geben', blueprint='geben jdm. etw.'
CREATE TABLE IF NOT EXISTS phrase_blueprint (
    blueprint_id SERIAL PRIMARY KEY,
    lookup_key   TEXT NOT NULL,
    blueprint    TEXT NOT NULL,
    UNIQUE (lookup_key)
);

-- Phrases extracted from sentences by phrase_finder.py
CREATE TABLE IF NOT EXISTS sentence_to_phrase (
    id           SERIAL PRIMARY KEY,
    sentence_id  INT  NOT NULL,
    blueprint_id INT,            -- NULL when match_type = 'constructed'
    surface_form TEXT NOT NULL,  -- actual tokens joined, e.g. 'gibt mir das'
    logic        TEXT NOT NULL,  -- e.g. 'geben -> jdm. -> etw.'
    match_type   TEXT NOT NULL,  -- 'exact' | 'fuzzy' | 'constructed' | 'lemma'
    indices      INT[] NOT NULL, -- token indices within the sentence
    CONSTRAINT fk_stp_sentence  FOREIGN KEY (sentence_id)  REFERENCES sentence (sentence_id)  ON DELETE CASCADE,
    CONSTRAINT fk_stp_blueprint FOREIGN KEY (blueprint_id) REFERENCES phrase_blueprint (blueprint_id) ON DELETE SET NULL
);

-- ============================================================
-- USER TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS user_table (
    uid               TEXT PRIMARY KEY,
    username          TEXT NOT NULL,
    current_language  TEXT DEFAULT '',
    email             TEXT NOT NULL,
    photo             TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_learned_language (
    uid               TEXT NOT NULL,
    learned_language  TEXT NOT NULL,
    PRIMARY KEY (uid, learned_language),
    CONSTRAINT fk_ull_user FOREIGN KEY (uid) REFERENCES user_table (uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS word_strength (
    uid      TEXT      NOT NULL,
    word_id  INT       NOT NULL,
    due_date TIMESTAMP NOT NULL,
    strength INT       DEFAULT 1,
    PRIMARY KEY (uid, word_id),
    CONSTRAINT fk_ws_user FOREIGN KEY (uid)     REFERENCES user_table (uid)     ON DELETE CASCADE,
    CONSTRAINT fk_ws_word FOREIGN KEY (word_id) REFERENCES word_table (word_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_grammar (
    uid     TEXT NOT NULL,
    rule_id INT  NOT NULL,
    PRIMARY KEY (uid, rule_id),
    CONSTRAINT fk_ug_user FOREIGN KEY (uid)     REFERENCES user_table (uid)         ON DELETE CASCADE,
    CONSTRAINT fk_ug_rule FOREIGN KEY (rule_id) REFERENCES grammar_rule (rule_id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_stat_table (
    uid                  TEXT NOT NULL,
    language             TEXT NOT NULL,
    total_time           INT  DEFAULT 0,
    shown_sentence_count INT  DEFAULT 0,
    cloze_count          INT  DEFAULT 0,
    PRIMARY KEY (uid, language),
    CONSTRAINT fk_ust_user FOREIGN KEY (uid) REFERENCES user_table (uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leaderboard (
    uid      TEXT NOT NULL,
    language TEXT NOT NULL,
    score    INT  DEFAULT 0,
    PRIMARY KEY (uid, language),
    CONSTRAINT fk_lb_user FOREIGN KEY (uid) REFERENCES user_table (uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_video_category (
    uid            TEXT NOT NULL,
    video_category TEXT NOT NULL,
    PRIMARY KEY (uid, video_category),
    CONSTRAINT fk_uvc_user     FOREIGN KEY (uid)           REFERENCES user_table     (uid)      ON DELETE CASCADE,
    CONSTRAINT fk_uvc_category FOREIGN KEY (video_category) REFERENCES video_category (category)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS fuzzy_word_search_index_gin    ON word_table           USING GIN (word gin_trgm_ops);
CREATE INDEX IF NOT EXISTS fuzzy_lemma_search_index_gin   ON word_table           USING GIN (lemma gin_trgm_ops);
CREATE INDEX IF NOT EXISTS wts_sentence_id_index          ON word_to_sentence     (sentence_id);
CREATE INDEX IF NOT EXISTS sentence_video_id_idx          ON sentence             (video_id);
CREATE INDEX IF NOT EXISTS idx_sentence_start_time        ON sentence             (start_time);
CREATE INDEX IF NOT EXISTS video_idx                      ON video                (video_id, language);
CREATE INDEX IF NOT EXISTS word_table_language_idx        ON word_table           (language);
CREATE INDEX IF NOT EXISTS word_table_word_id_idx         ON word_table           (word_id);
CREATE INDEX IF NOT EXISTS grammar_rule_language_idx      ON grammar_rule         (language);
CREATE INDEX IF NOT EXISTS word_strength_uid_strength_idx ON word_strength        (uid, strength);
CREATE INDEX IF NOT EXISTS leaderboard_score_idx          ON leaderboard          USING BTREE (score DESC);
CREATE INDEX IF NOT EXISTS user_learned_language_cognito  ON user_learned_language (uid);
CREATE INDEX IF NOT EXISTS user_grammar_cognito           ON user_grammar          (uid);
CREATE INDEX IF NOT EXISTS phrase_blueprint_key_idx       ON phrase_blueprint      (lookup_key);
CREATE INDEX IF NOT EXISTS stp_sentence_id_idx            ON sentence_to_phrase    (sentence_id);
