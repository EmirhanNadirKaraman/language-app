/**
 * Tests for the apiUrl helper.
 *
 * Vitest evaluates the module under test once per test file, so
 * `API_BASE_URL` captures the value of `import.meta.env.VITE_API_BASE_URL`
 * at module load. To exercise the "non-empty base" branch we re-import
 * the module with a stubbed env, using `vi.resetModules()` between cases.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
});

async function importHelper(base?: string) {
    if (base === undefined) {
        vi.stubEnv('VITE_API_BASE_URL', '');
    } else {
        vi.stubEnv('VITE_API_BASE_URL', base);
    }
    vi.resetModules();
    return await import('./_baseUrl');
}

describe('apiUrl — empty base (web/PWA default)', () => {
    it('returns path unchanged when base is unset', async () => {
        const { apiUrl } = await importHelper(undefined);
        expect(apiUrl('/api/v1/test')).toBe('/api/v1/test');
    });

    it('still ensures leading slash on a path without one', async () => {
        const { apiUrl } = await importHelper(undefined);
        expect(apiUrl('api/v1/test')).toBe('/api/v1/test');
    });

    it('preserves query strings', async () => {
        const { apiUrl } = await importHelper(undefined);
        expect(apiUrl('/api/v1/search?q=hund&lang=de')).toBe('/api/v1/search?q=hund&lang=de');
    });

    it('exposes API_BASE_URL as empty string', async () => {
        const { API_BASE_URL } = await importHelper(undefined);
        expect(API_BASE_URL).toBe('');
    });
});

describe('apiUrl — non-empty base (Capacitor/native)', () => {
    it('prefixes path with the base URL', async () => {
        const { apiUrl } = await importHelper('https://api.example.com');
        expect(apiUrl('/api/v1/test')).toBe('https://api.example.com/api/v1/test');
    });

    it('handles base with a trailing slash (trims it)', async () => {
        const { apiUrl } = await importHelper('https://api.example.com/');
        expect(apiUrl('/api/v1/test')).toBe('https://api.example.com/api/v1/test');
    });

    it('handles base with MULTIPLE trailing slashes', async () => {
        const { apiUrl } = await importHelper('https://api.example.com///');
        expect(apiUrl('/api/v1/test')).toBe('https://api.example.com/api/v1/test');
    });

    it('ensures path leading slash even when missing', async () => {
        const { apiUrl } = await importHelper('https://api.example.com');
        expect(apiUrl('api/v1/test')).toBe('https://api.example.com/api/v1/test');
    });

    it('never produces a double slash between base and path', async () => {
        const { apiUrl } = await importHelper('https://api.example.com/');
        // Verify with a path that already starts with /.
        const result = apiUrl('/api/v1/test');
        expect(result).not.toMatch(/[^:]\/\//); // ignore the `https://`
    });

    it('preserves query strings on prefixed paths', async () => {
        const { apiUrl } = await importHelper('https://api.example.com');
        expect(apiUrl('/api/v1/search?q=hund&lang=de'))
            .toBe('https://api.example.com/api/v1/search?q=hund&lang=de');
    });

    it('exposes API_BASE_URL as the trimmed base', async () => {
        const { API_BASE_URL } = await importHelper('https://api.example.com/');
        expect(API_BASE_URL).toBe('https://api.example.com');
    });
});

describe('apiUrl — integration: api/auth.login uses the helper', () => {
    it('hits the prefixed URL when VITE_API_BASE_URL is set', async () => {
        vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com');
        vi.resetModules();

        const seen: string[] = [];
        const fetchSpy = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
            seen.push(typeof input === 'string' ? input : input.toString());
            return new Response(JSON.stringify({ access_token: 'xxx' }), {
                status: 200, headers: { 'Content-Type': 'application/json' },
            });
        });
        vi.stubGlobal('fetch', fetchSpy);

        const auth = await import('./auth');
        await auth.login('user@example.com', 'pw');

        expect(seen).toEqual(['https://api.example.com/api/v1/auth/login']);

        vi.unstubAllGlobals();
    });

    it('hits the same-origin URL when VITE_API_BASE_URL is empty', async () => {
        vi.stubEnv('VITE_API_BASE_URL', '');
        vi.resetModules();

        const seen: string[] = [];
        const fetchSpy = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
            seen.push(typeof input === 'string' ? input : input.toString());
            return new Response(JSON.stringify({ access_token: 'xxx' }), {
                status: 200, headers: { 'Content-Type': 'application/json' },
            });
        });
        vi.stubGlobal('fetch', fetchSpy);

        const auth = await import('./auth');
        await auth.login('user@example.com', 'pw');

        expect(seen).toEqual(['/api/v1/auth/login']);

        vi.unstubAllGlobals();
    });
});
