import type { SearchResult } from '../types';
import type { VideoRecommendation, SentenceRecommendation } from '../types';

export function videoRecToSearchResult(r: VideoRecommendation): SearchResult {
    return {
        video_id:       r.video_id,
        title:          r.title,
        thumbnail_url:  r.thumbnail_url,
        language:       r.language,
        start_time:     r.start_time,
        start_time_int: r.start_time_int,
        content:        '',
        surface_form:   null,
        match_type:     'recommendation',
    };
}

export function sentenceRecToSearchResult(
    r: SentenceRecommendation,
    language: string,
): SearchResult {
    return {
        video_id:       r.video_id,
        title:          r.video_title,
        thumbnail_url:  r.thumbnail_url,
        language,
        start_time:     r.start_time,
        start_time_int: r.start_time_int,
        content:        r.content,
        surface_form:   null,
        match_type:     'recommendation',
    };
}

export function formatDuration(totalSeconds: number): string {
    const m = Math.floor(totalSeconds / 60);
    const s = Math.floor(totalSeconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}
