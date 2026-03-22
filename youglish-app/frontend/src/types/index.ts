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
  channel_id:   string | null;
  channel_name: string | null;
  genre:        string | null;
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

export interface FollowedChannelVideosResponse {
  videos: VideoRecommendation[];
  total: number;
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

export interface GrammarRuleRef {
  rule_id: number;
  slug: string;
  title: string;
  rule_type: string;
  short_explanation: string;
  pattern_hint: string | null;
}

export interface GrammarRuleDetail extends GrammarRuleRef {
  long_explanation: string | null;  // null = not yet generated
}

export interface GrammarRuleExplainResponse {
  slug: string;
  long_explanation: string;
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
  linked_grammar_rules: GrammarRuleRef[];
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

// ---------------------------------------------------------------------------
// Book reading mode
// ---------------------------------------------------------------------------

export type BookStatus = 'pending' | 'processing' | 'ready' | 'error';
export type BlockType = 'text' | 'ignored';
export type CorrectionStatus = 'none' | 'suggested' | 'approved' | 'rejected';
export type SourceType = 'pdf_text' | 'pdf_scan' | 'mixed' | 'unknown';

export interface BookDocument {
  doc_id: string;
  user_id: string;
  title: string;
  filename: string;
  total_pages: number | null;
  language: string;
  source_type: SourceType;
  status: BookStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface BookPageSummary {
  page_id: number;
  page_number: number;
  is_scanned: boolean;
  has_image: boolean;
  block_count: number;
}

export interface BookBlock {
  block_id: number;
  block_index: number;
  block_type: BlockType;
  bbox_x0: number | null;
  bbox_y0: number | null;
  bbox_x1: number | null;
  bbox_y1: number | null;
  ocr_text: string | null;
  clean_text: string | null;
  corrected_text: string | null;
  correction_status: CorrectionStatus;
  ocr_confidence: number | null;
  is_header_footer: boolean;
  user_text_override: string | null;
  display_text: string;
}

export interface BookPageDetail {
  page_id: number;
  page_number: number;
  is_scanned: boolean;
  has_image: boolean;
  width_pt: number | null;
  height_pt: number | null;
  blocks: BookBlock[];
}

export interface LLMRepairResponse {
  block_id: number;
  ocr_text: string | null;
  corrected_text: string;
  correction_status: CorrectionStatus;
}

// ---------------------------------------------------------------------------
// Interactive reading — selections (custom learning units)
// ---------------------------------------------------------------------------

export interface ReadingSelectionAnchor {
  block_id: number;
  token_index: number;
  surface: string;
}

export interface ReadingSelection {
  selection_id: string;
  doc_id: string;
  canonical: string;
  surface_text: string;
  sentence_text: string;
  anchors: ReadingSelectionAnchor[];
  note: string | null;
  status: string;
  review_count: number;
  next_review_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// SRS review
// ---------------------------------------------------------------------------

export interface SRSReviewCard {
  card_id: number;
  item_id: number;
  item_type: 'word' | 'phrase' | 'grammar_rule';
  direction: 'passive' | 'active';
  due_date: string;
  repetitions: number;
  passive_level: number;
  active_level: number;
  display_text: string;
}

export interface DueSelectionItem {
  selection_id: string;
  doc_id: string;
  doc_title: string;
  canonical: string;
  surface_text: string;
  sentence_text: string;
  note: string | null;
  review_count: number;
  next_review_at: string | null;
  created_at: string;
}
