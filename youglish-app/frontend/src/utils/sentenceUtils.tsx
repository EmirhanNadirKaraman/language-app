import { useState } from 'react';
import type { VideoSentence } from '../types';
import { WORD_COLORS } from '../config/wordColors';

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
    return terms.some(t => new RegExp(`(?<![\\p{L}\\p{N}])${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\p{L}\\p{N}])`, 'iu').test(sentence.content));
}

function ClickableWord({ word, isHighlighted, status, onClick, onRightClick, wordColors }: {
    word: string;
    isHighlighted: boolean;
    status: string | null;
    onClick: () => void;
    onRightClick?: () => void;
    wordColors?: WordColorScheme;
}) {
    const [hovered, setHovered] = useState(false);
    const colors = wordColors ?? WORD_COLORS;

    // Priority: search highlight > hover > knowledge status > default
    const style: React.CSSProperties = isHighlighted
        ? { cursor: 'pointer', padding: '0 2px', borderRadius: '3px', background: '#fff176' }
        : hovered
            ? { cursor: 'pointer', padding: '0 2px', borderRadius: '3px', background: '#e8eaf6' }
            : status && status in colors
                ? { cursor: 'pointer', padding: '0 2px', borderRadius: '3px', ...colors[status as keyof typeof colors] }
                : { cursor: 'pointer', padding: '0 2px' };

    return (
        <span
            onClick={onClick}
            onContextMenu={onRightClick ? (e) => { e.preventDefault(); onRightClick(); } : undefined}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            style={style}
        >
            {word}
        </span>
    );
}

export function renderClickableText(
    text: string,
    highlightTerms: string[],
    onWordClick: (word: string) => void,
    wordStatuses: Record<string, string> = {},
    onWordRightClick?: (word: string) => void,
    wordColors?: WordColorScheme,
): React.ReactNode {
    const parts = text.split(/(\p{L}+)/u);
    return parts.map((part, i) => {
        if (!/^\p{L}+$/u.test(part)) return part;
        const isHighlighted = highlightTerms.some(t => part.toLowerCase() === t.toLowerCase());
        const status = wordStatuses[part.toLowerCase()] ?? null;
        return (
            <ClickableWord
                key={i}
                word={part}
                isHighlighted={isHighlighted}
                status={status}
                onClick={() => onWordClick(part)}
                onRightClick={onWordRightClick ? () => onWordRightClick(part) : undefined}
                wordColors={wordColors}
            />
        );
    });
}

export function highlightText(text: string, terms: string[]): React.ReactNode {
    if (!terms.length) return text;

    const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const parts = text.split(new RegExp(`(?<![\\p{L}\\p{N}])(${escaped.join('|')})(?![\\p{L}\\p{N}])`, 'giu'));

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
