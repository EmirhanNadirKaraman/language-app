import { Component, type ErrorInfo, type ReactNode } from 'react';

import { reportClientError } from '../api/clientErrors';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    message:  string | null;
}

// VITE_APP_VERSION is wired by Vite at build time when set; falls back to
// undefined in dev / when unset, in which case the backend stores NULL.
const RELEASE: string | undefined =
    (import.meta.env.VITE_APP_VERSION as string | undefined) || undefined;

/**
 * Catches render errors in the routed subtree so a single bad component
 * doesn't white-screen the whole app. Mounted around <Outlet/> in App.tsx
 * — the navbar / auth state / Layout chrome are NOT inside the boundary,
 * so the user can navigate away or sign out even after a route crashes.
 *
 * Behaviour:
 *   - logs to console.error
 *   - best-effort POST to /api/v1/errors/client (W7); failure never affects
 *     the fallback UI
 *   - shows a one-line message + Reload button
 *   - no auto-recovery (forcing a hard reload is the safe option for now)
 */
export class ErrorBoundary extends Component<Props, State> {
    state: State = { hasError: false, message: null };

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, message: error.message || 'Unknown error' };
    }

    componentDidCatch(error: Error, info: ErrorInfo): void {
        console.error('ErrorBoundary caught:', error, info.componentStack);

        // Fire-and-forget. reportClientError is contracted not to throw, but
        // we attach a no-op .catch defensively so a regression there can't
        // surface as an unhandled rejection on top of an already-crashed page.
        reportClientError({
            message: error.message || 'Unknown error',
            stack: error.stack ?? null,
            component_stack: info.componentStack ?? null,
            url: typeof window !== 'undefined' ? window.location.href : null,
            user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
            release: RELEASE ?? null,
        }).catch(() => {});
    }

    handleReload = (): void => {
        window.location.reload();
    };

    render(): ReactNode {
        if (!this.state.hasError) return this.props.children;

        return (
            <div
                role="alert"
                style={{
                    margin: '32px auto',
                    maxWidth: '480px',
                    padding: '24px',
                    border: '1px solid var(--color-border)',
                    borderRadius: '8px',
                    background: 'var(--color-surface)',
                    color: 'var(--color-text)',
                    textAlign: 'center',
                    fontFamily: 'sans-serif',
                }}
            >
                <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-danger)', marginBottom: '8px' }}>
                    Something went wrong.
                </div>
                {this.state.message && (
                    <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '16px' }}>
                        {this.state.message}
                    </div>
                )}
                <button
                    onClick={this.handleReload}
                    style={{
                        padding: '8px 20px',
                        borderRadius: '6px',
                        border: '1px solid var(--color-border-accent)',
                        background: 'var(--color-primary-soft)',
                        color: 'var(--color-primary-on-soft)',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: 'pointer',
                    }}
                >
                    Reload
                </button>
            </div>
        );
    }
}
