/**
 * #27f — SettingsPanel mobile regression guards.
 *
 * Load-bearing invariants:
 *   - reps number inputs use fontSize: 16px (iOS focus-zoom guard).
 *   - TagInput text field uses fontSize: 16px.
 *   - Close button is 44×44.
 *   - Preference change still calls onSave (behaviour preserved).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SettingsPanel } from './SettingsPanel';
import * as searchApi from '../api/search';
import { PREFERENCE_DEFAULTS } from '../api/settings';

beforeEach(() => {
    vi.spyOn(searchApi, 'fetchCategories').mockResolvedValue(['News', 'Comedy']);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('SettingsPanel mobile (#27f)', () => {
    it('reps inputs have fontSize: 16px and minHeight: 44px', () => {
        render(<SettingsPanel prefs={PREFERENCE_DEFAULTS} onSave={vi.fn().mockResolvedValue(undefined)} onClose={() => {}} />);
        const passive = screen.getByTestId('settings-passive-reps') as HTMLInputElement;
        const active  = screen.getByTestId('settings-active-reps')  as HTMLInputElement;
        for (const input of [passive, active]) {
            expect(input.style.fontSize).toBe('16px');
            expect(input.style.minHeight).toBe('44px');
        }
    });

    it('TagInput text field has fontSize: 16px (iOS guard)', () => {
        render(<SettingsPanel prefs={PREFERENCE_DEFAULTS} onSave={vi.fn().mockResolvedValue(undefined)} onClose={() => {}} />);
        // There are two TagInput instances (liked_genres + liked_channels); both share the testid.
        const inputs = screen.getAllByTestId('tag-input-field');
        expect(inputs.length).toBeGreaterThan(0);
        for (const input of inputs) {
            expect((input as HTMLInputElement).style.fontSize).toBe('16px');
        }
    });

    it('close button is 44×44 and dismisses', () => {
        const onClose = vi.fn();
        render(<SettingsPanel prefs={PREFERENCE_DEFAULTS} onSave={vi.fn().mockResolvedValue(undefined)} onClose={onClose} />);
        const close = screen.getByTestId('settings-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
        fireEvent.click(close);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('changing a preference still triggers onSave (debounce respected)', async () => {
        const onSave = vi.fn().mockResolvedValue(undefined);
        render(<SettingsPanel prefs={PREFERENCE_DEFAULTS} onSave={onSave} onClose={() => {}} />);

        const passive = await screen.findByTestId('settings-passive-reps') as HTMLInputElement;
        // Wait one tick for syncFromProps to settle so this change isn't treated as a sync.
        await new Promise(r => setTimeout(r, 10));

        fireEvent.change(passive, { target: { value: '7' } });

        // Auto-save debounce is 600ms; allow a comfortable margin.
        await waitFor(
            () => expect(onSave).toHaveBeenCalled(),
            { timeout: 2000 },
        );
        const lastCall = onSave.mock.calls[onSave.mock.calls.length - 1][0];
        expect(lastCall.passive_reps_for_known).toBe(7);
    });
});
