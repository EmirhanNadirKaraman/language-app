import { useEffect, useState } from 'react';
import { fetchFollowedChannelVideos } from '../api/recommendations';
import { VideoRecommendationCard } from './RecommendationCards';
import type { VideoRecommendation, SearchResult } from '../types';
import type { ChannelAction, GenreAction, UserPreferences } from '../api/settings';

interface Props {
    token:           string;
    language:        string;
    prefs:           UserPreferences;
    onWatch:         (result: SearchResult) => void;
    onChannelAction: (channelId: string, channelName: string, action: ChannelAction) => Promise<void>;
    onGenreAction:   (genre: string, action: GenreAction) => Promise<void>;
}

export function FollowedChannelsSection({
    token, language, prefs, onWatch, onChannelAction, onGenreAction,
}: Props) {
    const [videos, setVideos] = useState<VideoRecommendation[]>([]);
    const [loading, setLoading] = useState(false);

    const followed = prefs.followed_channels ?? [];

    useEffect(() => {
        if (!language || followed.length === 0) {
            setVideos([]);
            return;
        }
        let cancelled = false;
        setLoading(true);
        fetchFollowedChannelVideos(token, language)
            .then(r => { if (!cancelled) setVideos(r.videos); })
            .catch(() => { if (!cancelled) setVideos([]); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token, language, followed.join(',')]);

    if (followed.length === 0) return null;

    return (
        <>
            <p style={{
                fontSize: '11px', fontWeight: 700, color: '#888',
                textTransform: 'uppercase', letterSpacing: '0.06em',
                margin: '16px 0 8px',
            }}>
                Followed Channels
            </p>
            {loading ? (
                <p style={{ fontSize: '13px', color: '#aaa', padding: '8px 0' }}>Loading…</p>
            ) : videos.length === 0 ? (
                <p style={{ fontSize: '13px', color: '#aaa', padding: '8px 0' }}>
                    No videos found from followed channels in this language.
                </p>
            ) : (
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    {videos.map(rec => (
                        <VideoRecommendationCard
                            key={rec.video_id}
                            rec={rec}
                            onWatch={onWatch}
                            prefs={prefs}
                            onChannelAction={onChannelAction}
                            onGenreAction={onGenreAction}
                        />
                    ))}
                </div>
            )}
        </>
    );
}
