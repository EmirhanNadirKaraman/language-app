import type { SearchResult } from '../types';
import { YoutubeEmbed } from './YoutubeEmbed';
import { PlayerControls } from './PlayerControls';
import { SubtitleDisplay } from './SubtitleDisplay';
import { usePlayerSentences } from '../hooks/usePlayerSentences';

interface Props {
    result: SearchResult;
    query: string;
    canPrev: boolean;
    canNext: boolean;
    onPrev: () => void;
    onNext: () => void;
}

export function PlayerView({ result, query, canPrev, canNext, onPrev, onNext }: Props) {
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

            <div data-debug="subtitle-box">
                <SubtitleDisplay
                    text={displayContent}
                    highlightTerms={highlightTerms}
                />
            </div>
        </div>
    );
}