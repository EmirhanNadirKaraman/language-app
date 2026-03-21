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
  passive_level: number;
  active_level: number;
  passive_due: string | null;
  active_due: string | null;
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

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------

export interface VideoRecommendation {
  video_id: string;
  title: string;
  thumbnail_url: string;
  language: string;
  duration: number;
  start_time: number;
  start_time_int: number;
  priority_score: number;
  covered_item_ids: number[];
  covered_count: number;
  score: number;
}

export interface SentenceRecommendation {
  sentence_id: number;
  content: string;
  video_id: string;
  video_title: string;
  thumbnail_url: string;
  start_time: number;
  start_time_int: number;
  unknown_count: number;
  due_count: number;
  priority_count: number;
  score: number;
}

export interface VideoRecommendationsResponse {
  videos: VideoRecommendation[];
  target_item_count: number;
  reason: string | null;
}

export interface SentenceRecommendationsResponse {
  sentences: SentenceRecommendation[];
  target_unknown: number;
  total: number;
}

export interface ItemSignals {
  is_due: number;
  mistake_recency: number;
  freq_rank: number;
  is_learning: number;
}

export interface ItemRecommendation {
  item_id: number;
  item_type: 'word' | 'phrase' | 'grammar_rule';
  score: number;
  display_text: string;
  secondary_text: string | null;
  current_status: 'unknown' | 'learning' | 'known' | null;
  passive_level: number;
  active_level: number;
  due_date: string | null;
  signals: ItemSignals;
  reasons: string[];
}

export interface ItemRecommendationsResponse {
  items: ItemRecommendation[];
  item_type: string;
  language: string;
  total: number;
}

// ---------------------------------------------------------------------------
// Playlist
// ---------------------------------------------------------------------------

export interface PlaylistVideo {
  video_id: string;
  title: string;
  thumbnail_url: string;
  language: string;
  start_time: number;
  start_time_int: number;
  content: string;
  covered_item_ids: number[];
  covered_count: number;
}

export interface PlaylistCoverageStats {
  target_count: number;
  covered_count: number;
  coverage_pct: number;
  uncovered_item_ids: number[];
  video_count: number;
}

export interface PlaylistResult {
  videos: PlaylistVideo[];
  coverage: PlaylistCoverageStats;
}

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

export interface InsightSignals {
  is_due: number;
  mistake_recency: number;
  freq_rank: number;
  is_learning: number;
}

export interface InsightItem {
  item_id: number;
  item_type: 'word' | 'phrase';
  display_text: string;
  secondary_text: string | null;
  score: number;
  reasons: string[];
  signals: InsightSignals;
  extra: Record<string, unknown>;
}

export interface InsightCard {
  card_type: 'frequent_unknowns' | 'recent_mistakes';
  title: string;
  explanation: string;
  items: InsightItem[];
}

export interface InsightCardsResponse {
  cards: InsightCard[];
  language: string;
}

export interface PrepViewData {
  item_id: number;
  item_type: string;
  display_text: string;
  translation: string;
  grammar_structure: string | null;
  grammar_explanation: string;
  example: string | null;
  templates: string[];
  has_examples: boolean;
}

export interface GenerateExamplesResponse {
  example: string;
  templates: string[];
}

export interface GuidedHints {
  intent_hint: string;
  anchor_hint: string;
  example: string;
}

export interface GuidedSession {
  session_id: string;
  session_type: 'guided';
  target_item_id: number;
  target_item_type: string;
  target_word: string;
  started_at: string;
  opening_message: ChatMessage;
  hints: GuidedHints | null;
}

export interface GuidedSessionSummary {
  session_id: string;
  target_word: string;
  target_item_id: number;
  target_item_type: string;
  // Deterministic signals
  target_used: boolean;
  target_counted: boolean;
  target_counted_count: number;
  total_turns: number;
  hint_level: number;
  sentence_quality: 'excellent' | 'good' | 'needs_work';
  // LLM feedback (empty string = nothing to show)
  what_went_well: string;
  what_to_improve: string;
  corrective_note: string;
}
