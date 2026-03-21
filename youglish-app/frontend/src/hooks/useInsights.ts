import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchInsightCards } from '../api/insights';
import type { InsightCard } from '../types';

interface State {
    cards: InsightCard[];
    loading: boolean;
    error: string | null;
}

const INITIAL: State = { cards: [], loading: false, error: null };

export function useInsights(token: string | null, language: string) {
    const [state, setState] = useState<State>(INITIAL);
    const abortRef = useRef<AbortController | null>(null);

    const refresh = useCallback(() => {
        if (!token || !language) {
            setState(INITIAL);
            return;
        }

        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setState(s => ({ ...s, loading: true, error: null }));

        fetchInsightCards(token, language)
            .then(res => setState({ cards: res.cards, loading: false, error: null }))
            .catch((err: unknown) => {
                if (err instanceof Error && err.name === 'AbortError') return;
                setState(s => ({ ...s, loading: false, error: 'Failed to load insights.' }));
            });
    }, [token, language]);

    useEffect(() => {
        refresh();
        return () => { abortRef.current?.abort(); };
    }, [refresh]);

    return { ...state, refresh };
}
