import type { PlaylistResult } from '../types';

export async function generatePlaylist(
    token: string,
    itemIds: number[],
    language: string,
    maxVideos: number,
): Promise<PlaylistResult> {
    const res = await fetch('/api/v1/playlists/generate', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            item_ids: itemIds,
            item_type: 'word',
            language,
            max_videos: maxVideos,
        }),
    });
    if (!res.ok) throw new Error('Failed to generate playlist');
    return res.json();
}
