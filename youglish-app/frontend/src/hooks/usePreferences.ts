import { useCallback, useEffect, useState } from 'react';
import {
    getPreferences,
    updatePreferences,
    PREFERENCE_DEFAULTS,
} from '../api/settings';
import type { UserPreferences, UserPreferencesUpdate } from '../api/settings';

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

    return { prefs, savePreferences, loading };
}
