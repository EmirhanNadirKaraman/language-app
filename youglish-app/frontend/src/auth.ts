// Thin localStorage wrapper for auth state.
// No global state — React components read this at render time or on event.

const TOKEN_KEY = 'auth_token';
const EMAIL_KEY = 'auth_email';

export function getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
    localStorage.removeItem(TOKEN_KEY);
}

/**
 * Read the signed-in user's email from localStorage. Returns `null` when no
 * user is signed in OR when the email was never persisted (older app versions
 * didn't store it). Callers MUST handle `null` — do not assert non-null.
 */
export function getStoredEmail(): string | null {
    return localStorage.getItem(EMAIL_KEY);
}

export function setStoredEmail(email: string): void {
    localStorage.setItem(EMAIL_KEY, email);
}

export function clearStoredEmail(): void {
    localStorage.removeItem(EMAIL_KEY);
}
