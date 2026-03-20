import { useEffect, useState } from 'react';
import type { SearchResult } from '../types';
import { YoutubeEmbed } from './YoutubeEmbed';
import { PlayerControls } from './PlayerControls';
import { SubtitleDisplay } from './SubtitleDisplay';
import { ReadingStatsPanel } from './ReadingStatsPanel';
import { TranscriptPanel } from './TranscriptPanel';
import { WordStatusPicker } from './WordStatusPicker';
import { usePlayerSentences } from '../hooks/usePlayerSentences';
import { useWordStatus } from '../hooks/useWordStatus';
import { useWordColors } from '../hooks/useWordColors';

interface Props {
    result: SearchResult;
    query: string;
    token: string | null;
    canPrev: boolean;
    canNext: boolean;
    onPrev: () => void;
    onNext: () => void;
}

export function PlayerView({ result, query, token, canPrev, canNext, onPrev, onNext }: Props) {
    const {
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
    } = usePlayerSentences({ result, query, onPrev, onNext });

    const { selected, state, selectWord, updateStatus, dismiss, refreshKey, toggleWordStatus } = useWordStatus(token, result.language);
    const wordStatuses = useWordColors(result.video_id, token, refreshKey);
    const [view, setView] = useState<'player' | 'transcript'>('player');

    // Dismiss picker and reset to player view when the video changes
    useEffect(() => { dismiss(); setView('player'); }, [result.video_id]);  // eslint-disable-line react-hooks/exhaustive-deps

    const displayContent = current?.content ?? result.content;

    return (
        <div
            style={{
                width: '100%',
                maxWidth: '100%',
                minWidth: 0,
                border: '1px solid #ddd',
                borderRadius: '8px',
                overflow: 'hidden',
                background: '#fff',
                boxSizing: 'border-box',
            }}
        >
            <div data-debug="youtube-box">
                <YoutubeEmbed
                    ref={playerRef}
                    videoId={result.video_id}
                    startTime={result.start_time_int}
                    autoplay
                />
            </div>

            <div data-debug="controls-box">
                <PlayerControls
                    onPrevVideo={onPrev}
                    onPrevMatch={handlePrevMatch}
                    onReplay={handleReplay}
                    onNextMatch={handleNextMatch}
                    onNextVideo={onNext}
                    disablePrevVideo={!canPrev}
                    disablePrevMatch={!hasPrevMatch && !canPrev}
                    disableNextMatch={!hasNextMatch && !canNext}
                    disableNextVideo={!canNext}
                    sentenceIdx={sentenceIdx}
                    sentenceCount={sentences.length}
                />
            </div>

            <div style={{ display: 'flex', borderBottom: '1px solid #e8eaf6', padding: '0 12px', gap: '2px' }}>
                {(['player', 'transcript'] as const).map(v => (
                    <button
                        key={v}
                        onClick={() => setView(v)}
                        style={{
                            padding: '6px 14px',
                            border: 'none',
                            background: view === v ? '#e8eaf6' : 'transparent',
                            color: view === v ? '#1a237e' : '#888',
                            fontWeight: view === v ? 700 : 400,
                            fontSize: '13px',
                            borderRadius: '4px 4px 0 0',
                            cursor: 'pointer',
                        }}
                    >
                        {v === 'player' ? 'Player' : 'Transcript'}
                    </button>
                ))}
            </div>

            {view === 'player' && (
                <div data-debug="subtitle-box">
                    <SubtitleDisplay
                        text={displayContent}
                        highlightTerms={highlightTerms}
                        onWordClick={token ? (word) => { playerRef.current?.pauseVideo(); selectWord(word); } : undefined}
                        onWordRightClick={token ? (word) => { toggleWordStatus(word); } : undefined}
                        wordStatuses={wordStatuses}
                    />
                </div>
            )}

            {view === 'transcript' && (
                <TranscriptPanel
                    sentences={sentences}
                    activeSentenceIdx={sentenceIdx}
                    highlightTerms={highlightTerms}
                    wordStatuses={wordStatuses}
                    onWordClick={token ? (word) => { playerRef.current?.pauseVideo(); selectWord(word); } : () => {}}
                    onWordRightClick={token ? (word) => { toggleWordStatus(word); } : () => {}}
                    onSentenceClick={(idx) => {
                        const s = sentences[idx];
                        if (s) playerRef.current?.seekTo(Math.max(0, Math.floor(s.timeSec) - 0.5));
                    }}
                    videoId={result.video_id}
                    token={token}
                    refreshKey={refreshKey}
                />
            )}

            {selected && (
                <WordStatusPicker
                    word={selected}
                    lookup={state.lookup}
                    loading={state.loading}
                    saving={state.saving}
                    onSelect={updateStatus}
                    onDismiss={dismiss}
                />
            )}

            {view === 'player' && (
                <div data-debug="stats-box">
                    <ReadingStatsPanel videoId={result.video_id} token={token} refreshKey={refreshKey} />
                </div>
            )}
        </div>
    );
}
