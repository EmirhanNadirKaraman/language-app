function extractDetail(detail: unknown, fallback: string): string {
    if (!detail) return fallback;
    if (typeof detail === 'string') return detail || fallback;
    if (Array.isArray(detail) && detail.length > 0) {
        return detail
            .map((d: { msg?: string; loc?: unknown[] }) => {
                const field = d.loc?.findLast(s => s !== 'body');
                const msg = d.msg ?? 'Invalid value';
                return field ? `${String(field).charAt(0).toUpperCase() + String(field).slice(1)}: ${msg}` : msg;
            })
            .join('. ');
    }
    return fallback;
}

export async function login(email: string, password: string): Promise<string> {
    const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: unknown };
        throw new Error(extractDetail(err.detail, `Login failed (${res.status})`));
    }
    const data = await res.json() as { access_token: string };
    return data.access_token;
}

export async function register(email: string, password: string): Promise<void> {
    const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: unknown };
        throw new Error(extractDetail(err.detail, `Registration failed (${res.status})`));
    }
}
