import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ErrorBoundary } from './ErrorBoundary';

function Boom({ message = 'kaboom' }: { message?: string }): never {
    throw new Error(message);
}

describe('ErrorBoundary', () => {
    it('renders children when no error', () => {
        render(
            <ErrorBoundary>
                <div>healthy content</div>
            </ErrorBoundary>
        );
        expect(screen.getByText('healthy content')).toBeInTheDocument();
    });

    it('shows fallback when a child throws during render', () => {
        // React logs the error to console.error; silence it for the test output.
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

        render(
            <ErrorBoundary>
                <Boom message="render exploded" />
            </ErrorBoundary>
        );

        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText('Something went wrong.')).toBeInTheDocument();
        expect(screen.getByText('render exploded')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();

        spy.mockRestore();
    });

    it('Reload button calls window.location.reload', () => {
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
        const reloadSpy = vi.fn();
        // jsdom's location is a real Location object; replace .reload via Object.defineProperty.
        Object.defineProperty(window, 'location', {
            value: { ...window.location, reload: reloadSpy },
            writable: true,
        });

        render(
            <ErrorBoundary>
                <Boom />
            </ErrorBoundary>
        );
        fireEvent.click(screen.getByRole('button', { name: /reload/i }));

        expect(reloadSpy).toHaveBeenCalledTimes(1);

        spy.mockRestore();
    });
});
