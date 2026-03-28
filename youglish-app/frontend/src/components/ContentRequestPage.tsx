import { useState, useEffect } from 'react';
import { submitContentRequest, listContentRequests } from '../api/contentRequests';
import type { ContentRequest } from '../api/contentRequests';

interface Props {
    token: string;
    onClose: () => void;
    darkMode?: boolean;
}

const STATUS_STYLES: Record<string, React.CSSProperties> = {
    pending: { background: '#fff8e1', color: '#e65100', border: '1px solid #ffe082' },
    done:    { background: '#e8f5e9', color: '#2e7d32', border: '1px solid #c8e6c9' },
    failed:  { background: '#ffebee', color: '#c62828', border: '1px solid #ffcdd2' },
};

export function ContentRequestPage({ token, onClose, darkMode = false }: Props) {
    const [requestType, setRequestType] = useState<'channel' | 'video'>('channel');
    const [contentId, setContentId] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState<string | null>(null);
    const [submitted, setSubmitted] = useState(false);
    const [requests, setRequests] = useState<ContentRequest[]>([]);
    const [loadError, setLoadError] = useState<string | null>(null);

    useEffect(() => {
        listContentRequests(token)
            .then(setRequests)
            .catch(e => setLoadError(e.message));
    }, [token]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        const id = contentId.trim();
        if (!id) return;

        setSubmitting(true);
        setSubmitError(null);
        setSubmitted(false);
        try {
            const req = await submitContentRequest(token, requestType, id);
            setRequests(prev => {
                const existing = prev.findIndex(r => r.request_id === req.request_id);
                if (existing >= 0) {
                    const next = [...prev];
                    next[existing] = req;
                    return next;
                }
                return [req, ...prev];
            });
            setContentId('');
            setSubmitted(true);
        } catch (e: unknown) {
            setSubmitError(e instanceof Error ? e.message : 'Unknown error');
        } finally {
            setSubmitting(false);
        }
    }

    const bg    = darkMode ? '#1e1e1e' : '#fff';
    const text  = darkMode ? '#e0e0e0' : '#222';
    const muted = darkMode ? '#aaa'    : '#666';
    const border = darkMode ? '#333'   : '#e0e0e0';
    const inputBg = darkMode ? '#2a2a2a' : '#fff';
    const inputBorder = darkMode ? '#444' : '#ccc';
    const tabActiveBg = darkMode ? '#1a237e' : '#e8eaf6';
    const tabActiveColor = darkMode ? '#fff' : '#1a237e';

    const hint = requestType === 'channel'
        ? 'YouTube channel ID — starts with UC, e.g. UCxxxxxxxxxxxxxxxxxxxxxxxx'
        : 'YouTube video ID — 11 characters, e.g. dQw4w9WgXcQ';

    return (
        <div style={{ background: bg, color: text, borderRadius: '10px', padding: '24px', maxWidth: '640px', margin: '0 auto' }}>

            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h2 style={{ margin: 0, fontSize: '18px', color: '#1a237e' }}>Request Content</h2>
                <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: muted }}>×</button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit}>
                {/* Type toggle */}
                <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                    {(['channel', 'video'] as const).map(t => (
                        <button
                            key={t}
                            type="button"
                            onClick={() => { setRequestType(t); setContentId(''); setSubmitted(false); setSubmitError(null); }}
                            style={{
                                padding: '7px 20px', borderRadius: '6px', fontSize: '13px', fontWeight: 600,
                                cursor: 'pointer', border: '1px solid #c5cae9',
                                background: requestType === t ? tabActiveBg : (darkMode ? '#2a2a2a' : '#fff'),
                                color: requestType === t ? tabActiveColor : muted,
                            }}
                        >
                            {t === 'channel' ? 'Channel' : 'Video'}
                        </button>
                    ))}
                </div>

                {/* ID input */}
                <div style={{ marginBottom: '8px' }}>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px', color: text }}>
                        {requestType === 'channel' ? 'Channel ID' : 'Video ID'}
                    </label>
                    <input
                        value={contentId}
                        onChange={e => { setContentId(e.target.value); setSubmitted(false); setSubmitError(null); }}
                        placeholder={requestType === 'channel' ? 'UCxxxxxxxxxxxxxxxxxxxxxxxx' : 'dQw4w9WgXcQ'}
                        style={{
                            width: '100%', padding: '8px 10px', boxSizing: 'border-box',
                            border: `1px solid ${inputBorder}`, borderRadius: '6px',
                            fontSize: '14px', fontFamily: 'monospace',
                            background: inputBg, color: text,
                        }}
                        autoComplete="off"
                        spellCheck={false}
                    />
                    <p style={{ margin: '5px 0 0', fontSize: '12px', color: muted }}>{hint}</p>
                </div>

                {submitError && (
                    <p style={{ margin: '10px 0', fontSize: '13px', color: '#c62828' }}>{submitError}</p>
                )}
                {submitted && (
                    <p style={{ margin: '10px 0', fontSize: '13px', color: '#2e7d32' }}>
                        Request submitted — it will be processed on the next pipeline run.
                    </p>
                )}

                <button
                    type="submit"
                    disabled={submitting || !contentId.trim()}
                    style={{
                        marginTop: '12px', padding: '9px 24px', borderRadius: '6px',
                        border: 'none', background: '#1a237e', color: '#fff',
                        fontSize: '14px', fontWeight: 600, cursor: submitting || !contentId.trim() ? 'not-allowed' : 'pointer',
                        opacity: submitting || !contentId.trim() ? 0.6 : 1,
                    }}
                >
                    {submitting ? 'Submitting…' : 'Submit Request'}
                </button>
            </form>

            {/* Existing requests */}
            <div style={{ marginTop: '32px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 600, color: muted, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Your Requests
                </h3>

                {loadError && <p style={{ color: '#c62828', fontSize: '13px' }}>{loadError}</p>}

                {requests.length === 0 && !loadError && (
                    <p style={{ color: muted, fontSize: '13px' }}>No requests yet.</p>
                )}

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {requests.map(r => (
                        <div
                            key={r.request_id}
                            style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                padding: '10px 14px', borderRadius: '8px',
                                border: `1px solid ${border}`,
                                background: darkMode ? '#2a2a2a' : '#fafafa',
                                gap: '12px', flexWrap: 'wrap',
                            }}
                        >
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                                <span style={{ fontSize: '12px', color: muted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                    {r.request_type}
                                </span>
                                <span style={{ fontSize: '13px', fontFamily: 'monospace', color: text, wordBreak: 'break-all' }}>
                                    {r.content_id}
                                </span>
                                {r.error && (
                                    <span style={{ fontSize: '12px', color: '#c62828' }}>{r.error}</span>
                                )}
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px', flexShrink: 0 }}>
                                <span style={{
                                    fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '10px',
                                    textTransform: 'uppercase', letterSpacing: '0.05em',
                                    ...STATUS_STYLES[r.status],
                                }}>
                                    {r.status}
                                </span>
                                <span style={{ fontSize: '11px', color: muted }}>
                                    {new Date(r.created_at).toLocaleDateString()}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
