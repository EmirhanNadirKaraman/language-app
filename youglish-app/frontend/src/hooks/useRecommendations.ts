import { useCallback, useEffect, useRef, useState } from 'react';
import {
    fetchItemRecommendations,
    fetchVideoRecommendations,
    fetchSentenceRecommendations,
} from '../api/recommendations';
import type {
    ItemRecommendation,
    VideoRecommendation,
    SentenceRecommendation,
} from '../types';

interface State {
    items:         ItemRecommendation[];
    phrases:       ItemRecommendation[];
    videos:        VideoRecommendation[];
    sentences:     SentenceRecommendation[];
    noTargetItems: boolean;   // true when videos reason === 'no_target_items'
    loading:       boolean;
    error:         string | null;
}

const INITIAL: State = {
    items: [], phrases: [], videos: [], sentences: [],
    noTargetItems: false, loading: false, error: null,
};

export function useRecommendations(token: string | null, language: string) {
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

        Promise.all([
            fetchItemRecommendations(token, language, 'word'),
            fetchItemRecommendations(token, language, 'phrase'),
            fetchVideoRecommendations(token, language),
            fetchSentenceRecommendations(token, language),
        ])
            .then(([itemsRes, phrasesRes, videosRes, sentencesRes]) => {
                setState({
                    items:         itemsRes.items,
                    phrases:       phrasesRes.items,
                    videos:        videosRes.videos,
                    sentences:     sentencesRes.sentences,
                    noTargetItems: videosRes.reason === 'no_target_items',
                    loading:       false,
                    error:         null,
                });
            })
            .catch((err: unknown) => {
                if (err instanceof Error && err.name === 'AbortError') return;
                setState(s => ({ ...s, loading: false, error: 'Failed to load recommendations.' }));
            });
    }, [token, language]);

    useEffect(() => {
        refresh();
        return () => { abortRef.current?.abort(); };
    }, [refresh]);

    return { ...state, refresh };
}
