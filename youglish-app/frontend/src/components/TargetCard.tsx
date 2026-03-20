import type { SearchResult } from '../types';

interface Props {
    result: SearchResult;
}

export function TargetCard({ result }: Props) {
    return (
        <div style={{
            padding: '8px 16px',
            background: '#e8eaf6',
            borderBottom: '1px solid #c5cae9',
            fontSize: '13px',
            display: 'flex',
            gap: '6px',
            alignItems: 'baseline',
            flexWrap: 'wrap',
        }}>
            <span style={{ color: '#5c6bc0', fontWeight: 600, flexShrink: 0 }}>Practicing with:</span>
            <span style={{ color: '#1a237e', fontStyle: 'italic' }}>{result.content}</span>
            <span style={{ color: '#9e9e9e', flexShrink: 0 }}>({result.language})</span>
        </div>
    );
}
