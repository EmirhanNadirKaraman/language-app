/**
 * #27e — SRSReviewPage mobile / iOS-safety regression guards.
 *
 * Load-bearing invariants:
 *   - Active production input has fontSize >= 16px (iOS Safari focus-zoom guard).
 *   - All review buttons have minHeight >= 44px (HIG/Material touch target).
 *   - Button row uses flexWrap so it survives 320px viewports.
 *
 * Active-card setup short-circuits getDueCards so we don't hit the backend.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { SRSReviewPage } from './SRSReviewPage';
import type { SRSReviewCard } from '../types';
import * as srsApi from '../api/srs';

const ACTIVE_CARD: SRSReviewCard = {
    card_id: 1,
    item_id: 100,
    item_type: 'word',
    direction: 'active',
    due_date: new Date(Date.now() + 86_400_000).toISOString(),
    repetitions: 0,
    passive_level: 1,
    active_level: 0,
    display_text: 'Auto',
    prompt_text: 'car',
    answer_text: 'Auto',
};

const PASSIVE_CARD: SRSReviewCard = {
    ...ACTIVE_CARD,
    card_id: 2,
    direction: 'passive',
    prompt_text: 'Auto',
    answer_text: 'car',
};

beforeEach(() => {
    vi.restoreAllMocks();
});

afterEach(() => {
    vi.restoreAllMocks();
});

async function renderWithCards(cards: SRSReviewCard[]) {
    vi.spyOn(srsApi, 'getDueCards').mockResolvedValue(cards);
    const utils = render(
        <SRSReviewPage
            token="fake-token"
            language="de"
            onLanguageChange={() => {}}
            onClose={() => {}}
        />,
    );
    // Wait for the card to land — the active-input renders only after load resolves.
    await waitFor(() => {
        // Either the input (active) or the "Show answer" button (passive) is mounted.
        const ready = utils.queryByTestId('srs-active-input')
            ?? utils.queryByText('Show answer');
        expect(ready).toBeTruthy();
    });
    return utils;
}

describe('SRSReviewPage mobile (#27e)', () => {
    it('ACTIVE card input has fontSize: 16px (iOS focus-zoom guard)', async () => {
        await renderWithCards([ACTIVE_CARD]);
        const input = screen.getByTestId('srs-active-input') as HTMLInputElement;
        expect(input.style.fontSize).toBe('16px');
    });

    it('ACTIVE card input has 44px minHeight', async () => {
        await renderWithCards([ACTIVE_CARD]);
        const input = screen.getByTestId('srs-active-input') as HTMLInputElement;
        expect(input.style.minHeight).toBe('44px');
    });

    it('ACTIVE card buttons (I don\'t know + Submit) have 44px minHeight', async () => {
        await renderWithCards([ACTIVE_CARD]);
        const dontKnow = screen.getByTestId('srs-active-dont-know') as HTMLElement;
        const submit   = screen.getByTestId('srs-active-submit')   as HTMLElement;
        expect(dontKnow.style.minHeight).toBe('44px');
        expect(submit.style.minHeight).toBe('44px');
    });

    it('ACTIVE button row uses flex-wrap so it survives narrow phones', async () => {
        await renderWithCards([ACTIVE_CARD]);
        const dontKnow = screen.getByTestId('srs-active-dont-know') as HTMLElement;
        const row = dontKnow.parentElement as HTMLElement;
        expect(row.style.flexWrap).toBe('wrap');
    });

    it('PASSIVE card buttons have 44px minHeight after reveal', async () => {
        await renderWithCards([PASSIVE_CARD]);
        // Click "Show answer" first to reveal the grade buttons.
        screen.getByText('Show answer').click();
        const no  = await screen.findByTestId('srs-passive-incorrect');
        const yes = await screen.findByTestId('srs-passive-correct');
        expect((no  as HTMLElement).style.minHeight).toBe('44px');
        expect((yes as HTMLElement).style.minHeight).toBe('44px');
    });

    it('close button is 44×44', async () => {
        await renderWithCards([ACTIVE_CARD]);
        const close = screen.getByTestId('srs-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
    });
});
