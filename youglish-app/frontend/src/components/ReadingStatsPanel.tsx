import { useReadingStats } from '../hooks/useReadingStats';

interface Props {
    videoId: string;
    token: string | null;
    refreshKey?: number;
}

export function ReadingStatsPanel({ videoId, token, refreshKey = 0 }: Props) {
    const stats = useReadingStats(videoId, token, refreshKey);

    if (!token) {
        return (
            <div style={containerStyle}>
                <span style={{ color: '#aaa', fontSize: '12px' }}>
                    Sign in to see word coverage for this video.
                </span>
            </div>
        );
    }

    if (!stats) {
        return (
            <div style={containerStyle}>
                <span style={{ color: '#bbb', fontSize: '12px' }}>Loading coverage…</span>
            </div>
        );
    }

    return (
        <div style={containerStyle}>
            {/* Stacked bar */}
            <div style={{ display: 'flex', height: '7px', borderRadius: '4px', overflow: 'hidden', background: '#e8e8e8', marginBottom: '7px' }}>
                <div style={{ width: `${stats.known_pct}%`, background: '#43a047', transition: 'width 0.4s' }} />
                <div style={{ width: `${stats.learning_pct}%`, background: '#fb8c00', transition: 'width 0.4s' }} />
                <div style={{ width: `${stats.unknown_pct}%`, background: '#e53935', transition: 'width 0.4s' }} />
            </div>

            {/* Legend row */}
            <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', fontSize: '12px', color: '#555' }}>
                <Chip color="#43a047" label="Known"    count={stats.known}    pct={stats.known_pct} />
                <Chip color="#fb8c00" label="Learning" count={stats.learning} pct={stats.learning_pct} />
                <Chip color="#e53935" label="Unknown"  count={stats.unknown}  pct={stats.unknown_pct} />
                <span style={{ marginLeft: 'auto', color: '#999' }}>
                    {stats.total_lemmas} unique lemmas
                </span>
            </div>
        </div>
    );
}

function Chip({ color, label, count, pct }: { color: string; label: string; count: number; pct: number }) {
    return (
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: color, display: 'inline-block' }} />
            <span style={{ color: '#444' }}>{label}:</span>
            <strong>{count}</strong>
            <span style={{ color: '#999' }}>({pct}%)</span>
        </span>
    );
}

const containerStyle: React.CSSProperties = {
    padding: '10px 16px',
    borderTop: '1px solid #ebebeb',
    background: '#fafafa',
    minHeight: '42px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
};
