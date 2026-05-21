/**
 * #27g — SelectionPanel mobile regression guards.
 *
 * Load-bearing invariants:
 *   - Note <textarea> uses fontSize: 16px (iOS focus-zoom guard).
 *   - Save primary button has minHeight ≥ 40px.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SelectionPanel } from './SelectionPanel';

const TOKEN_A = {
    blockId: 1, tokenId: 't0', tokenArrayIndex: 0,
    text: 'Hund', blockOrder: 0,
};

describe('SelectionPanel mobile (#27g)', () => {
    function renderPanel() {
        return render(
            <SelectionPanel
                token="t"
                docId="d"
                language="de"
                selectedTokens={[TOKEN_A]}
                sentenceText="Der Hund läuft."
                savedSelections={[]}
                blockTokenMap={new Map([[1, new Set(['t0'])]])}
                onSaved={() => {}}
                onDeleted={() => {}}
                onClear={() => {}}
            />,
        );
    }

    it('note textarea uses fontSize: 16px (iOS guard)', () => {
        renderPanel();
        const note = screen.getByTestId('selection-note') as HTMLTextAreaElement;
        expect(note.style.fontSize).toBe('16px');
    });

    it('Save button has minHeight: 40px (sidebar context)', () => {
        renderPanel();
        const save = screen.getByTestId('selection-save') as HTMLElement;
        expect(save.style.minHeight).toBe('40px');
    });
});
