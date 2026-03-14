from pydantic import BaseModel


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
