import { useEffect, useState } from 'react';
import type { ThemeMode } from '../api/settings';

export type ResolvedTheme = 'light' | 'dark';

/**
 * Resolve a `theme_mode` preference into the concrete theme to apply.
 *
 * - "light" / "dark" → that theme, fixed.
 * - "system" → follows `prefers-color-scheme: dark`, updates live when the
 *   system appearance changes (iOS Auto Dark, macOS Sundown, etc.).
 *
 * Returns the resolved theme and side-effects nothing — callers (App.tsx
 * Layout, BookReaderPage local override) decide what to do with the value.
 *
 * SSR/test-safe: when `window.matchMedia` is missing, falls back to "light".
 */
export function useResolvedTheme(mode: ThemeMode): ResolvedTheme {
    const [systemDark, setSystemDark] = useState<boolean>(() => {
        if (typeof window === 'undefined' || !window.matchMedia) return false;
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    });

    useEffect(() => {
        if (mode !== 'system') return;
        if (typeof window === 'undefined' || !window.matchMedia) return;
        const mql = window.matchMedia('(prefers-color-scheme: dark)');
        const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
        // matchMedia change events: modern + legacy Safari/iOS fallback.
        if (mql.addEventListener) {
            mql.addEventListener('change', onChange);
            return () => mql.removeEventListener('change', onChange);
        } else if (mql.addListener) {
            mql.addListener(onChange);
            return () => mql.removeListener(onChange);
        }
    }, [mode]);

    if (mode === 'light') return 'light';
    if (mode === 'dark') return 'dark';
    return systemDark ? 'dark' : 'light';
}
