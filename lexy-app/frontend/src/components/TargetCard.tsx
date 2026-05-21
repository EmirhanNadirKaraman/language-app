import type { SearchResult } from '../types';

interface Props {
    result: SearchResult;
}

export function TargetCard({ result }: Props) {
    return (
        <div style={{
            padding: '8px 16px',
            background: 'var(--color-primary-soft)',
            borderBottom: '1px solid var(--color-border-accent)',
            fontSize: '13px',
            display: 'flex',
            gap: '6px',
            alignItems: 'baseline',
            flexWrap: 'wrap',
        }}>
            <span style={{ color: 'var(--color-primary-on-soft)', fontWeight: 600, flexShrink: 0 }}>Practicing with:</span>
            <span style={{ color: 'var(--color-primary-on-soft)', fontStyle: 'italic' }}>{result.content}</span>
            <span style={{ color: 'var(--color-text-subtle)', flexShrink: 0 }}>({result.language})</span>
        </div>
    );
}
