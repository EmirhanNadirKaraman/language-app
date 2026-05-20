/**
 * ReadingReviewPage tests (#5).
 *
 * Mocks `fetch` to drive the page through:
 *   - empty due queue → empty state
 *   - one due selection → render canonical/sentence/doc title + 3 action buttons
 *   - clicking each outcome posts to the correct endpoint with the correct body
 *   - after submit the next selection is shown; emptying the queue shows
 *     "session complete"
 *   - touch targets are ≥44px (mobile guard)
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ReadingReviewPage } from './ReadingReviewPage';
import type { DueSelectionItem } from '../types';


function makeSelection(overrides: Partial<DueSelectionItem> = {}): DueSelectionItem {
    return {
        selection_id: 'sel-1',
        doc_id: 'doc-1',
        doc_title: 'Effi Briest',
        canonical: 'Spaziergang',
        surface_text: 'Spaziergang',
        sentence_text: 'Sie machten einen langen Spaziergang im Garten.',
        note: null,
        review_count: 0,
        next_review_at: null,
        created_at: '2026-05-01T12:00:00Z',
        ...overrides,
    };
}


type FetchCall = { url: string; init: RequestInit | undefined };
const calls: FetchCall[] = [];

function installFetch(handler: (url: string, init: RequestInit | undefined) => Response | Promise<Response>) {
    const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = typeof input === 'string' ? input : input.toString();
        calls.push({ url, init });
        return handler(url, init);
    });
    vi.stubGlobal('fetch', stub);
    return stub;
}

function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}


describe('ReadingReviewPage', () => {
    beforeEach(() => {
        calls.length = 0;
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('shows empty state when no selections are due', async () => {
        installFetch(() => jsonResponse([]));
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() =>
            expect(screen.getByTestId('reading-review-empty')).toBeInTheDocument()
        );
        expect(screen.getByText(/Nothing due right now/i)).toBeInTheDocument();
    });

    it('renders selection card with canonical, sentence, and doc title', async () => {
        installFetch(() => jsonResponse([makeSelection()]));
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() =>
            expect(screen.getByTestId('reading-review-card')).toBeInTheDocument()
        );
        expect(screen.getByTestId('reading-review-canonical')).toHaveTextContent('Spaziergang');
        expect(screen.getByTestId('reading-review-sentence')).toHaveTextContent(
            /Sie machten einen langen Spaziergang/
        );
        expect(screen.getByText(/From Effi Briest/i)).toBeInTheDocument();
    });

    it('clicking "Got it" posts {outcome: "got_it"} to the review endpoint', async () => {
        installFetch((url) =>
            url.endsWith('/api/v1/reading/selections/due?limit=30')
                ? jsonResponse([makeSelection()])
                : jsonResponse(makeSelection({ status: 'learning' } as Partial<DueSelectionItem>))
        );
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-got-it')).toBeInTheDocument());
        await act(async () => {
            fireEvent.click(screen.getByTestId('reading-review-got-it'));
        });
        const reviewCall = calls.find(c => c.url.includes('/review'));
        expect(reviewCall).toBeDefined();
        expect(reviewCall!.url).toContain('/api/v1/reading/selections/sel-1/review');
        expect(JSON.parse(reviewCall!.init!.body as string)).toEqual({ outcome: 'got_it' });
    });

    it('clicking "Still learning" posts {outcome: "still_learning"}', async () => {
        installFetch((url) =>
            url.endsWith('/api/v1/reading/selections/due?limit=30')
                ? jsonResponse([makeSelection()])
                : jsonResponse({})
        );
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-still-learning')).toBeInTheDocument());
        await act(async () => {
            fireEvent.click(screen.getByTestId('reading-review-still-learning'));
        });
        const reviewCall = calls.find(c => c.url.includes('/review'));
        expect(JSON.parse(reviewCall!.init!.body as string)).toEqual({ outcome: 'still_learning' });
    });

    it('clicking "Mastered" posts {outcome: "mastered"}', async () => {
        installFetch((url) =>
            url.endsWith('/api/v1/reading/selections/due?limit=30')
                ? jsonResponse([makeSelection()])
                : jsonResponse({})
        );
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-mastered')).toBeInTheDocument());
        await act(async () => {
            fireEvent.click(screen.getByTestId('reading-review-mastered'));
        });
        const reviewCall = calls.find(c => c.url.includes('/review'));
        expect(JSON.parse(reviewCall!.init!.body as string)).toEqual({ outcome: 'mastered' });
    });

    it('after submitting the last selection, shows the "Session complete" panel', async () => {
        installFetch((url) =>
            url.endsWith('/api/v1/reading/selections/due?limit=30')
                ? jsonResponse([makeSelection()])
                : jsonResponse({})
        );
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-got-it')).toBeInTheDocument());
        await act(async () => {
            fireEvent.click(screen.getByTestId('reading-review-got-it'));
        });
        await waitFor(() =>
            expect(screen.getByTestId('reading-review-session-complete')).toBeInTheDocument()
        );
        expect(screen.getByText(/1 selection reviewed/i)).toBeInTheDocument();
    });

    it('advances to the next selection after submit', async () => {
        const sel1 = makeSelection({ selection_id: 'sel-1', canonical: 'Apfel' });
        const sel2 = makeSelection({ selection_id: 'sel-2', canonical: 'Birne' });
        installFetch((url) =>
            url.endsWith('/api/v1/reading/selections/due?limit=30')
                ? jsonResponse([sel1, sel2])
                : jsonResponse({})
        );
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-canonical')).toHaveTextContent('Apfel'));
        await act(async () => {
            fireEvent.click(screen.getByTestId('reading-review-got-it'));
        });
        await waitFor(() =>
            expect(screen.getByTestId('reading-review-canonical')).toHaveTextContent('Birne')
        );
    });

    it('all three outcome buttons meet the 44px touch-target minimum', async () => {
        installFetch(() => jsonResponse([makeSelection()]));
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-got-it')).toBeInTheDocument());
        for (const tid of ['reading-review-still-learning', 'reading-review-got-it', 'reading-review-mastered']) {
            const btn = screen.getByTestId(tid) as HTMLElement;
            expect(btn.style.minHeight).toBe('44px');
        }
        const closeBtn = screen.getByTestId('reading-review-close') as HTMLElement;
        expect(closeBtn.style.minWidth).toBe('44px');
        expect(closeBtn.style.minHeight).toBe('44px');
    });

    it('shows error message when the review POST fails', async () => {
        installFetch((url) =>
            url.endsWith('/api/v1/reading/selections/due?limit=30')
                ? jsonResponse([makeSelection()])
                : new Response('boom', { status: 500 })
        );
        render(<ReadingReviewPage token="tok" onClose={() => {}} />);
        await waitFor(() => expect(screen.getByTestId('reading-review-got-it')).toBeInTheDocument());
        await act(async () => {
            fireEvent.click(screen.getByTestId('reading-review-got-it'));
        });
        await waitFor(() =>
            expect(screen.getByTestId('reading-review-error')).toBeInTheDocument()
        );
    });
});
