import { useState, useEffect, useCallback, useRef } from 'react';
import type { SearchResult } from '../types';
import type { YoutubeEmbedHandle } from '../components/YoutubeEmbed';
import { fetchVideoSentences } from '../api/search';
import { normalizeSentences, findSentenceByTime, type NormalizedSentence } from '../utils/sentenceUtils';

interface Args {
    result: SearchResult;
    query: string;
    canPrev: boolean;
    canNext: boolean;
    onPrev: () => void;
    onNext: () => void;
}

export function usePlayerSentences({ result, query, canPrev, canNext, onPrev, onNext }: Args) {
    const [sentences, setSentences] = useState<NormalizedSentence[]>([]);
    const [sentenceIdx, setSentenceIdx] = useState(0);

    const playerRef = useRef<YoutubeEmbedHandle>(null);

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
            .catch(err => console.error('fetchVideoSentences failed', err));
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
        playerRef.current?.seekTo(Math.floor(sents[newIdx].timeSec));
    }, []);

    const handlePrev = useCallback(() => {
        if (sentenceIdx > 0) seekTo(sentenceIdx - 1, sentences);
        else onPrev();
    }, [sentenceIdx, sentences, seekTo, onPrev]);

    const handleNext = useCallback(() => {
        if (sentenceIdx < sentences.length - 1) seekTo(sentenceIdx + 1, sentences);
        else onNext();
    }, [sentenceIdx, sentences, seekTo, onNext]);

    const current = sentences[sentenceIdx];

    const handleReplay = useCallback(() => {
        const time = current?.timeSec ?? result.start_time_int;
        playerRef.current?.seekTo(Math.floor(time));
    }, [current, result.start_time_int]);

    const atFirstEver = !canPrev && sentenceIdx === 0;
    const atLastEver = !canNext && sentenceIdx >= sentences.length - 1;

    return {
        sentences,
        sentenceIdx,
        playerRef,
        current,
        handlePrev,
        handleNext,
        handleReplay,
        atFirstEver,
        atLastEver,
    };
}
