import type { Correction } from '../types';

interface Props {
    correction: Correction;
}

export function TurnFeedbackChip({ correction }: Props) {
    return (
        <span
            title={correction.explanation}
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 8px',
                borderRadius: '12px',
                fontSize: '12px',
                background: '#fff8e1',
                border: '1px solid #ffc107',
                color: '#6d4c00',
                cursor: 'default',
                marginRight: '4px',
                marginTop: '4px',
                userSelect: 'none',
            }}
        >
            <span style={{ textDecoration: 'line-through', opacity: 0.65 }}>{correction.original}</span>
            <span style={{ opacity: 0.5 }}>→</span>
            <strong>{correction.corrected}</strong>
        </span>
    );
}
