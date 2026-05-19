/**
 * #27c — WordStatusPicker mobile/touch regression guards.
 *
 * Verifies the inline picker stays usable on phone-sized viewports:
 *   - status buttons meet the 44×44 touch target
 *   - status button row wraps so all 3 buttons remain visible on narrow phones
 *   - close button is also 44×44
 *   - status update still fires on click
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { WordStatusPicker } from './WordStatusPicker';
import type { WordLookupResult } from '../types';

function makeLookup(overrides: Partial<WordLookupResult> = {}): WordLookupResult {
    return {
        word_id:        42,
        word:           'Auto',
        lemma:          'Auto',
        current_status: 'learning',
        passive_level:  1,
        active_level:   0,
        passive_due:    null,
        active_due:     null,
        ...overrides,
    };
}

describe('WordStatusPicker mobile / touch', () => {
    it('renders all three status buttons with 44×44 minimum touch target', () => {
        render(
            <WordStatusPicker
                word="Auto"
                lookup={makeLookup()}
                loading={false}
                saving={false}
                onSelect={() => {}}
                onDismiss={() => {}}
            />,
        );
        const buttons = screen.getAllByTestId('word-status-button');
        expect(buttons.length).toBe(3);   // Unknown / Learning / Known
        for (const b of buttons) {
            const el = b as HTMLElement;
            expect(el.style.minWidth).toBe('44px');
            expect(el.style.minHeight).toBe('44px');
        }
    });

    it('status button row uses flex-wrap so it survives narrow phones', () => {
        const { container } = render(
            <WordStatusPicker
                word="Auto"
                lookup={makeLookup()}
                loading={false}
                saving={false}
                onSelect={() => {}}
                onDismiss={() => {}}
            />,
        );
        // The button row is the direct parent of the status buttons.
        const firstBtn = container.querySelector('[data-testid="word-status-button"]') as HTMLElement;
        const row = firstBtn.parentElement as HTMLElement;
        expect(row.style.flexWrap).toBe('wrap');
    });

    it('close button is 44×44 and dismisses on click', () => {
        const onDismiss = vi.fn();
        render(
            <WordStatusPicker
                word="Auto"
                lookup={makeLookup()}
                loading={false}
                saving={false}
                onSelect={() => {}}
                onDismiss={onDismiss}
            />,
        );
        const close = screen.getByTestId('word-status-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
        fireEvent.click(close);
        expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it('status update still fires on click (behaviour preserved)', () => {
        const onSelect = vi.fn();
        render(
            <WordStatusPicker
                word="Auto"
                lookup={makeLookup({ current_status: 'unknown' })}
                loading={false}
                saving={false}
                onSelect={onSelect}
                onDismiss={() => {}}
            />,
        );
        const buttons = screen.getAllByTestId('word-status-button');
        fireEvent.click(buttons[2]);   // "Known"
        expect(onSelect).toHaveBeenCalledWith(42, 'known');
    });

    it('renders "Not in vocabulary" when lookup is null', () => {
        render(
            <WordStatusPicker
                word="xyzzy"
                lookup={null}
                loading={false}
                saving={false}
                onSelect={() => {}}
                onDismiss={() => {}}
            />,
        );
        expect(screen.getByText(/Not in vocabulary/)).toBeInTheDocument();
        // No status buttons when the word isn't tracked.
        expect(screen.queryAllByTestId('word-status-button').length).toBe(0);
    });
});
