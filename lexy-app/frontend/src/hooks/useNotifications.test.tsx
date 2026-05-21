/**
 * useNotifications lifecycle (audit fix C).
 *
 * Verifies the one-stream-per-hook invariant: every connection has its own
 * AbortController; unmount, token change, and intentional reconnect all
 * abort the prior fetch before starting a new one.
 *
 * Tests focus on lifecycle + abort behaviour, not on event-payload parsing
 * (already covered indirectly by NotificationToast + by manual dogfood).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useNotifications } from './useNotifications';

// A pending stream that never resolves until the AbortController fires.
// Mirrors the real SSE shape closely enough for the lifecycle checks:
// fetch() returns a Response whose .body.getReader().read() waits forever.
type FetchCall = {
    url: string | URL;
    signal: AbortSignal | undefined;
    aborted: boolean;
};

function makePendingFetch(calls: FetchCall[]) {
    return (url: string | URL, init?: RequestInit) => {
        const signal = init?.signal ?? undefined;
        const call: FetchCall = { url, signal, aborted: false };
        calls.push(call);

        // Reader: read() blocks until the signal aborts.
        const reader = {
            read: () =>
                new Promise<ReadableStreamReadResult<Uint8Array>>((_resolve, reject) => {
                    if (signal?.aborted) {
                        call.aborted = true;
                        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
                        return;
                    }
                    signal?.addEventListener('abort', () => {
                        call.aborted = true;
                        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
                    });
                }),
            cancel: vi.fn(),
        };

        const body = { getReader: () => reader } as unknown as ReadableStream<Uint8Array>;

        return Promise.resolve({
            ok: true,
            body,
        } as unknown as Response);
    };
}

let fetchMock: ReturnType<typeof vi.fn>;
let calls: FetchCall[];

beforeEach(() => {
    vi.useFakeTimers();
    calls = [];
    fetchMock = vi.fn(makePendingFetch(calls));
    vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('useNotifications — lifecycle (audit fix C)', () => {
    it('does not call fetch when token is null', () => {
        renderHook(() => useNotifications(null));
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('does not call fetch when token is empty string', () => {
        renderHook(() => useNotifications(''));
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('opens one fetch with an AbortSignal when token is set', async () => {
        renderHook(() => useNotifications('tok'));
        // Flush microtasks so connect() executes its first await.
        await act(async () => { await Promise.resolve(); });

        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(calls[0].signal).toBeInstanceOf(AbortSignal);
        expect(calls[0].signal?.aborted).toBe(false);
    });

    it('unmount aborts the active fetch signal', async () => {
        const { unmount } = renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); });
        expect(calls).toHaveLength(1);

        unmount();
        expect(calls[0].signal?.aborted).toBe(true);
    });

    it('changing the token aborts the previous signal and starts a new fetch', async () => {
        const { rerender } = renderHook(({ tok }: { tok: string }) => useNotifications(tok), {
            initialProps: { tok: 'tok-1' },
        });
        await act(async () => { await Promise.resolve(); });
        expect(calls).toHaveLength(1);
        const firstSignal = calls[0].signal;

        rerender({ tok: 'tok-2' });
        await act(async () => { await Promise.resolve(); });

        expect(firstSignal?.aborted).toBe(true);
        expect(calls.length).toBeGreaterThanOrEqual(2);
        // Newest signal must be live.
        expect(calls[calls.length - 1].signal?.aborted).toBe(false);
    });

    it('an aborted fetch (unmount) does not schedule a reconnect', async () => {
        const { unmount } = renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); });

        unmount();

        // Even after the reconnect window elapses, no second fetch.
        await act(async () => {
            vi.advanceTimersByTime(10_000);
            await Promise.resolve();
        });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('keeps exactly one live signal across StrictMode-style remount + token change', async () => {
        const { rerender, unmount } = renderHook(({ tok }: { tok: string }) => useNotifications(tok), {
            initialProps: { tok: 'a' },
        });
        await act(async () => { await Promise.resolve(); });
        rerender({ tok: 'b' });
        await act(async () => { await Promise.resolve(); });
        rerender({ tok: 'c' });
        await act(async () => { await Promise.resolve(); });

        // Every prior signal aborted; only the latest is live.
        const live = calls.filter(c => c.signal?.aborted === false);
        expect(live).toHaveLength(1);

        unmount();
        const liveAfterUnmount = calls.filter(c => c.signal?.aborted === false);
        expect(liveAfterUnmount).toHaveLength(0);
    });
});

describe('useNotifications — 401 handling', () => {
    function make401Fetch(calls: FetchCall[], detail: string | null) {
        return (url: string | URL, init?: RequestInit) => {
            const signal = init?.signal ?? undefined;
            calls.push({ url, signal, aborted: false });
            const bodyJson = detail !== null ? JSON.stringify({ detail }) : '';
            // Mimic a Response so res.clone().json() works.
            return Promise.resolve({
                ok: false,
                status: 401,
                body: null,
                clone() {
                    return {
                        json: () =>
                            detail !== null
                                ? Promise.resolve(JSON.parse(bodyJson))
                                : Promise.reject(new Error('not json')),
                    };
                },
            } as unknown as Response);
        };
    }

    it('dispatches auth:expired with reason "expired" on token_expired detail', async () => {
        calls = [];
        fetchMock = vi.fn(make401Fetch(calls, 'token_expired'));
        vi.stubGlobal('fetch', fetchMock);
        const handler = vi.fn();
        window.addEventListener('auth:expired', handler);

        renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); await Promise.resolve(); });

        expect(handler).toHaveBeenCalledTimes(1);
        const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
        expect(detail).toEqual({ reason: 'expired' });

        window.removeEventListener('auth:expired', handler);
    });

    it('dispatches auth:expired with reason "unauthorized" on generic 401', async () => {
        calls = [];
        fetchMock = vi.fn(make401Fetch(calls, 'Invalid token'));
        vi.stubGlobal('fetch', fetchMock);
        const handler = vi.fn();
        window.addEventListener('auth:expired', handler);

        renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); await Promise.resolve(); });

        expect(handler).toHaveBeenCalledTimes(1);
        const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
        expect(detail).toEqual({ reason: 'unauthorized' });

        window.removeEventListener('auth:expired', handler);
    });

    it('dispatches auth:expired with reason "unauthorized" on 401 with non-JSON body', async () => {
        calls = [];
        fetchMock = vi.fn(make401Fetch(calls, null));
        vi.stubGlobal('fetch', fetchMock);
        const handler = vi.fn();
        window.addEventListener('auth:expired', handler);

        renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); await Promise.resolve(); });

        expect(handler).toHaveBeenCalledTimes(1);
        const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
        expect(detail).toEqual({ reason: 'unauthorized' });

        window.removeEventListener('auth:expired', handler);
    });

    it('401 does not schedule a reconnect', async () => {
        calls = [];
        fetchMock = vi.fn(make401Fetch(calls, 'token_expired'));
        vi.stubGlobal('fetch', fetchMock);

        renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); await Promise.resolve(); });
        expect(calls).toHaveLength(1);

        // The reconnect window (and beyond) elapses — no additional fetch.
        await act(async () => {
            vi.advanceTimersByTime(30_000);
            await Promise.resolve();
        });
        expect(calls).toHaveLength(1);
    });
});

describe('useNotifications — reconnect on network failure', () => {
    function makeFailingFetch(calls: FetchCall[], failTimes: number) {
        let n = 0;
        return (url: string | URL, init?: RequestInit) => {
            const signal = init?.signal ?? undefined;
            const call: FetchCall = { url, signal, aborted: false };
            calls.push(call);
            if (n++ < failTimes) {
                return Promise.reject(new Error('network down'));
            }
            // After failures, return a pending stream (same shape as the
            // happy-path mock).
            return makePendingFetch([])(url, init);
        };
    }

    it('schedules a single reconnect after a failure (not many)', async () => {
        calls = [];
        fetchMock = vi.fn(makeFailingFetch(calls, 1));
        vi.stubGlobal('fetch', fetchMock);

        renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); });
        await act(async () => { await Promise.resolve(); });
        expect(calls).toHaveLength(1);

        // Advance just under the reconnect window: nothing yet.
        await act(async () => {
            vi.advanceTimersByTime(4_000);
            await Promise.resolve();
        });
        expect(calls).toHaveLength(1);

        // Cross the window: exactly one reconnect.
        await act(async () => {
            vi.advanceTimersByTime(2_000);
            await Promise.resolve();
            await Promise.resolve();
        });
        expect(calls).toHaveLength(2);
    });

    it('cleanup clears the pending reconnect timer (no fetch after unmount)', async () => {
        calls = [];
        fetchMock = vi.fn(makeFailingFetch(calls, 1));
        vi.stubGlobal('fetch', fetchMock);

        const { unmount } = renderHook(() => useNotifications('tok'));
        await act(async () => { await Promise.resolve(); });
        await act(async () => { await Promise.resolve(); });
        expect(calls).toHaveLength(1);

        // The failed fetch scheduled a reconnect; unmount must clear it.
        unmount();

        await act(async () => {
            vi.advanceTimersByTime(30_000);
            await Promise.resolve();
        });
        expect(calls).toHaveLength(1);
    });
});
