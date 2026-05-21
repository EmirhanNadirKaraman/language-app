/**
 * #27g — ReminderBanner mobile regression guards.
 *
 * Load-bearing invariants:
 *   - "For You" button has minHeight: 36px (secondary action).
 *   - Dismiss × is 44×44.
 *   - Both still dispatch their handlers.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { ReminderBanner } from './ReminderBanner';

const SUMMARY = {
    srs_due_count: 5,
    reading_due_count: 2,
    learning_item_count: 10,
    total_due: 7,
    has_anything_due: true,
};

describe('ReminderBanner mobile (#27g)', () => {
    it('open button has minHeight: 36px', () => {
        render(<ReminderBanner summary={SUMMARY} onDismiss={() => {}} onOpenRecs={() => {}} />);
        const open = screen.getByTestId('reminder-banner-open') as HTMLElement;
        expect(open.style.minHeight).toBe('36px');
    });

    it('dismiss button is 44×44', () => {
        render(<ReminderBanner summary={SUMMARY} onDismiss={() => {}} onOpenRecs={() => {}} />);
        const dismiss = screen.getByTestId('reminder-banner-dismiss') as HTMLElement;
        expect(dismiss.style.minWidth).toBe('44px');
        expect(dismiss.style.minHeight).toBe('44px');
    });

    it('clicks dispatch handlers (behaviour preserved)', () => {
        const onOpenRecs = vi.fn();
        const onDismiss = vi.fn();
        render(<ReminderBanner summary={SUMMARY} onDismiss={onDismiss} onOpenRecs={onOpenRecs} />);
        fireEvent.click(screen.getByTestId('reminder-banner-open'));
        fireEvent.click(screen.getByTestId('reminder-banner-dismiss'));
        expect(onOpenRecs).toHaveBeenCalledTimes(1);
        expect(onDismiss).toHaveBeenCalledTimes(1);
    });
});
