// Stage 2 of second-language plan (2026-05-21).
//
// Pins the four user-visible language generalisations:
//   - SearchBar suggestions request honours the `language` prop.
//   - SearchBar falls back to DEFAULT_LANGUAGE when the prop is omitted
//     (so the legacy single-language call site keeps working).
//   - BookLibraryPage defaults its upload language to `defaultLanguage`
//     when supplied.
//   - SRSReviewPage active-input placeholder is language-neutral
//     ("Type the answer", not "Type the German answer").
//   - The shared LANGUAGE_OPTIONS list contains both 'de' and 'es'.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SearchBar } from '../components/SearchBar';
import { SRSReviewPage } from '../components/SRSReviewPage';
import { BookLibraryPage } from '../components/BookLibraryPage';
import { LANGUAGE_OPTIONS, languageLabel } from '../config/languages';
import * as suggestApi from '../api/suggest';
import * as booksApi from '../api/books';
import * as srsApi from '../api/srs';


// ---------------------------------------------------------------------------
// Shared config
// ---------------------------------------------------------------------------

describe('config/languages', () => {
  it('contains both de and es', () => {
    const codes = LANGUAGE_OPTIONS.map(l => l.code);
    expect(codes).toContain('de');
    expect(codes).toContain('es');
  });

  it('languageLabel maps known codes to display labels', () => {
    expect(languageLabel('de')).toBe('German');
    expect(languageLabel('es')).toBe('Spanish');
  });

  it('languageLabel falls back to upper-cased code for unknowns', () => {
    expect(languageLabel('xx')).toBe('XX');
  });

  it('languageLabel returns empty string for null/undefined', () => {
    expect(languageLabel(null)).toBe('');
    expect(languageLabel(undefined)).toBe('');
  });
});


// ---------------------------------------------------------------------------
// SearchBar — language threading
// ---------------------------------------------------------------------------

describe('SearchBar — language prop', () => {
  beforeEach(() => {
    vi.spyOn(suggestApi, 'fetchSuggestions').mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // SearchBar debounces fetchSuggestions for 250ms. Real timers + waitFor
  // (with a 1500ms cap) keeps the test stable without mocking timers, which
  // doesn't play well with React 19's effect scheduling here.

  it('passes language="es" to fetchSuggestions when provided', async () => {
    render(
      <SearchBar
        terms={[]}
        onAddTerm={() => {}}
        onRemoveTerm={() => {}}
        loading={false}
        language="es"
      />
    );

    const input = screen.getByRole('textbox', { name: /search vocabulary/i });
    fireEvent.change(input, { target: { value: 'hola' } });

    await waitFor(
      () => {
        expect(suggestApi.fetchSuggestions).toHaveBeenCalled();
      },
      { timeout: 1500 },
    );
    const [, lang] = (suggestApi.fetchSuggestions as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(lang).toBe('es');
  });

  it('falls back to "de" when language prop is omitted (back-compat)', async () => {
    render(
      <SearchBar
        terms={[]}
        onAddTerm={() => {}}
        onRemoveTerm={() => {}}
        loading={false}
      />
    );

    const input = screen.getByRole('textbox', { name: /search vocabulary/i });
    fireEvent.change(input, { target: { value: 'hallo' } });

    await waitFor(
      () => {
        expect(suggestApi.fetchSuggestions).toHaveBeenCalled();
      },
      { timeout: 1500 },
    );
    const [, lang] = (suggestApi.fetchSuggestions as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(lang).toBe('de');
  });
});


// ---------------------------------------------------------------------------
// BookLibraryPage — default upload language
// ---------------------------------------------------------------------------

describe('BookLibraryPage — defaultLanguage prop', () => {
  beforeEach(() => {
    vi.spyOn(booksApi, 'listBooks').mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults the upload language <select> to defaultLanguage='es'", async () => {
    render(
      <BookLibraryPage
        token="tok"
        onOpen={() => {}}
        onClose={() => {}}
        defaultLanguage="es"
      />
    );
    // The library renders the upload form synchronously alongside the
    // book list. The language select carries data-testid="book-upload-language".
    const select = await screen.findByTestId('book-upload-language') as HTMLSelectElement;
    expect(select.value).toBe('es');
  });

  it("falls back to 'de' when defaultLanguage is not provided", async () => {
    render(
      <BookLibraryPage
        token="tok"
        onOpen={() => {}}
        onClose={() => {}}
      />
    );
    const select = await screen.findByTestId('book-upload-language') as HTMLSelectElement;
    expect(select.value).toBe('de');
  });
});


// ---------------------------------------------------------------------------
// SRSReviewPage — language-neutral placeholder
// ---------------------------------------------------------------------------

describe('SRSReviewPage — placeholder is language-neutral', () => {
  beforeEach(() => {
    vi.spyOn(srsApi, 'getDueCards').mockResolvedValue([
      {
        card_id: 1,
        item_id: 10,
        item_type: 'word',
        direction: 'active',
        due_date: '2026-05-21T00:00:00Z',
        repetitions: 0,
        passive_level: 0,
        active_level: 0,
        display_text: 'hola',
        prompt_text: 'hello',
        answer_text: 'hola',
      },
    ] as unknown as ReturnType<typeof srsApi.getDueCards> extends Promise<infer T> ? T : never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the active input with "Type the answer" (no German)', async () => {
    render(
      <SRSReviewPage
        token="tok"
        language="es"
        onLanguageChange={() => {}}
        onClose={() => {}}
      />
    );

    const input = await screen.findByTestId('srs-active-input') as HTMLInputElement;
    expect(input.placeholder).toBe('Type the answer');
    expect(input.placeholder).not.toMatch(/german/i);
  });
});
