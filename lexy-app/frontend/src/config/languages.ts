// Shared language-selection config (Stage 2 of the second-language plan).
//
// Pre-Stage-2, SRSReviewPage / RecommendationsPanel / PlaylistPanel each
// carried an identical 12-entry LANGUAGES array, and BookLibraryPage had a
// parallel LANG_LABELS map. Adding a language meant editing four files.
//
// Single source of truth now: LANGUAGE_OPTIONS for `<select>` rendering,
// LANGUAGE_LABELS for code → display lookups, languageLabel() for the
// safe variant that falls back to the upper-case code on unknown inputs.
//
// Order matches the pre-Stage-2 components (German first as the current
// production target). DEFAULT_LANGUAGE is intentionally kept as 'de' for
// backward compatibility — anywhere that hardcoded 'de' as a fallback
// should now import this constant instead of inlining the string.

export interface LanguageOption {
  code: string;
  label: string;
}

export const LANGUAGE_OPTIONS: readonly LanguageOption[] = [
  { code: 'de', label: 'German' },
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'French' },
  { code: 'es', label: 'Spanish' },
  { code: 'it', label: 'Italian' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ru', label: 'Russian' },
  { code: 'ko', label: 'Korean' },
  { code: 'tr', label: 'Turkish' },
  { code: 'pl', label: 'Polish' },
  { code: 'sv', label: 'Swedish' },
] as const;

export const LANGUAGE_LABELS: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(LANGUAGE_OPTIONS.map(l => [l.code, l.label])),
);

export const DEFAULT_LANGUAGE = 'de';

/**
 * Display-friendly label for a language code. Falls back to the upper-cased
 * code when the language is unknown (e.g. 'xx' → 'XX') so the UI never shows
 * a blank string for content the scraper might have indexed under a language
 * not in our list.
 */
export function languageLabel(code: string | null | undefined): string {
  if (!code) return '';
  return LANGUAGE_LABELS[code] ?? code.toUpperCase();
}
