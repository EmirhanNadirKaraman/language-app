/**
 * #27g — RecommendationsPanel mobile regression guards.
 *
 * Load-bearing invariants:
 *   - Language <select> uses fontSize: 16px (iOS focus-zoom guard) + 44px minHeight.
 *   - Close × is 44×44.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { RecommendationsPanel } from './RecommendationsPanel';
import * as recsApi from '../api/recommendations';
import * as insightsApi from '../api/insights';
import * as readingApi from '../api/reading';

beforeEach(() => {
    vi.spyOn(recsApi, 'fetchItemRecommendations').mockResolvedValue({ items: [] } as never);
    vi.spyOn(recsApi, 'fetchVideoRecommendations').mockResolvedValue({ videos: [], reason: 'no_target_items' } as never);
    vi.spyOn(recsApi, 'fetchSentenceRecommendations').mockResolvedValue({ sentences: [] } as never);
    vi.spyOn(insightsApi, 'fetchInsightCards').mockResolvedValue({ cards: [] } as never);
    vi.spyOn(readingApi, 'getDueSelections').mockResolvedValue([]);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('RecommendationsPanel mobile (#27g)', () => {
    function renderPanel() {
        return render(
            <RecommendationsPanel
                token="t"
                language="de"
                onLanguageChange={() => {}}
                onWatch={() => {}}
                onPractice={() => {}}
                onPracticeItem={() => {}}
                onPracticeSentence={() => {}}
                onSearch={() => {}}
                onClose={() => {}}
            />,
        );
    }

    it('close × is 44×44', async () => {
        renderPanel();
        await waitFor(() => {
            expect(screen.getByTestId('recs-close')).toBeTruthy();
        });
        const close = screen.getByTestId('recs-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
    });

    it('language <select> uses fontSize: 16px and minHeight: 44px', async () => {
        renderPanel();
        await waitFor(() => {
            expect(screen.getByTestId('recs-language')).toBeTruthy();
        });
        const sel = screen.getByTestId('recs-language') as HTMLSelectElement;
        expect(sel.style.fontSize).toBe('16px');
        expect(sel.style.minHeight).toBe('44px');
    });
});
