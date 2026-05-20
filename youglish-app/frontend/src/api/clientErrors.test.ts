import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { reportClientError } from './clientErrors';

describe('reportClientError', () => {
    let fetchSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        fetchSpy = vi.spyOn(globalThis, 'fetch' as never) as unknown as ReturnType<typeof vi.spyOn>;
        localStorage.clear();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('POSTs the payload as JSON', async () => {
        fetchSpy.mockResolvedValue(new Response(null, { status: 204 }) as never);

        await reportClientError({ message: 'oh no' });

        expect(fetchSpy).toHaveBeenCalledTimes(1);
        const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
        expect(url).toContain('/api/v1/errors/client');
        expect(init.method).toBe('POST');
        expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
        expect(JSON.parse(init.body as string)).toEqual({ message: 'oh no' });
    });

    it('includes Authorization header when a token is stored', async () => {
        localStorage.setItem('auth_token', 'tok123');
        fetchSpy.mockResolvedValue(new Response(null, { status: 204 }) as never);

        await reportClientError({ message: 'auth crash' });

        const init = fetchSpy.mock.calls[0][1] as RequestInit;
        expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok123');
    });

    it('never throws when fetch rejects', async () => {
        fetchSpy.mockRejectedValue(new Error('network down'));

        await expect(reportClientError({ message: 'rejects' })).resolves.toBeUndefined();
    });

    it('never throws when fetch returns non-2xx', async () => {
        fetchSpy.mockResolvedValue(new Response('boom', { status: 500 }) as never);

        await expect(reportClientError({ message: '500' })).resolves.toBeUndefined();
    });
});
