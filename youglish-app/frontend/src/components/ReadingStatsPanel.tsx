import { useReadingStats } from '../hooks/useReadingStats';
import type { WordColorScheme } from '../config/wordColors';
import { WORD_COLORS } from '../config/wordColors';

interface Props {
    videoId: string;
    token: string | null;
    refreshKey?: number;
    wordColors?: WordColorScheme;
}

export function ReadingStatsPanel({ videoId, token, refreshKey = 0, wordColors }: Props) {
    const colors = wordColors ?? WORD_COLORS;
    const stats = useReadingStats(videoId, token, refreshKey);

    if (!token) {
        return (
            <div style={containerStyle}>
                <span style={{ color: 'var(--color-text-subtle)', fontSize: '12px' }}>
                    Sign in to see word coverage for this video.
                </span>
            </div>
        );
    }

    if (!stats) {
        return (
            <div style={containerStyle}>
                <span style={{ color: 'var(--color-text-subtle)', fontSize: '12px' }}>Loading coverage…</span>
            </div>
        );
    }

    return (
        <div style={containerStyle}>
            {/* Stacked bar */}
            <div style={{ display: 'flex', height: '7px', borderRadius: '4px', overflow: 'hidden', background: 'var(--color-border)', marginBottom: '7px' }}>
                <div style={{ width: `${stats.known_pct}%`, background: colors.known.color as string, transition: 'width 0.4s' }} />
                <div style={{ width: `${stats.learning_pct}%`, background: colors.learning.color as string, transition: 'width 0.4s' }} />
                <div style={{ width: `${stats.unknown_pct}%`, background: colors.unknown.color as string, transition: 'width 0.4s' }} />
            </div>

            {/* Legend row */}
            <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--color-text-muted)' }}>
                <Chip color={colors.known.color as string}    label="Known"    count={stats.known}    pct={stats.known_pct} />
                <Chip color={colors.learning.color as string} label="Learning" count={stats.learning} pct={stats.learning_pct} />
                <Chip color={colors.unknown.color as string}  label="Unknown"  count={stats.unknown}  pct={stats.unknown_pct} />
                <span style={{ marginLeft: 'auto', color: 'var(--color-text-subtle)' }}>
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
            <span style={{ color: 'var(--color-text)' }}>{label}:</span>
            <strong>{count}</strong>
            <span style={{ color: 'var(--color-text-subtle)' }}>({pct}%)</span>
        </span>
    );
}

const containerStyle: React.CSSProperties = {
    padding: '10px 16px',
    borderTop: '1px solid var(--color-border-subtle)',
    background: 'var(--color-surface-muted)',
    minHeight: '42px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
};
