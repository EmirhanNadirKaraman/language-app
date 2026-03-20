/**
 * Tests for TranscriptPanel deterministic UI behavior.
 *
 * Setup required (one time):
 *   npm install -D vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom
 *
 * Add to vite.config.ts:
 *   test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'] }
 *
 * Create src/test/setup.ts:
 *   import '@testing-library/jest-dom';
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TranscriptPanel } from './TranscriptPanel';
import type { NormalizedSentence } from '../utils/sentenceUtils';

// ReadingStatsPanel makes a fetch call — stub it out
vi.mock('./ReadingStatsPanel', () => ({
    ReadingStatsPanel: () => <div data-testid="stats-panel" />,
}));

const SENTENCES: NormalizedSentence[] = [
    { sentence_id: 1, start_time: 0,  start_time_int: 0,  content: 'Hello world',    timeSec: 0 },
    { sentence_id: 2, start_time: 5,  start_time_int: 5,  content: 'How are you',     timeSec: 5 },
    { sentence_id: 3, start_time: 10, start_time_int: 10, content: 'I am fine thanks', timeSec: 10 },
];

const DEFAULT_PROPS = {
    sentences: SENTENCES,
    activeSentenceIdx: 0,
    highlightTerms: [],
    wordStatuses: {},
    onWordClick: vi.fn(),
    onWordRightClick: vi.fn(),
    onSentenceClick: vi.fn(),
    videoId: 'vid123',
    token: null,
    refreshKey: 0,
};

beforeEach(() => {
    vi.clearAllMocks();
});

describe('TranscriptPanel', () => {
    it('renders all sentence texts', () => {
        render(<TranscriptPanel {...DEFAULT_PROPS} />);
        expect(screen.getByText(/Hello/)).toBeInTheDocument();
        expect(screen.getByText(/How/)).toBeInTheDocument();
        expect(screen.getByText(/fine/)).toBeInTheDocument();
    });

    it('applies active highlight style to the active sentence', () => {
        render(<TranscriptPanel {...DEFAULT_PROPS} activeSentenceIdx={1} />);
        const allBlocks = screen.getAllByText(/\w+/).map(el => el.closest('div[style]'));
        // The second sentence block should have the active background
        const activeBlock = screen.getByText('How').closest('div[style]');
        expect(activeBlock).toHaveStyle({ borderLeft: '3px solid #3f51b5' });
    });

    it('calls onSentenceClick when clicking the sentence background (not a word)', () => {
        const onSentenceClick = vi.fn();
        render(<TranscriptPanel {...DEFAULT_PROPS} onSentenceClick={onSentenceClick} />);

        // Fire click directly on the sentence block div (e.target === e.currentTarget)
        const sentenceBlocks = screen.getAllByTestId('sentence-block');
        fireEvent.click(sentenceBlocks[1]); // second sentence
        expect(onSentenceClick).toHaveBeenCalledWith(1);
    });

    it('does not call onSentenceClick when clicking a word span inside a sentence', () => {
        const onSentenceClick = vi.fn();
        render(<TranscriptPanel {...DEFAULT_PROPS} onSentenceClick={onSentenceClick} />);

        // Click a word inside a sentence — target is the <span>, not the div
        fireEvent.click(screen.getByText('world'));
        expect(onSentenceClick).not.toHaveBeenCalled();
    });

    it('calls onWordClick when a word is left-clicked', () => {
        const onWordClick = vi.fn();
        render(<TranscriptPanel {...DEFAULT_PROPS} onWordClick={onWordClick} />);
        fireEvent.click(screen.getByText('world'));
        expect(onWordClick).toHaveBeenCalledWith('world');
    });

    it('calls onWordRightClick on context menu and suppresses browser default', () => {
        const onWordRightClick = vi.fn();
        render(<TranscriptPanel {...DEFAULT_PROPS} onWordRightClick={onWordRightClick} />);
        const event = fireEvent.contextMenu(screen.getByText('world'));
        expect(onWordRightClick).toHaveBeenCalledWith('world');
        // preventDefault is called inside ClickableWord's onContextMenu handler
        expect(event).toBe(false); // fireEvent returns false when preventDefault is called
    });

    it('shows loading message when sentences array is empty', () => {
        render(<TranscriptPanel {...DEFAULT_PROPS} sentences={[]} />);
        expect(screen.getByText(/Loading transcript/)).toBeInTheDocument();
    });

    it('renders the stats panel', () => {
        render(<TranscriptPanel {...DEFAULT_PROPS} />);
        expect(screen.getByTestId('stats-panel')).toBeInTheDocument();
    });
});
