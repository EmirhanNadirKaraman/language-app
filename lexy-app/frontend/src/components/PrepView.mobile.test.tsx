/**
 * #27g — PrepView CTA mobile regression guard.
 *
 * Load-bearing invariants:
 *   - "Start Guided Practice" primary CTA has minHeight: 44px.
 *   - Back action is at least 36px tall.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { PrepView } from './PrepView';
import * as insightsApi from '../api/insights';
import type { InsightItem } from '../types';

const ITEM: InsightItem = {
    item_id: 1, item_type: 'word', display_text: 'Hund', secondary_text: null,
    score: 0.5, reasons: [],
    signals: { is_due: 0, mistake_recency: 0, freq_rank: 0.5, is_learning: 1 },
    extra: {},
};

beforeEach(() => {
    vi.spyOn(insightsApi, 'fetchPrepData').mockResolvedValue({
        item_id: 1, item_type: 'word',
        display_text: 'Hund', translation: 'dog',
        grammar_structure: null, grammar_explanation: '',
        example: null, templates: [],
        has_examples: false,
        linked_grammar_rules: [],
    } as never);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('PrepView mobile (#27g)', () => {
    it('Start Guided Practice CTA has minHeight: 44px', async () => {
        render(
            <PrepView
                token="t"
                item={ITEM}
                language="de"
                onClose={() => {}}
                onStartPractice={() => {}}
            />,
        );
        await waitFor(() => {
            expect(screen.getByTestId('prep-start-practice')).toBeTruthy();
        });
        const cta = screen.getByTestId('prep-start-practice') as HTMLElement;
        expect(cta.style.minHeight).toBe('44px');
    });

    it('Back action has minHeight: 36px', () => {
        render(
            <PrepView
                token="t"
                item={ITEM}
                language="de"
                onClose={() => {}}
                onStartPractice={() => {}}
            />,
        );
        const back = screen.getByTestId('prep-back') as HTMLElement;
        expect(back.style.minHeight).toBe('36px');
    });
});
