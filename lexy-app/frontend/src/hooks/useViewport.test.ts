import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useViewport } from './useViewport';

/**
 * Build a stub MediaQueryList object that responds to a known query and
 * supports adding/removing change listeners. Returns the stub plus a fire()
 * helper so tests can simulate a viewport change.
 */
function mockMatchMedia(initialMatches: boolean) {
    let matches = initialMatches;
    const listeners = new Set<(e: MediaQueryListEvent) => void>();

    const mql = {
        get matches() { return matches; },
        media: '(max-width: 768px)',
        onchange: null,
        addEventListener(type: string, cb: (e: MediaQueryListEvent) => void) {
            if (type === 'change') listeners.add(cb);
        },
        removeEventListener(type: string, cb: (e: MediaQueryListEvent) => void) {
            if (type === 'change') listeners.delete(cb);
        },
        addListener() { /* legacy fallback path; not exercised in this stub */ },
        removeListener() { /* legacy fallback */ },
        dispatchEvent: () => true,
    } as unknown as MediaQueryList;

    function fire(next: boolean) {
        matches = next;
        const evt = { matches: next, media: '(max-width: 768px)' } as MediaQueryListEvent;
        listeners.forEach(cb => cb(evt));
    }

    return { mql, fire, listenerCount: () => listeners.size };
}

describe('useViewport', () => {
    let mediaMock: ReturnType<typeof mockMatchMedia>;

    beforeEach(() => {
        mediaMock = mockMatchMedia(false);
        vi.stubGlobal('matchMedia', vi.fn(() => mediaMock.mql));
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('returns isMobile=false when matchMedia does not match', () => {
        const { result } = renderHook(() => useViewport());
        expect(result.current.isMobile).toBe(false);
    });

    it('returns isMobile=true when matchMedia matches on mount', () => {
        mediaMock = mockMatchMedia(true);
        vi.stubGlobal('matchMedia', vi.fn(() => mediaMock.mql));

        const { result } = renderHook(() => useViewport());
        expect(result.current.isMobile).toBe(true);
    });

    it('updates when a MediaQueryList change event fires', () => {
        const { result } = renderHook(() => useViewport());
        expect(result.current.isMobile).toBe(false);

        act(() => mediaMock.fire(true));
        expect(result.current.isMobile).toBe(true);

        act(() => mediaMock.fire(false));
        expect(result.current.isMobile).toBe(false);
    });

    it('removes its listener on unmount', () => {
        const { unmount } = renderHook(() => useViewport());
        expect(mediaMock.listenerCount()).toBe(1);
        unmount();
        expect(mediaMock.listenerCount()).toBe(0);
    });

    it('defaults to isMobile=false when window.matchMedia is unavailable', () => {
        vi.stubGlobal('matchMedia', undefined);
        const { result } = renderHook(() => useViewport());
        expect(result.current.isMobile).toBe(false);
    });
});
