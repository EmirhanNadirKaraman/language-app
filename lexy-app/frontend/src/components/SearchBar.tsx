import { useEffect, useRef, useState, useCallback } from 'react';
import { fetchSuggestions } from '../api/suggest';
import type { Suggestion } from '../types';
import { DEFAULT_LANGUAGE, hasPhraseSupport, type SuggestKind } from '../config/languages';

interface Props {
  terms: string[];
  onAddTerm: (word: string) => void;
  onRemoveTerm: (index: number) => void;
  loading: boolean;
  // Active learning language. Threaded into the suggestions request so a
  // user on Spanish gets Spanish suggestions instead of German (Stage 2
  // of the second-language plan). Falls back to DEFAULT_LANGUAGE so
  // pre-Stage-2 callers / tests that omit the prop keep working.
  language?: string;
}

const SUGGEST_KIND_OPTIONS: { value: SuggestKind; label: string }[] = [
  { value: 'words',   label: 'Words' },
  { value: 'phrases', label: 'Phrases' },
  { value: 'both',    label: 'Both' },
];

export function SearchBar({
  terms, onAddTerm, onRemoveTerm, loading, language,
}: Props) {
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  // User-selected suggestion source. Only meaningful (and only shown) for
  // languages with a phrase source — German today. Default 'both' so German
  // keeps phrase suggestions; for word-only languages the effective kind is
  // forced to 'words' below regardless of this state.
  const [kind, setKind] = useState<SuggestKind>('both');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const phraseCapable = hasPhraseSupport(language);
  const effectiveKind: SuggestKind = phraseCapable ? kind : 'words';

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!input.trim()) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }

    // Show the typed word immediately while we wait for phrase suggestions
    setSuggestions([{ word: input.trim(), score: 1, type: 'word' }]);
    setShowDropdown(true);

    debounceRef.current = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const data = await fetchSuggestions(
          input.trim(), language || DEFAULT_LANGUAGE, controller.signal, effectiveKind,
        );
        const wordSuggestion: Suggestion = { word: input.trim(), score: 1, type: 'word' };
        const rest = data.filter(s => s.word !== input.trim());
        setSuggestions([wordSuggestion, ...rest]);
        setShowDropdown(true);
        setActiveIdx(-1);
      } catch {
        // AbortError or network error — ignore
      }
    }, 250);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [input, language, effectiveKind]);

  const selectSuggestion = useCallback((word: string) => {
    onAddTerm(word);
    setInput('');
    setSuggestions([]);
    setShowDropdown(false);
    setActiveIdx(-1);
    inputRef.current?.focus();
  }, [onAddTerm]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx(i => Math.max(i - 1, -1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIdx >= 0 && suggestions[activeIdx]) {
        selectSuggestion(suggestions[activeIdx].word);
      } else if (input.trim()) {
        onAddTerm(input.trim());
        setInput('');
        setSuggestions([]);
        setShowDropdown(false);
      }
    } else if (e.key === 'Backspace' && !input && terms.length > 0) {
      onRemoveTerm(terms.length - 1);
    } else if (e.key === 'Escape') {
      setShowDropdown(false);
    }
  };

  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
      {phraseCapable && (
        <div
          role="group"
          aria-label="Suggestion type"
          data-testid="suggest-kind"
          style={{ display: 'inline-flex', borderRadius: '6px', overflow: 'hidden', border: '1px solid var(--color-input-border)', flexShrink: 0 }}
        >
          {SUGGEST_KIND_OPTIONS.map(opt => {
            const active = kind === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setKind(opt.value)}
                aria-pressed={active}
                data-testid={`suggest-kind-${opt.value}`}
                style={{
                  minHeight: '42px',
                  padding: '0 12px',
                  border: 'none',
                  borderLeft: opt.value !== 'words' ? '1px solid var(--color-input-border)' : 'none',
                  background: active ? 'var(--color-primary-soft)' : 'var(--color-surface)',
                  color: active ? 'var(--color-primary-on-soft)' : 'var(--color-text-muted)',
                  fontSize: '13px',
                  fontWeight: active ? 700 : 400,
                  cursor: 'pointer',
                  touchAction: 'manipulation',
                }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}
      <div style={{ position: 'relative', flex: 1, minWidth: '200px' }}>
        <div
          onClick={() => inputRef.current?.focus()}
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            alignItems: 'center',
            padding: '6px 36px 6px 8px',
            border: '1px solid var(--color-input-border)',
            borderRadius: '4px',
            minHeight: '42px',
            cursor: 'text',
            background: 'var(--color-input-bg)',
            boxSizing: 'border-box',
            width: '100%',
          }}
        >
          {terms.map((term, i) => (
            <span
              key={i}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--color-primary-soft)',
                border: '1px solid var(--color-border-accent)',
                borderRadius: '4px',
                padding: '2px 6px',
                fontSize: '14px',
                color: 'var(--color-primary-on-soft)',
                gap: '4px',
              }}
            >
              {term}
              <button
                onClick={(e) => { e.stopPropagation(); onRemoveTerm(i); }}
                aria-label={`Remove search term ${term}`}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', fontSize: '14px', color: 'var(--color-text-muted)', lineHeight: 1, touchAction: 'manipulation' }}
              >
                ×
              </button>
            </span>
          ))}
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
            onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
            placeholder={terms.length === 0 ? 'Search for words...' : ''}
            aria-label="Search vocabulary"
            style={{
              border: 'none',
              outline: 'none',
              flex: 1,
              minWidth: '120px',
              fontSize: '16px',
              padding: '2px 4px',
              background: 'transparent',
              color: 'var(--color-text)',
            }}
          />
        </div>

        {loading && (
          <span style={{ position: 'absolute', right: '10px', top: '13px', fontSize: '12px', color: 'var(--color-text-muted)' }}>
            ⏳
          </span>
        )}

        {showDropdown && (
          <ul style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-input-border)',
            borderTop: 'none',
            borderRadius: '0 0 4px 4px',
            margin: 0,
            padding: 0,
            listStyle: 'none',
            zIndex: 100,
            maxHeight: '200px',
            overflowY: 'auto',
            boxShadow: 'var(--shadow-card)',
          }}>
            {suggestions.map((s, i) => (
              <li
                key={s.word}
                onMouseDown={() => selectSuggestion(s.word)}
                onMouseEnter={() => setActiveIdx(i)}
                style={{
                  padding: '12px',
                  cursor: 'pointer',
                  fontSize: '15px',
                  background: i === activeIdx ? 'var(--color-primary-soft)' : 'var(--color-surface)',
                  color: 'var(--color-text)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>{s.word}</span>
                <span style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                  {s.type === 'phrase' && s.word.includes(' ') && (
                    <span style={{ fontSize: '10px', background: 'var(--color-warning-bg)', color: 'var(--color-warning)', borderRadius: '3px', padding: '1px 4px' }}>phrase</span>
                  )}
                  <span style={{ fontSize: '11px', color: 'var(--color-text-subtle)' }}>{Math.round(s.score * 100)}%</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

    </div>
  );
}
