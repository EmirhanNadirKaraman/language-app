import { useCallback, useEffect, useState } from 'react';
import {
    getPreferences,
    updatePreferences,
    updateChannelPreference,
    updateGenrePreference,
    PREFERENCE_DEFAULTS,
} from '../api/settings';
import type { ChannelAction, GenreAction, UserPreferences, UserPreferencesUpdate } from '../api/settings';

export function usePreferences(token: string | null) {
    const [prefs, setPrefs] = useState<UserPreferences>(PREFERENCE_DEFAULTS);
    const [loading, setLoading] = useState(false);
    const [error,   setError]   = useState<string | null>(null);

    useEffect(() => {
        if (!token) {
            setPrefs(PREFERENCE_DEFAULTS);
            setError(null);
            return;
        }
        let cancelled = false;
        setLoading(true);
        setError(null);
        getPreferences(token)
            .then(p => {
                if (!cancelled) setPrefs({ ...PREFERENCE_DEFAULTS, ...p });
            })
            .catch((e: unknown) => {
                // 401 → already handled by _http.ts (auth:expired event fired).
                // Other errors: surface the message; intentionally keep the
                // existing `prefs` state so the UI doesn't snap back to
                // defaults on a transient fetch failure.
                if (!cancelled) {
                    setError(e instanceof Error ? e.message : 'Failed to load preferences');
                }
            })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [token]);

    const savePreferences = useCallback(async (update: UserPreferencesUpdate): Promise<void> => {
        if (!token) return;
        const updated = await updatePreferences(token, update);
        setPrefs(p => ({ ...PREFERENCE_DEFAULTS, ...p, ...updated }));
    }, [token]);

    const channelAction = useCallback(async (
        channelId: string,
        channelName: string,
        action: ChannelAction,
    ): Promise<void> => {
        if (!token) return;
        const updated = await updateChannelPreference(token, channelId, channelName, action);
        setPrefs(p => ({ ...PREFERENCE_DEFAULTS, ...p, ...updated }));
    }, [token]);

    const genreAction = useCallback(async (
        genre: string,
        action: GenreAction,
    ): Promise<void> => {
        if (!token) return;
        const updated = await updateGenrePreference(token, genre, action);
        setPrefs(p => ({ ...PREFERENCE_DEFAULTS, ...p, ...updated }));
    }, [token]);

    return { prefs, savePreferences, channelAction, genreAction, loading, error };
}
