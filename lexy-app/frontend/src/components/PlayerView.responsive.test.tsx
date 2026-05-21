/**
 * #27b — mobile layout regression guards for the main video-learning surface.
 *
 * These tests don't try to render the full YouTube iframe / network — they
 * inspect the rendered DOM and confirm the responsive primitives are in
 * place: aspect-ratio container, fluid subtitle font/height, 44×44 minimum
 * touch targets, and flex-wrap on the controls row.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SubtitleDisplay } from './SubtitleDisplay';
import { PlayerControls } from './PlayerControls';
import { YoutubeEmbed } from './YoutubeEmbed';

// YoutubeEmbed kicks off loadYTApi() on mount which `new`s window.YT.Player.
// Stub a `new`-able function so jsdom doesn't fetch the real iframe script
// and we don't crash on construction.
function FakePlayer(this: Record<string, () => void>) {
    this.seekTo = () => {};
    this.getCurrentTime = () => {};
    this.pauseVideo = () => {};
    this.destroy = () => {};
}

beforeEach(() => {
    (window as unknown as { YT: unknown }).YT = { Player: FakePlayer };
});

afterEach(() => {
    (window as unknown as { YT: unknown }).YT = undefined;
});


// ---------------------------------------------------------------------------
// YoutubeEmbed — aspect-ratio container
// ---------------------------------------------------------------------------

describe('YoutubeEmbed responsive wrapper', () => {
    it('renders a 16/9 aspect-ratio container', () => {
        const { container } = render(<YoutubeEmbed videoId="abc" startTime={0} />);
        const wrapper = container.firstChild as HTMLElement;
        expect(wrapper).toBeTruthy();
        expect(wrapper.style.aspectRatio).toBe('16 / 9');
        expect(wrapper.style.width).toBe('100%');
    });

    it('does not use a fixed pixel height (was 56.25% padding-bottom trick before)', () => {
        const { container } = render(<YoutubeEmbed videoId="abc" startTime={0} />);
        const wrapper = container.firstChild as HTMLElement;
        // Padding-top hack removed; aspect-ratio is the source of truth now.
        expect(wrapper.style.paddingTop).toBe('');
    });
});


// ---------------------------------------------------------------------------
// SubtitleDisplay — fluid font, no clip
// ---------------------------------------------------------------------------

describe('SubtitleDisplay mobile-friendly sizing', () => {
    it('uses min-height (allows growth) instead of a fixed clipping height', () => {
        const { container } = render(
            <SubtitleDisplay text="Hallo Welt" highlightTerms={[]} />,
        );
        const wrapper = container.firstChild as HTMLElement;
        expect(wrapper.style.minHeight).toBe('200px');
        // Fixed `height` must NOT be set (otherwise long subtitles clip).
        expect(wrapper.style.height).toBe('');
    });

    // NOTE: jsdom drops `clamp()` from inline `style.fontSize` entirely (it
    // doesn't appear in either `.style.fontSize` or the serialised style
    // attribute). The `clamp(20px, 5vw, 38px)` value is verified visually in a
    // real browser; the minHeight test above is the structural regression guard.
});


// ---------------------------------------------------------------------------
// PlayerControls — touch target audit + wrap on mobile
// ---------------------------------------------------------------------------

describe('PlayerControls touch-target + wrap', () => {
    function renderControls() {
        return render(
            <PlayerControls
                onPrevVideo={() => {}}
                onPrevMatch={() => {}}
                onReplay={() => {}}
                onNextMatch={() => {}}
                onNextVideo={() => {}}
                disablePrevVideo={false}
                disablePrevMatch={false}
                disableNextMatch={false}
                disableNextVideo={false}
                sentenceIdx={0}
                sentenceCount={3}
            />,
        );
    }

    it('all buttons have at least 44×44 min size', () => {
        renderControls();
        const buttons = screen.getAllByRole('button');
        expect(buttons.length).toBe(5);
        for (const b of buttons) {
            const el = b as HTMLElement;
            // Both minWidth/minHeight and width/height set to 44px; the min*
            // pair is the guarantee that survives if width/height were ever
            // removed by a future change.
            expect(el.style.minWidth).toBe('44px');
            expect(el.style.minHeight).toBe('44px');
        }
    });

    it('outer container allows wrap so the sentence counter can drop below the buttons on narrow phones', () => {
        const { container } = renderControls();
        const outer = container.firstChild as HTMLElement;
        expect(outer.style.flexWrap).toBe('wrap');
    });
});
