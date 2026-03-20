import { useEffect, useRef } from 'react';
import type { NormalizedSentence } from '../utils/sentenceUtils';
import { renderClickableText } from '../utils/sentenceUtils';
import { ReadingStatsPanel } from './ReadingStatsPanel';
import type { WordColorScheme } from '../config/wordColors';

interface Props {
    sentences: NormalizedSentence[];
    activeSentenceIdx: number;
    highlightTerms: string[];
    wordStatuses: Record<string, string>;
    onWordClick: (word: string) => void;
    onWordRightClick: (word: string) => void;
    onSentenceClick: (idx: number) => void;
    videoId: string;
    token: string | null;
    refreshKey: number;
    wordColors?: WordColorScheme;
}

export function TranscriptPanel({
    sentences,
    activeSentenceIdx,
    highlightTerms,
    wordStatuses,
    onWordClick,
    onWordRightClick,
    onSentenceClick,
    videoId,
    token,
    refreshKey,
    wordColors,
}: Props) {
    const activeRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }, [activeSentenceIdx]);

    return (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
            <ReadingStatsPanel videoId={videoId} token={token} refreshKey={refreshKey} />
            <div
                style={{
                    maxHeight: '420px',
                    overflowY: 'auto',
                    padding: '4px 0',
                }}
            >
                {sentences.map((sentence, idx) => {
                    const isActive = idx === activeSentenceIdx;
                    return (
                        <div
                            key={sentence.sentence_id}
                            ref={isActive ? activeRef : undefined}
                            data-testid="sentence-block"
                            onClick={(e) => {
                                if (e.target === e.currentTarget) onSentenceClick(idx);
                            }}
                            style={{
                                padding: '6px 16px',
                                cursor: 'pointer',
                                background: isActive ? '#e8eaf6' : 'transparent',
                                borderLeft: isActive ? '3px solid #3f51b5' : '3px solid transparent',
                                fontSize: '15px',
                                lineHeight: 1.65,
                                color: '#1a237e',
                                transition: 'background 0.15s',
                            }}
                        >
                            {renderClickableText(sentence.content, highlightTerms, onWordClick, wordStatuses, onWordRightClick, wordColors)}
                        </div>
                    );
                })}
                {sentences.length === 0 && (
                    <p style={{ padding: '16px', color: '#aaa', fontSize: '13px', margin: 0 }}>
                        Loading transcript…
                    </p>
                )}
            </div>
        </div>
    );
}
