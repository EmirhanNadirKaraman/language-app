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
            borderTop: '1px solid #e0e0e0',
            background: '#fafafa',
        }}>
            <textarea
                ref={ref}
                value={value}
                onChange={e => setValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Schreib auf Deutsch…"
                enterKeyHint="send"
                disabled={disabled}
                rows={2}
                style={{
                    flex: 1,
                    resize: 'none',
                    padding: '7px 11px',
                    borderRadius: '8px',
                    border: '1px solid #ccc',
                    fontSize: '14px',
                    fontFamily: 'inherit',
                    outline: 'none',
                    lineHeight: 1.4,
                }}
            />
            <button
                onClick={submit}
                disabled={!canSend}
                style={{
                    padding: '0 18px',
                    borderRadius: '8px',
                    border: 'none',
                    background: canSend ? '#1a237e' : '#ccc',
                    color: '#fff',
                    cursor: canSend ? 'pointer' : 'not-allowed',
                    fontSize: '14px',
                    fontWeight: 600,
                    alignSelf: 'stretch',
                    minWidth: '64px',
                }}
            >
                {disabled ? '…' : 'Send'}
            </button>
        </div>
    );
}
