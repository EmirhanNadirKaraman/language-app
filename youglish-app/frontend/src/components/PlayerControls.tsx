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

const btnStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '36px',
    height: '36px',
    border: '1px solid #ccc',
    borderRadius: '6px',
    background: '#fff',
    cursor: 'pointer',
    color: '#333',
};

export function PlayerControls({
    onPrevVideo, onPrevMatch, onReplay, onNextMatch, onNextVideo,
    disablePrevVideo, disablePrevMatch, disableNextMatch, disableNextVideo,
    sentenceIdx, sentenceCount,
}: Props) {
    return (
        <div
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 16px',
                background: '#f5f5f5',
                borderTop: '1px solid #e0e0e0',
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
                    <span style={{ fontSize: '12px', color: '#888' }}>
                        {sentenceIdx + 1}/{sentenceCount} in video
                    </span>
                )}
            </div>
        </div>
    );
}
