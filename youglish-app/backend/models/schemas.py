from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Existing search schemas (unchanged)
# ---------------------------------------------------------------------------


class SearchResult(BaseModel):
    video_id: str
    title: str
    thumbnail_url: str
    language: str
    start_time: float
    start_time_int: int
    content: str
    surface_form: str | None
    match_type: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int


class SuggestionResult(BaseModel):
    word: str
    score: float
    type: str  # 'word' | 'phrase'


class VideoSentence(BaseModel):
    sentence_id: int
    start_time: float
    start_time_int: int
    content: str


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    user_id: str
    email: str


# ---------------------------------------------------------------------------
# Word knowledge
# ---------------------------------------------------------------------------


class WordKnowledgeRead(BaseModel):
    item_id: int
    item_type: str  # 'word' | 'phrase' | 'grammar_rule'
    status: str     # 'unknown' | 'learning' | 'known'
    passive_level: int
    active_level: int
    notes: str | None = None
    last_seen: datetime | None = None


class WordStatusUpdate(BaseModel):
    status: str  # 'unknown' | 'learning' | 'known'


# ---------------------------------------------------------------------------
# Chat (schemas only — routes/service come in a later step)
# ---------------------------------------------------------------------------


class ReadingStatsResponse(BaseModel):
    video_id: str
    total_lemmas: int
    known: int
    learning: int
    unknown: int
    known_pct: float
    learning_pct: float
    unknown_pct: float


class ChatSessionRead(BaseModel):
    session_id: str
    session_type: str  # 'free' | 'guided'
    target_item_id: int | None = None
    target_item_type: str | None = None
    started_at: datetime


class ChatMessageRead(BaseModel):
    message_id: int
    session_id: str
    role: str   # 'user' | 'assistant'
    content: str
    language_detected: str | None = None
    corrections: list[Any] | None = None
    word_matches: list[Any] | None = None
    evaluation: dict[str, Any] | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Sentence matcher
# ---------------------------------------------------------------------------


class MatchRequest(BaseModel):
    sentence: str


class MatchPhraseResult(BaseModel):
    dictionary_entry: str
    sentence_phrase: list[str]
    logic: str
    match_type: str
    indices: list[int]


class MatchResponse(BaseModel):
    sentence: str
    phrases: list[MatchPhraseResult]


# ---------------------------------------------------------------------------
# Word lookup
# ---------------------------------------------------------------------------


class WordLookupResult(BaseModel):
    word_id: int
    word: str
    lemma: str
    current_status: str | None = None
    passive_level: int = 0
    active_level: int = 0
    passive_due: datetime | None = None
    active_due: datetime | None = None


# ---------------------------------------------------------------------------
# SRS (spaced-repetition)
# ---------------------------------------------------------------------------


class CheckAnswerRequest(BaseModel):
    uid: str
    word_id: int
    correct: bool


class MagicSentencesRequest(BaseModel):
    uid: str
    word_id: int
    language: str
    full_sentence: bool
    page: int = Field(default=1, ge=1)
    rows_per_page: int = Field(default=10, ge=1, le=100)


class SentenceResult(BaseModel):
    content: str
    sentence_id: int
    video_properties: dict
    unknown_count: int


class MagicSentencesResponse(BaseModel):
    sentences: list[SentenceResult]
    total_count: int


class ClozeQuestionsRequest(BaseModel):
    uid: str
    native_language: str
    target_language: str
    is_exact: bool


class ClozeQuestionResult(BaseModel):
    word: str
    target_sentence: str
    translation: str
    removed: str
    word_id: int


# ---------------------------------------------------------------------------
# Free chat — input / output
# ---------------------------------------------------------------------------


class ChatSessionCreate(BaseModel):
    session_type: Literal["free"] = "free"


# ---------------------------------------------------------------------------
# Guided chat — input / output
# ---------------------------------------------------------------------------


class GuidedSessionCreate(BaseModel):
    language: str  # target language code, e.g. "de"


class GuidedHints(BaseModel):
    intent_hint: str   # English: what concept to express, no target word
    anchor_hint: str   # German: partial clue — related word or prefix hint
    example:     str   # Complete German sentence using the target word


class GuidedSessionRead(BaseModel):
    session_id: str
    session_type: str           # 'guided'
    target_item_id: int
    target_item_type: str
    target_word: str
    started_at: datetime
    opening_message: ChatMessageRead
    hints: GuidedHints | None = None


class ChatSendMessage(BaseModel):
    content: str


class Correction(BaseModel):
    original: str
    corrected: str
    explanation: str


class SendMessageResponse(BaseModel):
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class ItemFrequency(BaseModel):
    item_id: int
    item_type: str
    word: str | None = None
    event_count: int


class FailedItemStats(BaseModel):
    item_id: int
    item_type: str
    word: str | None = None
    fail_count: int
    last_failed: datetime


class InteractedItemStats(BaseModel):
    item_id: int
    item_type: str
    word: str | None = None
    total_interactions: int
    last_seen: datetime


# ---------------------------------------------------------------------------
# Playlist generation
# ---------------------------------------------------------------------------


class PlaylistGenerateRequest(BaseModel):
    item_ids: list[int] = Field(..., min_length=1, max_length=200)
    item_type: Literal["word"] = "word"   # extend to "phrase" when supported
    language: str
    max_videos: int = Field(default=10, ge=1, le=50)
    # algorithm: Literal["greedy"] = "greedy"   # add "ilp" here when implemented


class PlaylistVideoEntry(BaseModel):
    video_id: str
    title: str
    thumbnail_url: str
    language: str
    start_time: float
    start_time_int: int
    content: str
    covered_item_ids: list[int]
    covered_count: int


class PlaylistCoverage(BaseModel):
    target_count: int
    covered_count: int
    coverage_pct: float
    uncovered_item_ids: list[int]
    video_count: int


class PlaylistResult(BaseModel):
    videos: list[PlaylistVideoEntry]
    coverage: PlaylistCoverage


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class SentenceRecommendation(BaseModel):
    sentence_id: int
    content: str
    video_id: str
    video_title: str
    thumbnail_url: str
    start_time: float
    start_time_int: int
    unknown_count: int
    due_count: int       # SRS passive cards due in this sentence
    priority_count: int  # high-frequency unknown items present
    score: float


class SentenceRecommendationsResponse(BaseModel):
    sentences: list[SentenceRecommendation]
    target_unknown: int
    total: int


class VideoRecommendation(BaseModel):
    video_id: str
    title: str
    thumbnail_url: str
    language: str
    duration: float
    start_time: float
    start_time_int: int
    priority_score: float    # sum of prioritization scores for covered items
    covered_item_ids: list[int]
    covered_count: int
    score: float


class VideoRecommendationsResponse(BaseModel):
    videos: list[VideoRecommendation]
    target_item_count: int    # total prioritized items used as ranking targets
    reason: str | None = None  # e.g. "no_target_items" for new users


class PrioritizedItemRead(BaseModel):
    """
    Not yet exposed via API endpoint — schema added now so the future
    GET /api/v1/recommendations/items endpoint is one thin router file away.
    signals dict is intentionally omitted from the API model (internal only).
    """
    item_id:   int
    item_type: str
    score:     float
    reasons:   list[str]


class ItemRecommendation(BaseModel):
    item_id:        int
    item_type:      str            # 'word' | 'phrase' | 'grammar_rule'
    score:          float
    display_text:   str
    secondary_text: str | None = None
    current_status: str | None = None   # None = no knowledge row yet
    passive_level:  int = 0
    active_level:   int = 0
    due_date:       datetime | None = None
    signals:        dict[str, float]    # is_due, mistake_recency, freq_rank, is_learning
    reasons:        list[str]           # from explain_signals()


class ItemRecommendationsResponse(BaseModel):
    items:     list[ItemRecommendation]
    item_type: str
    language:  str
    total:     int


# ---------------------------------------------------------------------------
# Settings / preferences
# ---------------------------------------------------------------------------

import re as _re


def _hex_color(v: object) -> object:
    """Validator: accept None (optional field) or a 6-digit hex color string."""
    if v is not None and not _re.match(r'^#[0-9a-fA-F]{6}$', str(v)):
        raise ValueError('must be a 6-digit hex color, e.g. "#388e3c"')
    return v


class UserPreferences(BaseModel):
    liked_genres:           list[str] = []
    liked_channels:         list[str] = []
    passive_reps_for_known: int       = 3
    active_reps_for_known:  int       = 5
    known_word_color:       str       = "#388e3c"
    learning_word_color:    str       = "#f57c00"
    unknown_word_color:     str       = "#d32f2f"


class UserPreferencesUpdate(BaseModel):
    """
    All fields are optional — absent fields keep their current stored value.
    This gives PATCH-style merge semantics while using a PUT endpoint.
    """
    liked_genres:           list[str] | None = None
    liked_channels:         list[str] | None = None
    passive_reps_for_known: int | None = Field(default=None, ge=1, le=20)
    active_reps_for_known:  int | None = Field(default=None, ge=1, le=20)
    known_word_color:       str | None = None
    learning_word_color:    str | None = None
    unknown_word_color:     str | None = None

    @field_validator("known_word_color", "learning_word_color", "unknown_word_color", mode="before")
    @classmethod
    def validate_hex_color(cls, v: object) -> object:
        return _hex_color(v)
