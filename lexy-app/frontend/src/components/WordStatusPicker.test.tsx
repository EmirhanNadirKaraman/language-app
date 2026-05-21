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

    // W2 / Hole 1 — never-scraped word recovery
    describe('Learn this anyway', () => {
        it('shows "Not in vocabulary yet" + button when onLearnAnyway is provided', () => {
            render(
                <WordStatusPicker
                    word="xyzzy"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    onLearnAnyway={() => {}}
                />,
            );
            expect(screen.getByText(/Not in vocabulary yet/)).toBeInTheDocument();
            expect(screen.getByTestId('learn-anyway')).toBeInTheDocument();
        });

        it('does NOT render the button when onLearnAnyway is omitted (back-compat)', () => {
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
            expect(screen.queryByTestId('learn-anyway')).toBeNull();
        });

        it('calls onLearnAnyway when the button is clicked', () => {
            const learnAnyway = vi.fn();
            render(
                <WordStatusPicker
                    word="xyzzy"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    onLearnAnyway={learnAnyway}
                />,
            );
            fireEvent.click(screen.getByTestId('learn-anyway'));
            expect(learnAnyway).toHaveBeenCalledTimes(1);
        });

        it('disables the button when saving + shows "Adding…" label', () => {
            render(
                <WordStatusPicker
                    word="xyzzy"
                    lookup={null}
                    loading={false}
                    saving={true}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    onLearnAnyway={() => {}}
                />,
            );
            const btn = screen.getByTestId('learn-anyway') as HTMLButtonElement;
            expect(btn.disabled).toBe(true);
            expect(btn.textContent).toBe('Adding…');
        });

        it('shows the error message when learnAnywayError is set', () => {
            render(
                <WordStatusPicker
                    word="xyzzy"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    onLearnAnyway={() => {}}
                    learnAnywayError="Network down"
                />,
            );
            expect(screen.getByTestId('learn-anyway-error').textContent).toBe('Network down');
        });
    });

    // W3 / Hole 2 — disambiguation candidate chooser
    describe('Candidate chooser (ambiguous lookup)', () => {
        const candidates: WordLookupResult[] = [
            { word_id: 1, word: 'Bank', lemma: 'Bank', pos: 'NOUN',
              current_status: 'learning', passive_level: 2, active_level: 0,
              passive_due: null, active_due: null },
            { word_id: 2, word: 'Bank', lemma: 'Bank', pos: 'NOUN',
              current_status: null, passive_level: 0, active_level: 0,
              passive_due: null, active_due: null },
        ];

        it('renders the chooser and hides the status buttons', () => {
            render(
                <WordStatusPicker
                    word="Bank"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    candidates={candidates}
                    onSelectCandidate={() => {}}
                />,
            );
            expect(screen.getByTestId('candidate-chooser')).toBeInTheDocument();
            expect(screen.getAllByTestId('candidate-button')).toHaveLength(2);
            expect(screen.queryAllByTestId('word-status-button')).toHaveLength(0);
        });

        it('hides "Not in vocabulary yet" / "Learn this anyway" when candidates exist', () => {
            render(
                <WordStatusPicker
                    word="Bank"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    onLearnAnyway={() => {}}
                    candidates={candidates}
                    onSelectCandidate={() => {}}
                />,
            );
            expect(screen.queryByText(/Not in vocabulary yet/)).toBeNull();
            expect(screen.queryByTestId('learn-anyway')).toBeNull();
        });

        it('invokes onSelectCandidate with the chosen candidate', () => {
            const onSelectCandidate = vi.fn();
            render(
                <WordStatusPicker
                    word="Bank"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    candidates={candidates}
                    onSelectCandidate={onSelectCandidate}
                />,
            );
            const buttons = screen.getAllByTestId('candidate-button');
            fireEvent.click(buttons[1]);
            expect(onSelectCandidate).toHaveBeenCalledTimes(1);
            expect(onSelectCandidate.mock.calls[0][0].word_id).toBe(2);
        });

        it('falls back to "Not in vocabulary" when candidates is empty', () => {
            render(
                <WordStatusPicker
                    word="xyzzy"
                    lookup={null}
                    loading={false}
                    saving={false}
                    onSelect={() => {}}
                    onDismiss={() => {}}
                    candidates={[]}
                    onSelectCandidate={() => {}}
                />,
            );
            expect(screen.queryByTestId('candidate-chooser')).toBeNull();
            expect(screen.getByText(/Not in vocabulary/)).toBeInTheDocument();
        });
    });
});
