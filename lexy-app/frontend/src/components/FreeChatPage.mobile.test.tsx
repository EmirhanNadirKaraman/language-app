/**
 * #27g — FreeChatPage close button mobile regression guard.
 *
 * Load-bearing invariants:
 *   - Header close × is 44×44.
 *   - Click dispatches onClose.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { FreeChatPage } from './FreeChatPage';
import * as chatApi from '../api/chat';
import type { SearchResult } from '../types';

const RESULT: SearchResult = {
    video_id: 'v', title: 't', thumbnail_url: '', language: 'de',
    start_time: 0, start_time_int: 0, content: '', surface_form: null,
    match_type: 'search',
};

beforeEach(() => {
    // Never resolve — the close button is rendered regardless of session state.
    vi.spyOn(chatApi, 'createSession').mockReturnValue(new Promise(() => {}));
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('FreeChatPage mobile (#27g)', () => {
    it('close button is 44×44 and fires onClose', () => {
        const onClose = vi.fn();
        render(<FreeChatPage result={RESULT} token="t" onClose={onClose} />);
        const close = screen.getByTestId('free-chat-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
        fireEvent.click(close);
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});
