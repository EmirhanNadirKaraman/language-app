import { useState, useEffect, useCallback, useRef } from 'react';
import type { SearchResult } from '../types';
import type { YoutubeEmbedHandle } from '../components/YoutubeEmbed';
import { fetchVideoSentences, fetchWordForms } from '../api/search';
import { normalizeSentences, findSentenceByTime, sentenceContainsTerm, type NormalizedSentence } from '../utils/sentenceUtils';

interface Args {
    result: SearchResult;
    query: string;
    onPrev: () => void;
    onNext: () => void;
}

export function usePlayerSentences({ result, query, onPrev, onNext }: Args) {
    const [sentences, setSentences] = useState<NormalizedSentence[]>([]);
    const [sentenceIdx, setSentenceIdx] = useState(0);

    const playerRef = useRef<YoutubeEmbedHandle>(null);

    const baseTerms = result.surface_form
        ? [result.surface_form]
        : query.split(' ').filter(t => t.length > 0);

    const [highlightTerms, setHighlightTerms] = useState<string[]>(baseTerms);

    // For word searches, expand terms to all conjugated/inflected forms
    useEffect(() => {
        if (result.surface_form) {
            setHighlightTerms([result.surface_form]);
            return;
        }
        if (!query) return;
        fetchWordForms(query)
            .then(forms => setHighlightTerms(forms.length > 0 ? forms : baseTerms))
            .catch(() => setHighlightTerms(baseTerms));
    }, [query, result.surface_form]); // eslint-disable-line react-hooks/exhaustive-deps

    // Fetch sentences when the video/query changes
    useEffect(() => {
        setSentences([]);
        setSentenceIdx(0);

        if (!query) return;

        fetchVideoSentences(result.video_id)
            .then(data => {
                const normalized = normalizeSentences(data);
                setSentences(normalized);

                const idx = normalized.findIndex(s => Math.floor(s.timeSec) === result.start_time_int);
                setSentenceIdx(idx >= 0 ? idx : 0);
            })
            .catch(() => {});
    }, [result.video_id, result.start_time_int, query]);

    // Refs so the interval callback always sees fresh values
    const sentencesRef = useRef<NormalizedSentence[]>([]);
    sentencesRef.current = sentences;

    const sentenceIdxRef = useRef(0);
    sentenceIdxRef.current = sentenceIdx;

    // Drive subtitle sync from actual player time, not wall clock
    useEffect(() => {
        const id = setInterval(() => {
            if (sentencesRef.current.length === 0) return;

            const currentTime = playerRef.current?.getCurrentTime() ?? 0;
            if (currentTime === 0) return;

            const newIdx = findSentenceByTime(sentencesRef.current, currentTime);
            if (newIdx !== sentenceIdxRef.current) {
                setSentenceIdx(newIdx);
            }
        }, 250);

        return () => clearInterval(id);
    }, []);

    const seekTo = useCallback((newIdx: number, sents: NormalizedSentence[]) => {
        setSentenceIdx(newIdx);
        const LEAD_IN = 0.5;
        playerRef.current?.seekTo(Math.max(0, Math.floor(sents[newIdx].timeSec) - LEAD_IN));
    }, []);

    // Navigate to the previous sentence that contains a highlight term,
    // or fall through to the previous video result if none exists
    const handlePrevMatch = useCallback(() => {
        for (let i = sentenceIdx - 1; i >= 0; i--) {
            if (sentenceContainsTerm(sentences[i], highlightTerms)) {
                seekTo(i, sentences);
                return;
            }
        }
        onPrev();
    }, [sentenceIdx, sentences, highlightTerms, seekTo, onPrev]);

    // Navigate to the next sentence that contains a highlight term,
    // or fall through to the next video result if none exists
    const handleNextMatch = useCallback(() => {
        for (let i = sentenceIdx + 1; i < sentences.length; i++) {
            if (sentenceContainsTerm(sentences[i], highlightTerms)) {
                seekTo(i, sentences);
                return;
            }
        }
        onNext();
    }, [sentenceIdx, sentences, highlightTerms, seekTo, onNext]);

    const current = sentences[sentenceIdx];

    const handleReplay = useCallback(() => {
        const time = current?.timeSec ?? result.start_time_int;
        playerRef.current?.seekTo(Math.floor(time));
    }, [current, result.start_time_int]);

    const hasPrevMatch = sentences.slice(0, sentenceIdx).some(s => sentenceContainsTerm(s, highlightTerms));
    const hasNextMatch = sentences.slice(sentenceIdx + 1).some(s => sentenceContainsTerm(s, highlightTerms));

    return {
        sentences,
        sentenceIdx,
        playerRef,
        current,
        highlightTerms,
        handlePrevMatch,
        handleNextMatch,
        handleReplay,
        hasPrevMatch,
        hasNextMatch,
    };
}
