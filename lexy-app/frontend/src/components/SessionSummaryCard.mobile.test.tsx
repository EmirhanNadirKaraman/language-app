/**
 * #27g — SessionSummaryCard mobile regression guards.
 *
 * Load-bearing invariants:
 *   - Primary CTA "See next recommended item" has minHeight: 44px.
 *   - Click dispatches handlers.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { SessionSummaryCard } from './SessionSummaryCard';
import type { GuidedSessionSummary } from '../types';

const SUMMARY: GuidedSessionSummary = {
    session_id: 's1',
    target_word: 'sich freuen',
    target_item_id: 1,
    target_item_type: 'phrase',
    target_used: true,
    target_counted: true,
    target_counted_count: 1,
    total_turns: 3,
    hint_level: 0,
    sentence_quality: 'good',
    what_went_well: 'Used target correctly',
    what_to_improve: 'Vary sentence structure',
    corrective_note: '',
};

describe('SessionSummaryCard mobile (#27g)', () => {
    it('next-item CTA has minHeight: 44px and fires handler', () => {
        const onNextItem = vi.fn();
        render(
            <SessionSummaryCard
                summary={SUMMARY}
                onNextItem={onNextItem}
                onPracticeAgain={() => {}}
                onClose={() => {}}
            />,
        );
        const cta = screen.getByTestId('summary-next-item') as HTMLElement;
        expect(cta.style.minHeight).toBe('44px');
        fireEvent.click(cta);
        expect(onNextItem).toHaveBeenCalledTimes(1);
    });
});
