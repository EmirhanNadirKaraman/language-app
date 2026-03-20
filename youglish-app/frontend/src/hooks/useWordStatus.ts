import { useCallback, useState } from 'react';
import * as wordsApi from '../api/words';
import type { WordLookupResult } from '../types';

interface State {
    lookup: WordLookupResult | null;
    loading: boolean;
    saving: boolean;
}

const IDLE: State = { lookup: null, loading: false, saving: false };

export function useWordStatus(token: string | null, language: string) {
    const [selected, setSelected] = useState<string | null>(null);
    const [state, setState] = useState<State>(IDLE);
    const [refreshKey, setRefreshKey] = useState(0);

    const selectWord = useCallback(async (word: string) => {
        if (!token) return;
        // toggle off if same word clicked again
        if (selected === word) {
            setSelected(null);
            setState(IDLE);
            return;
        }
        setSelected(word);
        setState({ lookup: null, loading: true, saving: false });
        const result = await wordsApi.lookupWord(token, word, language);
        setState({ lookup: result, loading: false, saving: false });
    }, [token, language, selected]);

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
        const result = await wordsApi.lookupWord(token, word, language);
        if (!result) return;
        const idx = CYCLE.indexOf(result.current_status ?? '');
        const next = CYCLE[(idx + 1) % CYCLE.length];
        await wordsApi.setWordStatus(token, result.word_id, next);
        setRefreshKey(k => k + 1);
    }, [token, language]);

    const dismiss = useCallback(() => {
        setSelected(null);
        setState(IDLE);
    }, []);

    return { selected, state, selectWord, updateStatus, dismiss, refreshKey, toggleWordStatus };
}
