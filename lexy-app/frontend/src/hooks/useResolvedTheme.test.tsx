import { describe, expect, it, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useResolvedTheme } from './useResolvedTheme';

type Listener = (e: MediaQueryListEvent) => void;

/**
 * Build a controllable matchMedia mock for `(prefers-color-scheme: dark)`.
 * Tests can mutate `matches` + fire change events to simulate iOS toggling.
 */
function installMatchMedia(initialDark: boolean) {
    const listeners = new Set<Listener>();
    const mql = {
        matches: initialDark,
        media: '(prefers-color-scheme: dark)',
        onchange: null,
        addEventListener: (_: string, l: Listener) => { listeners.add(l); },
        removeEventListener: (_: string, l: Listener) => { listeners.delete(l); },
        // Some legacy Safari paths use these — leave them undefined to force
        // the addEventListener branch.
        addListener: undefined,
        removeListener: undefined,
        dispatchEvent: () => true,
    };
    const original = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        writable: true,
        value: (_query: string) => mql,
    });
    return {
        mql,
        fire(matches: boolean) {
            mql.matches = matches;
            listeners.forEach((l) => l({ matches } as MediaQueryListEvent));
        },
        restore() {
            Object.defineProperty(window, 'matchMedia', {
                configurable: true,
                writable: true,
                value: original,
            });
        },
    };
}

describe('useResolvedTheme', () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('returns "light" when mode is "light" regardless of system', () => {
        const ctl = installMatchMedia(true); // system says dark
        const { result } = renderHook(() => useResolvedTheme('light'));
        expect(result.current).toBe('light');
        ctl.restore();
    });

    it('returns "dark" when mode is "dark" regardless of system', () => {
        const ctl = installMatchMedia(false);
        const { result } = renderHook(() => useResolvedTheme('dark'));
        expect(result.current).toBe('dark');
        ctl.restore();
    });

    it('returns system value when mode is "system"', () => {
        const ctl = installMatchMedia(true);
        const { result } = renderHook(() => useResolvedTheme('system'));
        expect(result.current).toBe('dark');
        ctl.restore();
    });

    it('updates live when prefers-color-scheme changes (system mode)', () => {
        const ctl = installMatchMedia(false);
        const { result } = renderHook(() => useResolvedTheme('system'));
        expect(result.current).toBe('light');

        act(() => { ctl.fire(true); });
        expect(result.current).toBe('dark');

        act(() => { ctl.fire(false); });
        expect(result.current).toBe('light');
        ctl.restore();
    });

    it('does NOT subscribe to matchMedia when mode is explicit', () => {
        const ctl = installMatchMedia(false);
        const { result } = renderHook(() => useResolvedTheme('light'));
        // Firing system change should not affect the fixed-mode result.
        act(() => { ctl.fire(true); });
        expect(result.current).toBe('light');
        ctl.restore();
    });

    it('cleans up the matchMedia listener on unmount', () => {
        const ctl = installMatchMedia(false);
        const removeSpy = vi.spyOn(ctl.mql, 'removeEventListener');
        const { unmount } = renderHook(() => useResolvedTheme('system'));
        unmount();
        expect(removeSpy).toHaveBeenCalledWith('change', expect.any(Function));
        ctl.restore();
    });
});
