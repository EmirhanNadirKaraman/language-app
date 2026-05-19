/**
 * #27g — BookLibraryPage mobile regression guards.
 *
 * Load-bearing invariants:
 *   - Title input uses fontSize: 16px (iOS focus-zoom guard).
 *   - Language select uses fontSize: 16px (iOS focus-zoom guard).
 *   - Upload submit button has minHeight: 44px.
 *   - Close × is 44×44.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { BookLibraryPage } from './BookLibraryPage';
import * as booksApi from '../api/books';

beforeEach(() => {
    vi.spyOn(booksApi, 'listBooks').mockResolvedValue([]);
});

afterEach(() => {
    vi.restoreAllMocks();
});

async function renderLib() {
    const utils = render(
        <BookLibraryPage token="t" onOpen={() => {}} onClose={() => {}} darkMode={false} />,
    );
    // Wait for listBooks() to resolve so the initial loading paint is finished.
    await waitFor(() => {
        expect(screen.getByTestId('book-upload-title')).toBeTruthy();
    });
    return utils;
}

describe('BookLibraryPage mobile (#27g)', () => {
    it('title input has fontSize: 16px and minHeight: 44px', async () => {
        await renderLib();
        const title = screen.getByTestId('book-upload-title') as HTMLInputElement;
        expect(title.style.fontSize).toBe('16px');
        expect(title.style.minHeight).toBe('44px');
    });

    it('language select has fontSize: 16px and minHeight: 44px', async () => {
        await renderLib();
        const lang = screen.getByTestId('book-upload-language') as HTMLSelectElement;
        expect(lang.style.fontSize).toBe('16px');
        expect(lang.style.minHeight).toBe('44px');
    });

    it('upload submit button has minHeight: 44px', async () => {
        await renderLib();
        const submit = screen.getByTestId('book-upload-submit') as HTMLElement;
        expect(submit.style.minHeight).toBe('44px');
    });

    it('close button is 44×44', async () => {
        await renderLib();
        const close = screen.getByTestId('book-library-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
    });
});
