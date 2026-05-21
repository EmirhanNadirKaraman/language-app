import { IconSkipPrev, IconPrevMatch, IconReplay, IconNextMatch, IconSkipNext } from './icons';

interface Props {
    onPrevVideo: () => void;
    onPrevMatch: () => void;
    onReplay: () => void;
    onNextMatch: () => void;
    onNextVideo: () => void;
    disablePrevVideo: boolean;
    disablePrevMatch: boolean;
    disableNextMatch: boolean;
    disableNextVideo: boolean;
    sentenceIdx: number;
    sentenceCount: number;
}

// 44×44 touch target meets iOS Human Interface Guidelines and Material's
// minimum. `minWidth`/`minHeight` so buttons can grow but never shrink below
// the threshold on very narrow phones.
const btnStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '44px',
    minHeight: '44px',
    width: '44px',
    height: '44px',
    border: '1px solid var(--color-input-border)',
    borderRadius: '6px',
    background: 'var(--color-surface)',
    cursor: 'pointer',
    color: 'var(--color-text)',
    touchAction: 'manipulation',
};

export function PlayerControls({
    onPrevVideo, onPrevMatch, onReplay, onNextMatch, onNextVideo,
    disablePrevVideo, disablePrevMatch, disableNextMatch, disableNextVideo,
    sentenceIdx, sentenceCount,
}: Props) {
    return (
        // flexWrap lets the sentence counter drop below the button row on
        // narrow phones (5 × 44 + gaps ≈ 244px already — anything below 320px
        // viewport had no room for the counter on the same line).
        // Gap added on the outer flex so wrapped rows have breathing space.
        <div
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '8px',
                padding: '10px 16px',
                background: 'var(--color-surface-muted)',
                borderTop: '1px solid var(--color-border)',
            }}
        >
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <button
                    title="Previous video"
                    onClick={onPrevVideo}
                    disabled={disablePrevVideo}
                    style={btnStyle}
                >
                    <IconSkipPrev />
                </button>
                <button
                    title="Previous occurrence"
                    onClick={onPrevMatch}
                    disabled={disablePrevMatch}
                    style={btnStyle}
                >
                    <IconPrevMatch />
                </button>
                <button
                    title="Replay"
                    onClick={onReplay}
                    style={btnStyle}
                >
                    <IconReplay />
                </button>
                <button
                    title="Next occurrence"
                    onClick={onNextMatch}
                    disabled={disableNextMatch}
                    style={btnStyle}
                >
                    <IconNextMatch />
                </button>
                <button
                    title="Next video"
                    onClick={onNextVideo}
                    disabled={disableNextVideo}
                    style={btnStyle}
                >
                    <IconSkipNext />
                </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
                {sentenceCount > 1 && (
                    <span style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                        {sentenceIdx + 1}/{sentenceCount} in video
                    </span>
                )}
            </div>
        </div>
    );
}
