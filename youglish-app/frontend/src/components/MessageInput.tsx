import { useState, useRef, type KeyboardEvent } from 'react';

interface Props {
    onSend: (content: string) => void;
    disabled: boolean;
}

export function MessageInput({ onSend, disabled }: Props) {
    const [value, setValue] = useState('');
    const ref = useRef<HTMLTextAreaElement>(null);

    const submit = () => {
        const trimmed = value.trim();
        if (!trimmed || disabled) return;
        onSend(trimmed);
        setValue('');
        ref.current?.focus();
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
        }
    };

    const canSend = !disabled && value.trim().length > 0;

    return (
        <div style={{
            display: 'flex',
            gap: '8px',
            padding: '10px 12px',
            borderTop: '1px solid var(--color-border)',
            background: 'var(--color-surface-muted)',
        }}>
            <textarea
                data-testid="chat-input"
                ref={ref}
                value={value}
                onChange={e => setValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Schreib auf Deutsch…"
                enterKeyHint="send"
                disabled={disabled}
                rows={2}
                // iOS Safari zooms in on any input below 16px on focus. 16px
                // is the minimum that keeps the focus-zoom behaviour off.
                style={{
                    flex: 1,
                    minWidth: 0,
                    resize: 'none',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid var(--color-input-border)',
                    background: 'var(--color-input-bg)',
                    color: 'var(--color-text)',
                    fontSize: '16px',
                    fontFamily: 'inherit',
                    outline: 'none',
                    lineHeight: 1.4,
                }}
            />
            <button
                data-testid="chat-send"
                onClick={submit}
                disabled={!canSend}
                style={{
                    padding: '0 18px',
                    minHeight: '44px',
                    borderRadius: '8px',
                    border: 'none',
                    background: canSend ? 'var(--color-primary)' : 'var(--color-input-border)',
                    color: 'var(--color-primary-text)',
                    cursor: canSend ? 'pointer' : 'not-allowed',
                    fontSize: '14px',
                    fontWeight: 600,
                    alignSelf: 'stretch',
                    minWidth: '64px',
                    touchAction: 'manipulation',
                }}
            >
                {disabled ? '…' : 'Send'}
            </button>
        </div>
    );
}
