import { useEffect, useState } from 'react';

/**
 * Mobile-vs-desktop hook (#27a).
 *
 * Returns `{ isMobile }` where `isMobile === true` when the viewport is at or
 * below the `--bp-md` breakpoint (768px — kept in sync with index.css).
 *
 * Implementation notes:
 *   - Uses `window.matchMedia('(max-width: 768px)')` so it tracks orientation
 *     changes + window resizes via the native MediaQueryList event, no resize
 *     listener / throttling needed.
 *   - SSR / jsdom-without-matchMedia safe: when `window` or `matchMedia` is
 *     unavailable, defaults to NOT mobile (the conservative choice — don't
 *     ship a mobile-stripped layout to a server-rendered desktop browser).
 *   - Subscribes via `addEventListener('change', ...)` and falls back to the
 *     deprecated `addListener` on older Safari versions that still exist in
 *     macOS 10.13 / iOS 12 land. Both paths clean up on unmount.
 */
const MOBILE_QUERY = '(max-width: 768px)';

function getInitialMatch(): boolean {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return false;
    }
    return window.matchMedia(MOBILE_QUERY).matches;
}

export function useViewport(): { isMobile: boolean } {
    const [isMobile, setIsMobile] = useState<boolean>(getInitialMatch);

    useEffect(() => {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        const mql = window.matchMedia(MOBILE_QUERY);
        const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);

        // Resync once on mount in case window size changed between initial render
        // and effect attach (unlikely but cheap to cover).
        setIsMobile(mql.matches);

        if (typeof mql.addEventListener === 'function') {
            mql.addEventListener('change', onChange);
            return () => mql.removeEventListener('change', onChange);
        }
        // Legacy Safari fallback.
        const legacyListener = (e: MediaQueryListEvent) => setIsMobile(e.matches);
        mql.addListener(legacyListener);
        return () => mql.removeListener(legacyListener);
    }, []);

    return { isMobile };
}
