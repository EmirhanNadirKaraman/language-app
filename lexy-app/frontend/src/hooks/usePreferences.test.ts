import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { usePreferences } from './usePreferences';
import * as settings from '../api/settings';

describe('usePreferences', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('sets preferences on successful load', async () => {
        vi.spyOn(settings, 'getPreferences').mockResolvedValue({
            ...settings.PREFERENCE_DEFAULTS,
            dark_mode: true,
            known_word_color: '#aabbcc',
        });

        const { result } = renderHook(() => usePreferences('tok'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.prefs.dark_mode).toBe(true);
        expect(result.current.prefs.known_word_color).toBe('#aabbcc');
        expect(result.current.error).toBeNull();
    });

    it('exposes error state when preference load fails', async () => {
        vi.spyOn(settings, 'getPreferences').mockRejectedValue(new Error('boom'));

        const { result } = renderHook(() => usePreferences('tok'));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('boom');
    });

    it('does not reset preferences on a transient failure mid-session', async () => {
        // First load succeeds with custom prefs.
        const first = vi.spyOn(settings, 'getPreferences').mockResolvedValueOnce({
            ...settings.PREFERENCE_DEFAULTS,
            dark_mode: true,
        });

        const { result, rerender } = renderHook(
            ({ token }: { token: string | null }) => usePreferences(token),
            { initialProps: { token: 'tok-1' } },
        );
        await waitFor(() => expect(result.current.prefs.dark_mode).toBe(true));
        first.mockRestore();

        // Second call (after token change) fails — prefs from the previous load
        // should remain intact, error should surface.
        vi.spyOn(settings, 'getPreferences').mockRejectedValue(new Error('network down'));
        rerender({ token: 'tok-2' });

        await waitFor(() => expect(result.current.error).toBe('network down'));
        // CRITICAL: prefs not wiped.
        expect(result.current.prefs.dark_mode).toBe(true);
    });

    it('resets to defaults when token becomes null (sign out)', async () => {
        vi.spyOn(settings, 'getPreferences').mockResolvedValue({
            ...settings.PREFERENCE_DEFAULTS,
            dark_mode: true,
        });
        const { result, rerender } = renderHook(
            ({ token }: { token: string | null }) => usePreferences(token),
            { initialProps: { token: 'tok' as string | null } },
        );
        await waitFor(() => expect(result.current.prefs.dark_mode).toBe(true));

        rerender({ token: null });
        await waitFor(() => expect(result.current.prefs.dark_mode).toBe(false));
        expect(result.current.error).toBeNull();
    });
});
