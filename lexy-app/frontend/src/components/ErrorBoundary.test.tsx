import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ErrorBoundary } from './ErrorBoundary';

vi.mock('../api/clientErrors', () => ({
    reportClientError: vi.fn(() => Promise.resolve()),
}));

// eslint-disable-next-line import/first
import { reportClientError } from '../api/clientErrors';
const mockedReport = vi.mocked(reportClientError);

function Boom({ message = 'kaboom' }: { message?: string }): never {
    throw new Error(message);
}

describe('ErrorBoundary', () => {
    beforeEach(() => {
        mockedReport.mockClear();
        mockedReport.mockImplementation(() => Promise.resolve());
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

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

    it('reports the error to the backend with message, stack, component_stack, url, user_agent', () => {
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

        render(
            <ErrorBoundary>
                <Boom message="report me" />
            </ErrorBoundary>
        );

        expect(mockedReport).toHaveBeenCalledTimes(1);
        const payload = mockedReport.mock.calls[0][0];
        expect(payload.message).toBe('report me');
        expect(typeof payload.stack === 'string' || payload.stack === null).toBe(true);
        // component_stack is supplied by React's ErrorInfo — should be a string.
        expect(typeof payload.component_stack).toBe('string');
        expect(payload.url).toBe(window.location.href);
        expect(payload.user_agent).toBe(navigator.userAgent);

        spy.mockRestore();
    });

    it('report failure does not break the fallback UI', () => {
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
        // reportClientError is documented as never-throwing, but defensive:
        // even if it returns a rejected promise, the boundary must still
        // render its fallback synchronously.
        mockedReport.mockImplementation(() => Promise.reject(new Error('net down')));

        render(
            <ErrorBoundary>
                <Boom message="still falls back" />
            </ErrorBoundary>
        );

        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText('still falls back')).toBeInTheDocument();

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
