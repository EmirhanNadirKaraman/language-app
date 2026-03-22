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

    useEffect(() => {
        if (!token) {
            setPrefs(PREFERENCE_DEFAULTS);
            return;
        }
        let cancelled = false;
        setLoading(true);
        getPreferences(token)
            .then(p => { if (!cancelled) setPrefs(p); })
            .catch(() => {})
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [token]);

    const savePreferences = useCallback(async (update: UserPreferencesUpdate): Promise<void> => {
        if (!token) return;
        const updated = await updatePreferences(token, update);
        setPrefs(updated);
    }, [token]);

    const channelAction = useCallback(async (
        channelId: string,
        channelName: string,
        action: ChannelAction,
    ): Promise<void> => {
        if (!token) return;
        const updated = await updateChannelPreference(token, channelId, channelName, action);
        setPrefs(updated);
    }, [token]);

    const genreAction = useCallback(async (
        genre: string,
        action: GenreAction,
    ): Promise<void> => {
        if (!token) return;
        const updated = await updateGenrePreference(token, genre, action);
        setPrefs(updated);
    }, [token]);

    return { prefs, savePreferences, channelAction, genreAction, loading };
}
