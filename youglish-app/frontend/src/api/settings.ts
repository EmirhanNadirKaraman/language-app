import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';

export type ThemeMode = 'system' | 'light' | 'dark';

export interface UserPreferences {
    liked_genres: string[];
    liked_channels: string[];
    disliked_genres: string[];
    followed_channels: string[];
    disliked_channels: string[];
    channel_names: Record<string, string>;
    passive_reps_for_known: number;
    active_reps_for_known: number;
    known_word_color: string;
    learning_word_color: string;
    unknown_word_color: string;
    reminders_enabled: boolean;
    theme_mode: ThemeMode;
    // dark_mode is kept on the wire for legacy compatibility; theme_mode is
    // the source of truth. Read either, but write theme_mode in new code.
    dark_mode: boolean;
    auto_mark_known: boolean;
}

export type UserPreferencesUpdate = Partial<UserPreferences>;

export type ChannelAction = 'follow' | 'like' | 'dislike' | 'clear';
export type GenreAction   = 'like' | 'dislike' | 'clear';

export const PREFERENCE_DEFAULTS: UserPreferences = {
    liked_genres: [],
    liked_channels: [],
    disliked_genres: [],
    followed_channels: [],
    disliked_channels: [],
    channel_names: {},
    passive_reps_for_known: 3,
    active_reps_for_known: 5,
    known_word_color: '#388e3c',
    learning_word_color: '#f57c00',
    unknown_word_color: '#d32f2f',
    reminders_enabled: true,
    theme_mode: 'system',
    dark_mode: false,
    auto_mark_known: false,
};

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// All settings fetches go through assertOkJson so a 401 triggers the shared
// auth:expired flow in _http.ts (clears auth + dispatches the event Layout
// listens for). Non-401 errors surface as readable messages for the caller.

export async function getPreferences(token: string): Promise<UserPreferences> {
    const res = await fetch(apiUrl('/api/v1/settings/preferences'), { headers: authHeaders(token) });
    return assertOkJson<UserPreferences>(res, 'Failed to fetch preferences');
}

export async function updatePreferences(
    token: string,
    update: UserPreferencesUpdate,
): Promise<UserPreferences> {
    const res = await fetch(apiUrl('/api/v1/settings/preferences'), {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify(update),
    });
    return assertOkJson<UserPreferences>(res, 'Failed to update preferences');
}

export async function updateChannelPreference(
    token: string,
    channelId: string,
    channelName: string,
    action: ChannelAction,
): Promise<UserPreferences> {
    const res = await fetch(apiUrl('/api/v1/settings/channel-preference'), {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify({ channel_id: channelId, channel_name: channelName, action }),
    });
    return assertOkJson<UserPreferences>(res, 'Failed to update channel preference');
}

export async function updateGenrePreference(
    token: string,
    genre: string,
    action: GenreAction,
): Promise<UserPreferences> {
    const res = await fetch(apiUrl('/api/v1/settings/genre-preference'), {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify({ genre, action }),
    });
    return assertOkJson<UserPreferences>(res, 'Failed to update genre preference');
}
