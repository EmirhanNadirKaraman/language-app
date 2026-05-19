import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    message:  string | null;
}

/**
 * Catches render errors in the routed subtree so a single bad component
 * doesn't white-screen the whole app. Mounted around <Outlet/> in App.tsx
 * — the navbar / auth state / Layout chrome are NOT inside the boundary,
 * so the user can navigate away or sign out even after a route crashes.
 *
 * Intentionally minimal:
 *   - logs to console.error (no telemetry endpoint yet)
 *   - shows a one-line message + Reload button
 *   - no auto-recovery (forcing a hard reload is the safe option for now)
 */
export class ErrorBoundary extends Component<Props, State> {
    state: State = { hasError: false, message: null };

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, message: error.message || 'Unknown error' };
    }

    componentDidCatch(error: Error, info: ErrorInfo): void {
        // Future: ship this to a logging endpoint. For now, console is enough.
        console.error('ErrorBoundary caught:', error, info.componentStack);
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
                    border: '1px solid #e0e0e0',
                    borderRadius: '8px',
                    background: '#fff',
                    textAlign: 'center',
                    fontFamily: 'sans-serif',
                }}
            >
                <div style={{ fontSize: '16px', fontWeight: 600, color: '#c62828', marginBottom: '8px' }}>
                    Something went wrong.
                </div>
                {this.state.message && (
                    <div style={{ fontSize: '12px', color: '#666', marginBottom: '16px' }}>
                        {this.state.message}
                    </div>
                )}
                <button
                    onClick={this.handleReload}
                    style={{
                        padding: '8px 20px',
                        borderRadius: '6px',
                        border: '1px solid #c5cae9',
                        background: '#e8eaf6',
                        color: '#1a237e',
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
