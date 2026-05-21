/**
 * #27d — BookReaderPage mobile regression guards.
 *
 * BookReaderPage is the largest single component (~1100 lines) and pulls a lot
 * of network + ref machinery on mount. These tests use the same exported style
 * helpers + a minimal mock for the page-fetch flow to verify the load-bearing
 * mobile invariants without rendering a full page of blocks.
 *
 * Load-bearing invariants:
 *   - Page-nav arrow buttons are 44×44 (primary nav).
 *   - Top-bar chrome buttons (Back, Mode toggle, Scan, Saved, Edit, Dark/Light) are ≥36px.
 *   - Page input has fontSize: 16px (iOS focus-zoom guard).
 *   - Content area uses column flow on mobile, row on desktop.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { BookReaderPage } from './BookReaderPage';
import type { BookDocument } from '../types';
import * as readingApi from '../api/reading';
import * as booksApi from '../api/books';

const DOC: BookDocument = {
    doc_id:       '11111111-1111-1111-1111-111111111111',
    user_id:      'u',
    title:        'Test Book',
    filename:     'test.pdf',
    total_pages:  3,
    language:     'de',
    source_type:  'pdf_text',
    status:       'ready',
    error_message: null,
    created_at:   new Date().toISOString(),
    updated_at:   new Date().toISOString(),
};

beforeEach(() => {
    // Stub the page-fetch flow so the component reaches its rendered state
    // without real network calls.
    vi.spyOn(booksApi, 'getPage').mockResolvedValue({
        page_id: 'p1', doc_id: DOC.doc_id, page_number: 1, sentence_count: 0,
        blocks: [], has_image: false,
    } as never);
    vi.spyOn(booksApi, 'listPages').mockResolvedValue([
        { page_id: 'p1', doc_id: DOC.doc_id, page_number: 1, sentence_count: 0 },
        { page_id: 'p2', doc_id: DOC.doc_id, page_number: 2, sentence_count: 0 },
        { page_id: 'p3', doc_id: DOC.doc_id, page_number: 3, sentence_count: 0 },
    ] as never);
    vi.spyOn(readingApi, 'getPageWordStatuses').mockResolvedValue({});
    vi.spyOn(readingApi, 'getPageSelections').mockResolvedValue([]);
    vi.spyOn(readingApi, 'listAllSelections').mockResolvedValue([]);

    // Default to NOT mobile so existing-layout tests stay deterministic;
    // individual tests override with vi.stubGlobal('matchMedia', ...).
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((q: string) => ({
        matches: false,
        media: q,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => true,
    })));
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

async function renderReader() {
    const utils = render(
        <BookReaderPage
            token="t"
            doc={DOC}
            onClose={() => {}}
            autoMarkKnown={false}
        />,
    );
    // Wait until the page-fetch resolves and either the reader pane or its
    // "Loading page…" placeholder is gone — the testids exist either way.
    await waitFor(() => {
        expect(utils.queryByTestId('book-content-area')).toBeTruthy();
    });
    return utils;
}

describe('BookReaderPage mobile (#27d)', () => {
    it('page input has fontSize: 16px (iOS focus-zoom guard)', async () => {
        await renderReader();
        const input = screen.getByTestId('book-page-input') as HTMLInputElement;
        expect(input.style.fontSize).toBe('16px');
        expect(input.style.minHeight).toBe('44px');
    });

    it('page-nav arrows are 44×44', async () => {
        await renderReader();
        // The arrow buttons render the literal ◀ / ▶ glyphs; find by text.
        const prev = screen.getByText('◀') as HTMLElement;
        const next = screen.getByText('▶') as HTMLElement;
        expect(prev.style.minWidth).toBe('44px');
        expect(prev.style.minHeight).toBe('44px');
        expect(next.style.minWidth).toBe('44px');
        expect(next.style.minHeight).toBe('44px');
    });

    it('Back button has at least 44px minHeight', async () => {
        await renderReader();
        const back = screen.getByTestId('book-back') as HTMLElement;
        expect(back.style.minHeight).toBe('44px');
    });

    it('content area uses row flow on desktop', async () => {
        await renderReader();
        const area = screen.getByTestId('book-content-area') as HTMLElement;
        expect(area.style.flexDirection).toBe('row');
    });

    it('content area uses column flow on mobile', async () => {
        // Override matchMedia BEFORE render so useViewport picks up isMobile=true.
        vi.stubGlobal('matchMedia', vi.fn().mockImplementation((q: string) => ({
            matches: q.includes('max-width: 768px'),
            media: q,
            addEventListener: () => {}, removeEventListener: () => {},
            addListener: () => {}, removeListener: () => {},
            dispatchEvent: () => true,
        })));
        await renderReader();
        const area = screen.getByTestId('book-content-area') as HTMLElement;
        expect(area.style.flexDirection).toBe('column');
    });

    it('top-bar Mode toggle buttons are at least 36px', async () => {
        await renderReader();
        const page = screen.getByRole('button', { name: 'Page' }) as HTMLElement;
        const sentence = screen.getByRole('button', { name: 'Sentence' }) as HTMLElement;
        expect(page.style.minHeight).toBe('36px');
        expect(sentence.style.minHeight).toBe('36px');
    });
});
