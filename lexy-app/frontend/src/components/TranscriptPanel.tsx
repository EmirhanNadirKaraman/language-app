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
    onWordClick: (word: string, sentenceId?: number) => void;
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
            <ReadingStatsPanel videoId={videoId} token={token} refreshKey={refreshKey} wordColors={wordColors} />
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
                                // Mobile (#27c): bump padding so each row gives a finger-friendly
                                // tap area without changing desktop density much. clamp() keeps
                                // the side padding tight on phones and roomy on desktop.
                                padding: '10px clamp(10px, 3vw, 16px)',
                                minHeight: '44px',
                                boxSizing: 'border-box',
                                cursor: 'pointer',
                                background: isActive ? 'var(--color-primary-soft)' : 'transparent',
                                borderLeft: isActive ? '3px solid var(--color-primary)' : '3px solid transparent',
                                // Fluid sentence font: 14px on a 320px phone, 16px on desktop.
                                fontSize: 'clamp(14px, 3.5vw, 16px)',
                                lineHeight: 1.65,
                                color: 'var(--color-text-strong)',
                                transition: 'background 0.15s',
                                overflowWrap: 'anywhere',
                                wordBreak: 'break-word',
                            }}
                        >
                            {renderClickableText(
                                sentence.content,
                                highlightTerms,
                                (word) => onWordClick(word, sentence.sentence_id),
                                wordStatuses,
                                onWordRightClick,
                                wordColors,
                            )}
                        </div>
                    );
                })}
                {sentences.length === 0 && (
                    <p style={{ padding: '16px', color: 'var(--color-text-subtle)', fontSize: '13px', margin: 0 }}>
                        Loading transcript…
                    </p>
                )}
            </div>
        </div>
    );
}
