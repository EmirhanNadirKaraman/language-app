from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

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


class GuidedSessionRead(BaseModel):
    session_id: str
    session_type: str           # 'guided'
    target_item_id: int
    target_item_type: str
    target_word: str
    started_at: datetime
    opening_message: ChatMessageRead


class ChatSendMessage(BaseModel):
    content: str


class Correction(BaseModel):
    original: str
    corrected: str
    explanation: str


class SendMessageResponse(BaseModel):
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead
