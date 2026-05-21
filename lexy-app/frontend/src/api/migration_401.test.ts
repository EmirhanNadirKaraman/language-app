// Shared-handler regression tests (#14).
//
// Confirms the migrated API clients route 401s through the shared
// `signalAuthExpired` flow in _http.ts. We test a representative spread:
//   * srs.ts (mid-session SRS review — token expiry here was the worst
//     user-visible bug before migration)
//   * reminders.ts (GET → assertOkJson)
//   * words.ts setWordStatus (PUT → assertOk void return)
//
// Per the audit-fix-C pattern: tests subscribe to AUTH_EXPIRED_EVENT
// directly and assert the reason in the CustomEvent detail.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getDueCards, submitReviewAnswer } from './srs';
import { getReminderSummary } from './reminders';
import { setWordStatus } from './words';

const AUTH_EXPIRED_EVENT = 'auth:expired';

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

beforeEach(() => {
    localStorage.setItem('auth_token', 'fake-token');
    localStorage.setItem('auth_email', 'fake@example.com');
});

afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('migrated API clients — happy path', () => {
    it('srs.getDueCards returns parsed JSON on 2xx', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(200, [{ card_id: 1, prompt_text: 'p', answer_text: 'a' }]),
        ));
        const out = await getDueCards('tok', 'de', 5);
        expect(Array.isArray(out)).toBe(true);
        expect(out[0].card_id).toBe(1);
    });

    it('reminders.getReminderSummary returns parsed JSON on 2xx', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(200, {
                srs_due_count: 3, reading_due_count: 0, learning_item_count: 7,
                total_due: 3, has_anything_due: true,
            }),
        ));
        const out = await getReminderSummary('tok');
        expect(out.srs_due_count).toBe(3);
    });

    it('words.setWordStatus resolves cleanly on 204 (no JSON body)', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            new Response(null, { status: 204 }),
        ));
        await expect(setWordStatus('tok', 42, 'learning')).resolves.toBeUndefined();
    });
});

describe('migrated API clients — 401 token_expired', () => {
    it('srs.getDueCards dispatches auth:expired with reason="expired"', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(401, { detail: 'token_expired' }),
        ));
        const handler = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, handler);

        await expect(getDueCards('tok', 'de', 5)).rejects.toThrow();

        expect(handler).toHaveBeenCalledTimes(1);
        const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
        expect(detail).toEqual({ reason: 'expired' });
        expect(localStorage.getItem('auth_token')).toBeNull();

        window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
    });

    it('srs.submitReviewAnswer (assertOk path) dispatches auth:expired on token_expired', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(401, { detail: 'token_expired' }),
        ));
        const handler = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, handler);

        await expect(submitReviewAnswer('tok', 1, true)).rejects.toThrow();
        expect(handler).toHaveBeenCalledTimes(1);
        expect((handler.mock.calls[0][0] as CustomEvent).detail.reason).toBe('expired');

        window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
    });
});

describe('migrated API clients — generic 401', () => {
    it('words.setWordStatus on generic 401 dispatches "unauthorized"', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(401, { detail: 'Invalid token' }),
        ));
        const handler = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, handler);

        await expect(setWordStatus('tok', 42, 'learning')).rejects.toThrow();
        expect(handler).toHaveBeenCalledTimes(1);
        expect((handler.mock.calls[0][0] as CustomEvent).detail.reason).toBe('unauthorized');
        expect(localStorage.getItem('auth_token')).toBeNull();

        window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
    });

    it('reminders.getReminderSummary on generic 401 dispatches "unauthorized"', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(401, { detail: 'Invalid token' }),
        ));
        const handler = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, handler);

        await expect(getReminderSummary('tok')).rejects.toThrow();
        expect(handler).toHaveBeenCalledTimes(1);
        expect((handler.mock.calls[0][0] as CustomEvent).detail.reason).toBe('unauthorized');

        window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
    });
});

describe('migrated API clients — non-401 errors do NOT clear auth', () => {
    it('5xx throws but leaves auth_token in place', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse(500, { detail: 'internal' }),
        ));
        const handler = vi.fn();
        window.addEventListener(AUTH_EXPIRED_EVENT, handler);

        await expect(getReminderSummary('tok')).rejects.toThrow('internal');

        expect(handler).not.toHaveBeenCalled();
        expect(localStorage.getItem('auth_token')).toBe('fake-token');

        window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
    });
});
