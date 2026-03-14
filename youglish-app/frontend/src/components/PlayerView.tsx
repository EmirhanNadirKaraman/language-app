import { useEffect, useRef } from 'react';
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
        handlePrev,
        handleNext,
        handleReplay,
        atFirstEver,
        atLastEver,
    } = usePlayerSentences({ result, query, canPrev, canNext, onPrev, onNext });

    const highlightTerms = result.surface_form
        ? [result.surface_form]
        : query.split(' ').filter(t => t.length > 0);

    const displayContent = current?.content ?? result.content;

    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const root = rootRef.current;
        if (!root) return;

        const youtubeBox = root.querySelector('[data-debug="youtube-box"]') as HTMLElement | null;
        const controlsBox = root.querySelector('[data-debug="controls-box"]') as HTMLElement | null;
        const subtitleBox = root.querySelector('[data-debug="subtitle-box"]') as HTMLElement | null;
        const subtitleText = root.querySelector('[data-debug="subtitle-text"]') as HTMLElement | null;

        console.log('--- PLAYERVIEW SIZE DEBUG ---');
        console.log('displayContent:', displayContent);
        console.log('root', {
            clientWidth: root.clientWidth,
            scrollWidth: root.scrollWidth,
            offsetWidth: root.offsetWidth,
        });
        console.log('youtubeBox', youtubeBox && {
            clientWidth: youtubeBox.clientWidth,
            scrollWidth: youtubeBox.scrollWidth,
            offsetWidth: youtubeBox.offsetWidth,
        });
        console.log('controlsBox', controlsBox && {
            clientWidth: controlsBox.clientWidth,
            scrollWidth: controlsBox.scrollWidth,
            offsetWidth: controlsBox.offsetWidth,
        });
        console.log('subtitleBox', subtitleBox && {
            clientWidth: subtitleBox.clientWidth,
            scrollWidth: subtitleBox.scrollWidth,
            offsetWidth: subtitleBox.offsetWidth,
        });
        console.log('subtitleText', subtitleText && {
            clientWidth: subtitleText.clientWidth,
            scrollWidth: subtitleText.scrollWidth,
            offsetWidth: subtitleText.offsetWidth,
        });
    }, [displayContent, sentenceIdx]);

    return (
        <div
            ref={rootRef}
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
                    onPrev={handlePrev}
                    onReplay={handleReplay}
                    onNext={handleNext}
                    disablePrev={atFirstEver}
                    disableNext={atLastEver}
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