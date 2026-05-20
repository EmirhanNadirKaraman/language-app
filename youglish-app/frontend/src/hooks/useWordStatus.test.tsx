import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useWordStatus } from './useWordStatus';
import * as wordsApi from '../api/words';
import type { WordLookupResult } from '../types';

// Helper: build a 'single' lookup response wrapping a partial WordLookupResult.
function single(item: Partial<WordLookupResult>) {
    const fullItem = {
        word_id: 42, word: 'Auto', lemma: 'Auto',
        pos: 'NOUN', current_status: 'unknown',
        passive_level: 0, active_level: 0,
        passive_due: null, active_due: null,
        ...item,
    };
    return { status: 'single' as const, item: fullItem, candidates: [fullItem] };
}

function notFound() {
    return { status: 'not_found' as const, item: null, candidates: [] };
}

describe('useWordStatus.selectWord — transcript click', () => {
    beforeEach(() => { vi.restoreAllMocks(); });
    afterEach(() => { vi.restoreAllMocks(); });

    it('fires recordTranscriptClick with sentence_id when a word is selected', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(single({ word_id: 42 }) as never);
        const record = vi.spyOn(wordsApi, 'recordTranscriptClick').mockResolvedValue();

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Auto', 7); });

        expect(record).toHaveBeenCalledTimes(1);
        expect(record).toHaveBeenCalledWith('tok', 42, 7);
    });

    it('passes undefined sentence_id when caller omits it', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(single({ word_id: 42 }) as never);
        const record = vi.spyOn(wordsApi, 'recordTranscriptClick').mockResolvedValue();

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Auto'); });

        expect(record).toHaveBeenCalledWith('tok', 42, undefined);
    });

    it('surfaces a recordTranscriptClick failure via console.warn but does not throw', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(single({ word_id: 42 }) as never);
        vi.spyOn(wordsApi, 'recordTranscriptClick').mockRejectedValue(new Error('500'));
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Auto', 7); });

        await waitFor(() => {
            expect(result.current.selected).toBe('Auto');
            expect(result.current.state.lookup?.word_id).toBe(42);
        });
        await waitFor(() => {
            expect(warn).toHaveBeenCalledWith('recordTranscriptClick failed', expect.any(Error));
        });
    });

    it('skips recordTranscriptClick when lookupWord returns not_found', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(notFound() as never);
        const record = vi.spyOn(wordsApi, 'recordTranscriptClick').mockResolvedValue();

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Unbekannt', 7); });

        expect(record).not.toHaveBeenCalled();
    });
});

describe('useWordStatus.learnAnyway (W2 / Hole 1)', () => {
    beforeEach(() => { vi.restoreAllMocks(); });
    afterEach(() => { vi.restoreAllMocks(); });

    it('calls learnWordAnyway and flips lookup to learning on success', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(notFound() as never);
        const learn = vi.spyOn(wordsApi, 'learnWordAnyway').mockResolvedValue({
            word_id: 99, word: 'Unbekannt', lemma: 'Unbekannt',
            current_status: 'learning', passive_level: 0, active_level: 0,
        } as never);

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Unbekannt'); });
        await act(async () => { await result.current.learnAnyway(); });

        expect(learn).toHaveBeenCalledWith('tok', 'Unbekannt', 'de');
        expect(result.current.state.lookup?.current_status).toBe('learning');
        expect(result.current.state.lookup?.word_id).toBe(99);
        expect(result.current.state.learnAnywayError).toBeNull();
    });

    it('surfaces an error in state when the API rejects', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(notFound() as never);
        vi.spyOn(wordsApi, 'learnWordAnyway').mockRejectedValue(new Error('Network down'));

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Unbekannt'); });
        await act(async () => { await result.current.learnAnyway(); });

        expect(result.current.state.lookup).toBeNull();
        expect(result.current.state.learnAnywayError).toBe('Network down');
        expect(result.current.state.saving).toBe(false);
    });

    it('no-ops when no word is currently selected', async () => {
        const learn = vi.spyOn(wordsApi, 'learnWordAnyway').mockResolvedValue({
            word_id: 1, word: '', lemma: '', current_status: 'learning',
            passive_level: 0, active_level: 0,
        } as never);

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.learnAnyway(); });

        expect(learn).not.toHaveBeenCalled();
    });
});

describe('useWordStatus.selectCandidate (W3 / Hole 2 disambiguation)', () => {
    beforeEach(() => { vi.restoreAllMocks(); });
    afterEach(() => { vi.restoreAllMocks(); });

    function ambiguous(...items: Array<Partial<{ word_id: number; word: string; lemma: string; pos: string }>>) {
        const fulls = items.map(it => ({
            word_id: 0, word: 'Bank', lemma: 'Bank', pos: 'NOUN',
            current_status: null, passive_level: 0, active_level: 0,
            passive_due: null, active_due: null,
            ...it,
        }));
        return { status: 'ambiguous' as const, item: null, candidates: fulls };
    }

    it('populates candidates and does NOT call transcript-click on ambiguous lookup', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(
            ambiguous({ word_id: 1, lemma: 'Bank' }, { word_id: 2, lemma: 'Bank' }) as never,
        );
        const record = vi.spyOn(wordsApi, 'recordTranscriptClick').mockResolvedValue();

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Bank', 99); });

        expect(result.current.state.candidates).toHaveLength(2);
        expect(result.current.state.lookup).toBeNull();
        expect(record).not.toHaveBeenCalled();
    });

    it('selectCandidate flips lookup to the chosen item and fires deferred transcript-click', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(
            ambiguous({ word_id: 1 }, { word_id: 2 }) as never,
        );
        const record = vi.spyOn(wordsApi, 'recordTranscriptClick').mockResolvedValue();

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Bank', 99); });
        await act(async () => {
            result.current.selectCandidate(result.current.state.candidates[1]);
        });

        expect(result.current.state.lookup?.word_id).toBe(2);
        expect(result.current.state.candidates).toEqual([]);
        // Deferred click fires NOW with the chosen word_id + originally-stashed sentence_id.
        expect(record).toHaveBeenCalledTimes(1);
        expect(record).toHaveBeenCalledWith('tok', 2, 99);
    });

    it('dismiss clears candidates and pending sentence_id', async () => {
        vi.spyOn(wordsApi, 'lookupWord').mockResolvedValue(
            ambiguous({ word_id: 1 }, { word_id: 2 }) as never,
        );
        const record = vi.spyOn(wordsApi, 'recordTranscriptClick').mockResolvedValue();

        const { result } = renderHook(() => useWordStatus('tok', 'de'));
        await act(async () => { await result.current.selectWord('Bank', 99); });
        await act(async () => { result.current.dismiss(); });

        expect(result.current.state.candidates).toEqual([]);
        expect(result.current.state.lookup).toBeNull();
        expect(record).not.toHaveBeenCalled();
    });
});
