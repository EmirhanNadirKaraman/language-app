// Unit tests for the shared 401 handler in _http.ts (#14).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AUTH_EXPIRED_EVENT, assertOk, signalAuthExpired } from './_http';

function mockResponse(status: number, body: unknown = {}): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

describe('_http.ts assertOk', () => {
    beforeEach(() => {
        localStorage.setItem('auth_token', 'fake-token');
        localStorage.setItem('auth_email', 'fake@example.com');
    });

    afterEach(() => {
        localStorage.clear();
    });

    it('returns without throwing for 2xx', async () => {
        await expect(assertOk(mockResponse(200))).resolves.toBeUndefined();
        // Auth state untouched
        expect(localStorage.getItem('auth_token')).toBe('fake-token');
    });

    it('throws on a non-401 error with the detail message', async () => {
        await expect(assertOk(mockResponse(422, { detail: 'bad input' })))
            .rejects.toThrow('bad input');
        // Non-auth errors do NOT clear the token
        expect(localStorage.getItem('auth_token')).toBe('fake-token');
    });

    it('on 401 token_expired: clears auth, fires auth:expired, throws', async () => {
        const listener = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, listener);

        await expect(assertOk(mockResponse(401, { detail: 'token_expired' })))
            .rejects.toThrow('token_expired');

        expect(localStorage.getItem('auth_token')).toBeNull();
        expect(localStorage.getItem('auth_email')).toBeNull();
        expect(listener).toHaveBeenCalledTimes(1);
        // CustomEvent should carry { reason: 'expired' }
        const evt = listener.mock.calls[0][0] as CustomEvent<{ reason: string }>;
        expect(evt.detail.reason).toBe('expired');

        window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
    });

    it('on generic 401: clears auth, fires auth:expired with reason=unauthorized', async () => {
        const listener = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, listener);

        await expect(assertOk(mockResponse(401, { detail: 'Invalid token' })))
            .rejects.toThrow();

        expect(localStorage.getItem('auth_token')).toBeNull();
        expect(listener).toHaveBeenCalledTimes(1);
        const evt = listener.mock.calls[0][0] as CustomEvent<{ reason: string }>;
        expect(evt.detail.reason).toBe('unauthorized');

        window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
    });

    it('signalAuthExpired clears auth and dispatches the event', () => {
        const listener = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, listener);

        signalAuthExpired('expired');

        expect(localStorage.getItem('auth_token')).toBeNull();
        expect(localStorage.getItem('auth_email')).toBeNull();
        expect(listener).toHaveBeenCalledTimes(1);

        window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
    });
});
