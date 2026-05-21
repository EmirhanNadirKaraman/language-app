import { useEffect, useRef, useState } from 'react';
import { apiUrl } from '../api/_baseUrl';
import { signalAuthExpired } from '../api/_http';

export interface AppNotification {
    id: string;
    // Scraper-emitted types (CLAUDE.md §10):
    //   'video_done'     — single video added
    //   'channel_done'   — channel scan finished, N videos added
    //   'request_failed' — content_request status flipped to 'failed'; payload.reason
    //                       carries the error string set by _mark_request
    type: 'video_done' | 'channel_done' | 'request_failed';
    payload: Record<string, unknown>;
}

const RECONNECT_MS = 5000;

export function useNotifications(token: string | null) {
    const [notifications, setNotifications] = useState<AppNotification[]>([]);

    // Audit fix C: lifecycle of the SSE stream.
    //
    // Invariant: ONE hook instance has at most one live fetch. Previously
    // reconnect-on-error scheduled `setTimeout(connect, 5000)` without
    // aborting the in-flight fetch/reader, so transient network blips could
    // leak readers. The new shape:
    //   - One AbortController per connection. Stored in a ref so cleanup
    //     and reconnect can both abort.
    //   - Reconnect timer in a ref so unmount can clear it.
    //   - `signal.aborted` is the single source of truth for "intentional
    //     teardown — do NOT reconnect."
    const controllerRef       = useRef<AbortController | null>(null);
    const reconnectTimerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        if (!token) return;

        // Abort any in-flight reader before starting a new one. This handles
        // the StrictMode double-mount and the token-change case the same way.
        function abortInFlight() {
            if (controllerRef.current) {
                controllerRef.current.abort();
                controllerRef.current = null;
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
        }

        async function connect() {
            // Defensive: a prior loop may have raced past abortInFlight.
            // Clear and start fresh.
            abortInFlight();

            const controller = new AbortController();
            controllerRef.current = controller;

            try {
                const res = await fetch(apiUrl('/api/v1/notifications/stream'), {
                    headers: { Authorization: `Bearer ${token}` },
                    signal: controller.signal,
                });
                if (controller.signal.aborted) return;
                // 401: token expired or otherwise invalid. Surface to the rest
                // of the app via auth:expired (matches the _http.ts contract)
                // instead of reconnecting silently every 5s forever. The token
                // state in App.tsx will flip to null and this hook will
                // unmount its current effect cleanly on the next render.
                if (res.status === 401) {
                    let detail = '';
                    try {
                        const body = await res.clone().json() as { detail?: unknown };
                        if (typeof body?.detail === 'string') detail = body.detail;
                    } catch {
                        // body wasn't JSON; treat as generic 401.
                    }
                    signalAuthExpired(detail === 'token_expired' ? 'expired' : 'unauthorized');
                    return;
                }
                if (!res.ok || !res.body) {
                    scheduleReconnect(controller);
                    return;
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                // The reader read loop. We bail on abort (intentional
                // teardown / token change / new connection) without
                // scheduling a reconnect.
                while (!controller.signal.aborted) {
                    let chunk: ReadableStreamReadResult<Uint8Array>;
                    try {
                        chunk = await reader.read();
                    } catch (err) {
                        // AbortError is fine — caller intentionally tore down.
                        if (!controller.signal.aborted) {
                            // Network error: schedule one reconnect.
                            scheduleReconnect(controller);
                        }
                        // Silently absorb the aborted-read error either way.
                        void err;
                        return;
                    }

                    if (chunk.done) break;
                    if (!chunk.value) continue;

                    buffer += decoder.decode(chunk.value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() ?? '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        try {
                            const event = JSON.parse(line.slice(6));
                            setNotifications(prev => [
                                ...prev,
                                {
                                    id: crypto.randomUUID(),
                                    type: event.type,
                                    payload: event.payload,
                                },
                            ]);
                        } catch {
                            // malformed event — ignore
                        }
                    }
                }

                // Stream ended cleanly (server closed). Reconnect unless we
                // were aborted.
                if (!controller.signal.aborted) {
                    scheduleReconnect(controller);
                }
            } catch (err) {
                // AbortError on the initial fetch is the cleanup path — do
                // not reconnect and do not surface.
                if (!controller.signal.aborted) {
                    scheduleReconnect(controller);
                }
                void err;
            }
        }

        function scheduleReconnect(forController: AbortController) {
            // Guard: don't schedule if this controller was aborted between
            // the failure and now (e.g. unmount during the network roundtrip).
            if (forController.signal.aborted) return;
            // Guard: only ever one pending timer.
            if (reconnectTimerRef.current) return;
            reconnectTimerRef.current = setTimeout(() => {
                reconnectTimerRef.current = null;
                connect();
            }, RECONNECT_MS);
        }

        connect();

        return () => {
            abortInFlight();
        };
    }, [token]);

    function dismiss(id: string) {
        setNotifications(prev => prev.filter(n => n.id !== id));
    }

    return { notifications, dismiss };
}
