// Best-effort client crash reporter for the ErrorBoundary (W7).
//
// Contract:
//   - Never throws. The boundary is already in a crash path; making the report
//     path also fail would replace a useful fallback UI with a blank screen.
//   - Never returns a meaningful value. Callers fire-and-forget.
//   - Does NOT use assertOk / signalAuthExpired: a 401 here must not trigger
//     a global sign-out (the user wasn't trying to do anything auth-related).

import { apiUrl } from './_baseUrl';
import { getToken } from '../auth';

export interface ClientErrorPayload {
    message: string;
    stack?: string | null;
    component_stack?: string | null;
    url?: string | null;
    user_agent?: string | null;
    release?: string | null;
}

export async function reportClientError(payload: ClientErrorPayload): Promise<void> {
    try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) headers.Authorization = `Bearer ${token}`;

        await fetch(apiUrl('/api/v1/errors/client'), {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
            // Hint to the browser this should not delay unload; some browsers
            // ignore it for fetch(), which is fine — it's just a hint.
            keepalive: true,
        });
    } catch {
        // Swallow. The boundary already shows a fallback UI; surfacing a
        // network error here would replace it with a different crash.
        if (import.meta.env.DEV) {
            // eslint-disable-next-line no-console
            console.warn('reportClientError failed (suppressed)');
        }
    }
}
