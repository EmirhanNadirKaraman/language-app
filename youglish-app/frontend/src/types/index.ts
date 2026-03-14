export interface SearchResult {
  video_id: string;
  title: string;
  thumbnail_url: string;
  language: string;
  start_time: number;
  start_time_int: number;
  content: string;
  surface_form: string | null;
  match_type: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
}

export interface Suggestion {
  word: string;
  score: number;
  type: 'word' | 'phrase';
}

export interface VideoSentence {
  sentence_id: number;
  start_time: number;
  start_time_int: number;
  content: string;
}
