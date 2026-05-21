/**
 * #27f — ContentRequestPage mobile regression guards.
 *
 * Load-bearing invariants:
 *   - Input fontSize >= 16px (iOS focus-zoom guard).
 *   - Submit button minHeight >= 44px.
 *   - Channel/Video toggle row wraps on narrow phones.
 *   - Close button is 44×44.
 *   - Submit still fires (behaviour preserved).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ContentRequestPage } from './ContentRequestPage';
import * as api from '../api/contentRequests';

beforeEach(() => {
    vi.spyOn(api, 'listContentRequests').mockResolvedValue([]);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('ContentRequestPage mobile (#27f)', () => {
    it('content ID input has fontSize: 16px and minHeight: 44px', () => {
        render(<ContentRequestPage token="t" onClose={() => {}} />);
        const input = screen.getByTestId('content-request-input') as HTMLInputElement;
        expect(input.style.fontSize).toBe('16px');
        expect(input.style.minHeight).toBe('44px');
    });

    it('submit button has minHeight: 44px', () => {
        render(<ContentRequestPage token="t" onClose={() => {}} />);
        const submit = screen.getByTestId('content-request-submit') as HTMLElement;
        expect(submit.style.minHeight).toBe('44px');
    });

    it('Channel/Video toggle row uses flex-wrap', () => {
        const { container } = render(<ContentRequestPage token="t" onClose={() => {}} />);
        const channelBtn = screen.getByRole('button', { name: 'Channel' });
        const row = channelBtn.parentElement as HTMLElement;
        expect(row.style.flexWrap).toBe('wrap');
        // Sanity that we picked the right element — same row contains both buttons.
        expect(container.contains(screen.getByRole('button', { name: 'Video' }))).toBe(true);
    });

    it('close button is 44×44 and dismisses', () => {
        const onClose = vi.fn();
        render(<ContentRequestPage token="t" onClose={onClose} />);
        const close = screen.getByTestId('content-request-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
        fireEvent.click(close);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('submit calls submitContentRequest with the typed ID (behaviour preserved)', async () => {
        const submit = vi.spyOn(api, 'submitContentRequest').mockResolvedValue({
            request_id: 1, request_type: 'channel', content_id: 'UCabc',
            status: 'pending', error: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
        });
        render(<ContentRequestPage token="t" onClose={() => {}} />);

        const input = screen.getByTestId('content-request-input') as HTMLInputElement;
        fireEvent.change(input, { target: { value: 'UCabc' } });
        fireEvent.click(screen.getByTestId('content-request-submit'));

        await waitFor(() => expect(submit).toHaveBeenCalledWith('t', 'channel', 'UCabc'));
    });
});


describe('ContentRequestPage detected-language note (Stage 5)', () => {
    it('renders the detected-language note before the form', () => {
        render(<ContentRequestPage token="t" onClose={() => {}} />);
        const note = screen.getByTestId('content-request-language-note');
        expect(note).toBeInTheDocument();
        // Key signals — language-neutral wording about the active learning
        // language. The exact copy can evolve; assert the load-bearing
        // phrases that make the policy unambiguous.
        expect(note.textContent).toMatch(/detected/i);
        expect(note.textContent).toMatch(/subtitles/i);
        expect(note.textContent).toMatch(/active learning language/i);
    });

    it('language note appears before the submit button in DOM order', () => {
        render(<ContentRequestPage token="t" onClose={() => {}} />);
        const note = screen.getByTestId('content-request-language-note');
        const submit = screen.getByTestId('content-request-submit');
        // bitmask: 4 (DOCUMENT_POSITION_FOLLOWING) means submit follows note
        expect(note.compareDocumentPosition(submit) & 4).toBeTruthy();
    });
});
