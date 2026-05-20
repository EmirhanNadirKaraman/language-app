/**
 * API base-URL helper.
 *
 * Web / PWA build: `VITE_API_BASE_URL` is unset → `apiUrl('/api/v1/foo')`
 * returns `/api/v1/foo` (same-origin; Vite dev proxy or production reverse
 * proxy handles routing to the backend).
 *
 * Capacitor / native build: `VITE_API_BASE_URL=https://api.example.com` →
 * `apiUrl('/api/v1/foo')` returns `https://api.example.com/api/v1/foo`. The
 * WebView origin is `capacitor://localhost`, so same-origin paths can't
 * reach the backend.
 *
 * Rules:
 *   - Empty / missing base: return path unchanged (after normalising leading slash).
 *   - Non-empty base: trim a trailing slash, ensure path has a leading slash, join.
 *   - Never produces a double slash between base and path.
 *   - Preserves query strings and fragments (they're part of the path arg).
 *
 * Examples (with VITE_API_BASE_URL='https://api.example.com'):
 *   apiUrl('/api/v1/foo')           → 'https://api.example.com/api/v1/foo'
 *   apiUrl('api/v1/foo')            → 'https://api.example.com/api/v1/foo'
 *   apiUrl('/api/v1/foo?x=1')       → 'https://api.example.com/api/v1/foo?x=1'
 *
 * Examples (with VITE_API_BASE_URL unset or ''):
 *   apiUrl('/api/v1/foo')           → '/api/v1/foo'
 *   apiUrl('api/v1/foo')            → '/api/v1/foo'  (still ensures leading /)
 */

export const API_BASE_URL: string =
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ?? '';

export function apiUrl(path: string): string {
    const normalised = path.startsWith('/') ? path : `/${path}`;
    return API_BASE_URL ? `${API_BASE_URL}${normalised}` : normalised;
}
