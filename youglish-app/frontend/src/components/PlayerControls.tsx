interface Props {
    onPrev: () => void;
    onReplay: () => void;
    onNext: () => void;
    disablePrev: boolean;
    disableNext: boolean;
    sentenceIdx: number;
    sentenceCount: number;
}

export function PlayerControls({ onPrev, onReplay, onNext, disablePrev, disableNext, sentenceIdx, sentenceCount }: Props) {
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
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <button onClick={onPrev} disabled={disablePrev}>Prev</button>
                <button onClick={onReplay}>Replay</button>
                <button onClick={onNext} disabled={disableNext}>Next</button>
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
