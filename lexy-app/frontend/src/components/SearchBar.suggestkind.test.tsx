// TODO #38 follow-up — user-selectable suggestion kind (words/phrases/both).
//
// The selector only shows for languages with a phrase source (German today,
// via config/languages.hasPhraseSupport). For word-only languages the
// control is hidden and the request is forced to kind='words'.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SearchBar } from './SearchBar';
import * as suggestApi from '../api/suggest';

beforeEach(() => {
  vi.spyOn(suggestApi, 'fetchSuggestions').mockResolvedValue([]);
});
afterEach(() => {
  vi.restoreAllMocks();
});

function kindArg(call: unknown[]): unknown {
  // fetchSuggestions(query, language, signal, kind)
  return call[3];
}

describe('SearchBar suggestion-kind selector', () => {
  it('shows the selector for a phrase-capable language (de)', () => {
    render(<SearchBar terms={[]} onAddTerm={() => {}} onRemoveTerm={() => {}} loading={false} language="de" />);
    expect(screen.getByTestId('suggest-kind')).toBeInTheDocument();
    expect(screen.getByTestId('suggest-kind-words')).toBeInTheDocument();
    expect(screen.getByTestId('suggest-kind-phrases')).toBeInTheDocument();
    expect(screen.getByTestId('suggest-kind-both')).toBeInTheDocument();
  });

  it('hides the selector for a word-only language (es)', () => {
    render(<SearchBar terms={[]} onAddTerm={() => {}} onRemoveTerm={() => {}} loading={false} language="es" />);
    expect(screen.queryByTestId('suggest-kind')).not.toBeInTheDocument();
  });

  it('defaults German to kind="both" in the request', async () => {
    render(<SearchBar terms={[]} onAddTerm={() => {}} onRemoveTerm={() => {}} loading={false} language="de" />);
    fireEvent.change(screen.getByRole('textbox', { name: /search vocabulary/i }), { target: { value: 'geb' } });
    await waitFor(() => expect(suggestApi.fetchSuggestions).toHaveBeenCalled(), { timeout: 1500 });
    expect(kindArg((suggestApi.fetchSuggestions as ReturnType<typeof vi.fn>).mock.calls.at(-1)!)).toBe('both');
  });

  it('selecting Phrases sends kind="phrases"', async () => {
    render(<SearchBar terms={[]} onAddTerm={() => {}} onRemoveTerm={() => {}} loading={false} language="de" />);
    fireEvent.click(screen.getByTestId('suggest-kind-phrases'));
    fireEvent.change(screen.getByRole('textbox', { name: /search vocabulary/i }), { target: { value: 'geben' } });
    await waitFor(() => expect(suggestApi.fetchSuggestions).toHaveBeenCalled(), { timeout: 1500 });
    expect(kindArg((suggestApi.fetchSuggestions as ReturnType<typeof vi.fn>).mock.calls.at(-1)!)).toBe('phrases');
  });

  it('word-only language forces kind="words" in the request', async () => {
    render(<SearchBar terms={[]} onAddTerm={() => {}} onRemoveTerm={() => {}} loading={false} language="es" />);
    fireEvent.change(screen.getByRole('textbox', { name: /search vocabulary/i }), { target: { value: 'univ' } });
    await waitFor(() => expect(suggestApi.fetchSuggestions).toHaveBeenCalled(), { timeout: 1500 });
    expect(kindArg((suggestApi.fetchSuggestions as ReturnType<typeof vi.fn>).mock.calls.at(-1)!)).toBe('words');
  });
});
