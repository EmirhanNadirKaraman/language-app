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

export interface WordLookupResult {
  word_id: number;
  word: string;
  lemma: string;
  current_status: string | null;
}

export interface Correction {
  original: string;
  corrected: string;
  explanation: string;
}

export interface GuidedEvaluation {
  target_used: boolean;
  target_counted: boolean;
  feedback_short: string;
  naturalness: 'high' | 'medium' | 'low';
}

export interface ChatMessage {
  message_id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  language_detected: string | null;
  corrections: Correction[] | null;
  word_matches: unknown[] | null;
  evaluation: GuidedEvaluation | null;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  session_type: string;
  target_item_id: number | null;
  target_item_type: string | null;
  started_at: string;
}

export interface GuidedSession {
  session_id: string;
  session_type: 'guided';
  target_item_id: number;
  target_item_type: string;
  target_word: string;
  started_at: string;
  opening_message: ChatMessage;
}
