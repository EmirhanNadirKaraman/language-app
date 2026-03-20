export interface UserPreferences {
    liked_genres: string[];
    liked_channels: string[];
    passive_reps_for_known: number;
    active_reps_for_known: number;
    known_word_color: string;
    learning_word_color: string;
    unknown_word_color: string;
}

export type UserPreferencesUpdate = Partial<UserPreferences>;

export const PREFERENCE_DEFAULTS: UserPreferences = {
    liked_genres: [],
    liked_channels: [],
    passive_reps_for_known: 3,
    active_reps_for_known: 5,
    known_word_color: '#388e3c',
    learning_word_color: '#f57c00',
    unknown_word_color: '#d32f2f',
};

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function getPreferences(token: string): Promise<UserPreferences> {
    const res = await fetch('/api/v1/settings/preferences', { headers: authHeaders(token) });
    if (!res.ok) throw new Error('Failed to fetch preferences');
    return res.json() as Promise<UserPreferences>;
}

export async function updatePreferences(
    token: string,
    update: UserPreferencesUpdate,
): Promise<UserPreferences> {
    const res = await fetch('/api/v1/settings/preferences', {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify(update),
    });
    if (!res.ok) throw new Error('Failed to update preferences');
    return res.json() as Promise<UserPreferences>;
}
