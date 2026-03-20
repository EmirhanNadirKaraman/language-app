import { useState } from 'react';
import { login, register } from '../api/auth';
import { clearStoredEmail, clearToken, getStoredEmail, setStoredEmail, setToken } from '../auth';

interface Props {
    token: string | null;
    onLogin: (token: string) => void;
    onLogout: () => void;
}

type Mode = 'closed' | 'login' | 'register';

export function LoginForm({ token, onLogin, onLogout }: Props) {
    const [mode, setMode] = useState<Mode>('closed');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    function handleLogout() {
        clearToken();
        clearStoredEmail();
        onLogout();
    }

    // Signed in — show email + sign out
    if (token) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
                <span style={{ color: '#555' }}>{getStoredEmail() ?? 'Signed in'}</span>
                <button onClick={handleLogout} style={ghostBtn}>Sign out</button>
            </div>
        );
    }

    // Signed out — show button or inline form
    if (mode === 'closed') {
        return (
            <button onClick={() => setMode('login')} style={outlineBtn}>Sign in</button>
        );
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            if (mode === 'register') {
                await register(email, password);
            }
            const newToken = await login(email, password);
            setToken(newToken);
            setStoredEmail(email);
            onLogin(newToken);
            setMode('closed');
            setEmail('');
            setPassword('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed');
        } finally {
            setLoading(false);
        }
    }

    return (
        <form onSubmit={handleSubmit} style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            {/* Mode toggle */}
            <span style={{ fontSize: '12px', color: '#888' }}>
                <button type="button" onClick={() => { setMode('login'); setError(null); }}
                    style={{ ...ghostBtn, fontWeight: mode === 'login' ? 700 : 400 }}>Login</button>
                {' / '}
                <button type="button" onClick={() => { setMode('register'); setError(null); }}
                    style={{ ...ghostBtn, fontWeight: mode === 'register' ? 700 : 400 }}>Register</button>
            </span>

            <input type="email" placeholder="Email" value={email}
                onChange={e => setEmail(e.target.value)} required style={inputStyle} />
            <input type="password" placeholder="Password" value={password}
                onChange={e => setPassword(e.target.value)} required style={inputStyle} />

            <button type="submit" disabled={loading} style={primaryBtn}>
                {loading ? '…' : mode === 'register' ? 'Create' : 'Sign in'}
            </button>
            <button type="button" onClick={() => { setMode('closed'); setError(null); }} style={ghostBtn}>
                ✕
            </button>

            {error && <span style={{ color: '#c62828', fontSize: '12px', width: '100%' }}>{error}</span>}
        </form>
    );
}

const inputStyle: React.CSSProperties = {
    fontSize: '13px', padding: '4px 8px',
    border: '1px solid #ccc', borderRadius: '4px',
    width: '140px',
};
const ghostBtn: React.CSSProperties = {
    background: 'none', border: 'none', cursor: 'pointer',
    fontSize: '12px', color: '#666', padding: 0,
};
const outlineBtn: React.CSSProperties = {
    fontSize: '13px', padding: '4px 12px',
    border: '1px solid #1a3a6c', borderRadius: '4px',
    background: 'none', color: '#1a3a6c', cursor: 'pointer',
};
const primaryBtn: React.CSSProperties = {
    fontSize: '13px', padding: '4px 12px',
    background: '#1a3a6c', color: '#fff',
    border: 'none', borderRadius: '4px', cursor: 'pointer',
};
