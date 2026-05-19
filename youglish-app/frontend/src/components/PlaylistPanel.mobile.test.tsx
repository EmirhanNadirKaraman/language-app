/**
 * #27g — PlaylistPanel mobile regression guards.
 *
 * Load-bearing invariants:
 *   - BuildView inputs use fontSize: 16px (iOS focus-zoom guard).
 *   - Generate playlist primary CTA has minHeight: 44px.
 *   - Close × is 44×44.
 *   - Word "Add" button has minHeight: 44px.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PlaylistPanel } from './PlaylistPanel';
import * as suggestApi from '../api/suggest';

beforeEach(() => {
    // Autocomplete fetch is debounced + AbortController-guarded; no-op the
    // network so the component stays in its initial state for these checks.
    vi.spyOn(suggestApi, 'fetchSuggestions').mockResolvedValue([]);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('PlaylistPanel mobile (#27g)', () => {
    function renderPanel() {
        return render(
            <PlaylistPanel
                token="t"
                language="de"
                onLanguageChange={() => {}}
                onWatch={() => {}}
                onClose={() => {}}
            />,
        );
    }

    it('close button is 44×44', () => {
        renderPanel();
        const close = screen.getByTestId('playlist-close') as HTMLElement;
        expect(close.style.minWidth).toBe('44px');
        expect(close.style.minHeight).toBe('44px');
    });

    it('Add button has minHeight: 44px', () => {
        renderPanel();
        const add = screen.getByTestId('playlist-add') as HTMLElement;
        expect(add.style.minHeight).toBe('44px');
    });

    it('Generate playlist CTA has minHeight: 44px', () => {
        renderPanel();
        const gen = screen.getByTestId('playlist-generate') as HTMLElement;
        expect(gen.style.minHeight).toBe('44px');
    });

    it('BuildView inputs use fontSize: 16px (iOS guard)', () => {
        renderPanel();
        // The shared inputStyle is applied to all <input>/<select> in BuildView.
        // Sample the language select + word search input.
        const inputs = screen.getAllByRole('combobox').concat(
            screen.getAllByRole('textbox'),
            screen.getAllByRole('spinbutton') as HTMLElement[],
        );
        expect(inputs.length).toBeGreaterThan(0);
        for (const el of inputs) {
            expect((el as HTMLInputElement).style.fontSize).toBe('16px');
        }
    });
});
