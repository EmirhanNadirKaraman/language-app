import { useCallback, useRef, useState } from 'react';
import * as wordsApi from '../api/words';
import type { WordLookupResult } from '../types';

interface State {
    lookup: WordLookupResult | null;
    // W3 (Hole 2): populated when /by-text returns status='ambiguous'.
    // Picker shows a candidate chooser; selecting one promotes it to
    // `lookup` and clears `candidates`. Empty array otherwise.
    candidates: WordLookupResult[];
    loading: boolean;
    saving: boolean;
    learnAnywayError: string | null;
}

const IDLE: State = {
    lookup: null,
    candidates: [],
    loading: false,
    saving: false,
    learnAnywayError: null,
};

export function useWordStatus(token: string | null, language: string) {
    const [selected, setSelected] = useState<string | null>(null);
    const [state, setState] = useState<State>(IDLE);
    const [refreshKey, setRefreshKey] = useState(0);
    // W3: stash the sentence_id from selectWord so we can fire transcript-click
    // AFTER the user picks an ambiguous candidate (not before, otherwise we'd
    // record exposure against an arbitrary word_id). Cleared when the picker
    // dismisses or a new word is selected.
    const pendingSentenceIdRef = useRef<number | null | undefined>(undefined);

    function fireTranscriptClick(wordId: number, sentenceId: number | null | undefined) {
        if (!token) return;
        wordsApi.recordTranscriptClick(token, wordId, sentenceId).catch((err) => {
            console.warn('recordTranscriptClick failed', err);
        });
    }

    const selectWord = useCallback(async (word: string, sentenceId?: number | null) => {
        if (!token) return;
        // toggle off if same word clicked again
        if (selected === word) {
            setSelected(null);
            setState(IDLE);
            pendingSentenceIdRef.current = undefined;
            return;
        }
        setSelected(word);
        pendingSentenceIdRef.current = sentenceId;
        setState({
            lookup: null, candidates: [],
            loading: true, saving: false, learnAnywayError: null,
        });
        const resp = await wordsApi.lookupWord(token, word, language);

        if (resp.status === 'single' && resp.item) {
            // Single match — set lookup and record transcript exposure now.
            setState({
                lookup: resp.item, candidates: [],
                loading: false, saving: false, learnAnywayError: null,
            });
            fireTranscriptClick(resp.item.word_id, sentenceId);
            pendingSentenceIdRef.current = undefined;
        } else if (resp.status === 'ambiguous') {
            // Defer transcript-click until user picks a candidate (W3).
            setState({
                lookup: null, candidates: resp.candidates,
                loading: false, saving: false, learnAnywayError: null,
            });
            // pendingSentenceIdRef stays — selectCandidate will consume it.
        } else {
            // not_found
            setState({
                lookup: null, candidates: [],
                loading: false, saving: false, learnAnywayError: null,
            });
            pendingSentenceIdRef.current = undefined;
        }
    }, [token, language, selected]);

    /**
     * W3 (Hole 2): user picks one of the ambiguous candidates. Promotes it
     * to `lookup` (so the normal status picker renders) and fires the
     * deferred transcript-click against the now-known word_id.
     */
    const selectCandidate = useCallback((candidate: WordLookupResult) => {
        setState(s => ({
            ...s,
            lookup: candidate,
            candidates: [],
        }));
        fireTranscriptClick(candidate.word_id, pendingSentenceIdRef.current);
        pendingSentenceIdRef.current = undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token]);

    const updateStatus = useCallback(async (wordId: number, status: string) => {
        if (!token) return;
        setState(s => ({ ...s, saving: true }));
        try {
            await wordsApi.setWordStatus(token, wordId, status);
            setRefreshKey(k => k + 1);
            setState(s => ({
                ...s,
                saving: false,
                lookup: s.lookup ? { ...s.lookup, current_status: status } : null,
            }));
        } catch {
            setState(s => ({ ...s, saving: false }));
        }
    }, [token]);

    const toggleWordStatus = useCallback(async (word: string) => {
        if (!token) return;
        const CYCLE = ['unknown', 'learning', 'known'];
        const resp = await wordsApi.lookupWord(token, word, language);
        const result = wordsApi.pickSingleOrFirst(resp);
        if (!result) return;
        const idx = CYCLE.indexOf(result.current_status ?? '');
        const next = CYCLE[(idx + 1) % CYCLE.length];
        await wordsApi.setWordStatus(token, result.word_id, next);
        setRefreshKey(k => k + 1);
    }, [token, language]);

    const learnAnyway = useCallback(async () => {
        if (!token || !selected) return;
        setState(s => ({ ...s, saving: true, learnAnywayError: null }));
        try {
            const result = await wordsApi.learnWordAnyway(token, selected, language);
            setRefreshKey(k => k + 1);
            setState({
                lookup: result, candidates: [],
                loading: false, saving: false, learnAnywayError: null,
            });
        } catch (err) {
            const msg = err instanceof Error ? err.message : 'Failed to add word';
            setState(s => ({ ...s, saving: false, learnAnywayError: msg }));
        }
    }, [token, language, selected]);

    const dismiss = useCallback(() => {
        setSelected(null);
        setState(IDLE);
        pendingSentenceIdRef.current = undefined;
    }, []);

    return {
        selected, state,
        selectWord, selectCandidate,
        updateStatus, learnAnyway,
        dismiss, refreshKey, toggleWordStatus,
    };
}
