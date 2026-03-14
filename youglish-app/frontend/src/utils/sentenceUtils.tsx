import type { ReactNode } from 'react';
import type { VideoSentence } from '../types';

export type NormalizedSentence = VideoSentence & {
    timeSec: number;
};

export function normalizeSentences(sentences: VideoSentence[]): NormalizedSentence[] {
    return sentences.map(s => ({
        ...s,
        timeSec: Number(s.start_time ?? s.start_time_int ?? 0),
    }));
}

export function findSentenceByTime(sentences: NormalizedSentence[], time: number): number {
    let idx = 0;

    for (let i = 0; i < sentences.length; i++) {
        if (sentences[i].timeSec <= time + 0.3) {
            idx = i;
        } else {
            break;
        }
    }

    return idx;
}

export function sentenceContainsTerm(sentence: NormalizedSentence, terms: string[]): boolean {
    return terms.some(t => new RegExp(`\\b${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(sentence.content));
}

export function highlightText(text: string, terms: string[]): React.ReactNode {
    if (!terms.length) return text;

    const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const parts = text.split(new RegExp(`\\b(${escaped.join('|')})\\b`, 'gi'));

    return parts.map((part, i) =>
        terms.some(t => part.toLowerCase() === t.toLowerCase())
            ? (
                <mark
                    key={i}
                    style={{
                        background: '#fff176',
                        padding: '0 4px',
                        borderRadius: '2px',
                        display: 'inline',
                        whiteSpace: 'normal',
                        overflowWrap: 'anywhere',
                        wordBreak: 'break-word',
                    }}
                >
                    {part}
                </mark>
            )
            : part
    );
}
