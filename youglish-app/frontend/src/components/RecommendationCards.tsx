import { useState } from 'react';
import type { ItemRecommendation, VideoRecommendation, SentenceRecommendation } from '../types';
import { setItemStatus } from '../api/words';
import { formatDuration } from '../utils/recommendationUtils';
import type { SearchResult } from '../types';
import type { WordColorScheme } from '../config/wordColors';
import { WORD_COLORS } from '../config/wordColors';
import type { ChannelAction, GenreAction, UserPreferences } from '../api/settings';

// ---------------------------------------------------------------------------
// Shared: reason tag
// ---------------------------------------------------------------------------

type ReasonVariant = 'due' | 'mistake' | 'freq' | 'learning' | 'coverage' | 'new';

const REASON_STYLES: Record<ReasonVariant, { bg: string; color: string }> = {
    due:      { bg: '#fff3e0', color: '#e65100' },
    mistake:  { bg: '#fce4ec', color: '#c62828' },
    freq:     { bg: '#e3f2fd', color: '#1565c0' },
    learning: { bg: '#e8f5e9', color: '#2e7d32' },
    coverage: { bg: '#e8f5e9', color: '#2e7d32' },
    new:      { bg: '#f5f5f5', color: '#616161' },
};

function reasonVariant(reason: string): ReasonVariant {
    if (reason === 'review due')              return 'due';
    if (reason === 'recent mistake')          return 'mistake';
    if (reason === 'frequently encountered') return 'freq';
    if (reason === 'in study list')          return 'learning';
    return 'new';
}

function ReasonTag({ label, variant }: { label: string; variant: ReasonVariant }) {
    const { bg, color } = REASON_STYLES[variant];
    return (
        <span style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: '10px',
            fontSize: '11px',
            fontWeight: 600,
            background: bg,
            color,
            whiteSpace: 'nowrap',
        }}>
            {label}
        </span>
    );
}

function ReasonRow({ reasons }: { reasons: string[] }) {
    if (reasons.length === 0) return null;
    return (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', margin: '6px 0' }}>
            {reasons.slice(0, 3).map(r => (
                <ReasonTag key={r} label={r} variant={reasonVariant(r)} />
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Shared: action button
// ---------------------------------------------------------------------------

function ActionButton({
    label,
    onClick,
    primary = false,
    disabled = false,
}: {
    label: string;
    onClick: () => void;
    primary?: boolean;
    disabled?: boolean;
}) {
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            style={{
                padding: '5px 12px',
                borderRadius: '5px',
                border: primary ? 'none' : '1px solid #c5cae9',
                background: primary ? '#1a237e' : '#fff',
                color: primary ? '#fff' : '#1a237e',
                fontSize: '12px',
                fontWeight: 600,
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.5 : 1,
            }}
        >
            {label}
        </button>
    );
}

// ---------------------------------------------------------------------------
// PassiveLevelPips
// ---------------------------------------------------------------------------

function PassiveLevelPips({ level, max }: { level: number; max: number }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
            {Array.from({ length: max }, (_, i) => (
                <span
                    key={i}
                    style={{
                        width: 8,
                        height: 8,
                        borderRadius: 2,
                        background: i < level ? '#fb8c00' : '#e0e0e0',
                        display: 'inline-block',
                    }}
                />
            ))}
            <span style={{ fontSize: '10px', color: '#aaa', marginLeft: '4px' }}>
                {level}/{max}
            </span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Status dot
// ---------------------------------------------------------------------------

function StatusDot({ status, wordColors }: { status: string | null; wordColors: WordColorScheme }) {
    const colorMap: Record<string, string> = {
        unknown:  wordColors.unknown.color as string,
        learning: wordColors.learning.color as string,
        known:    wordColors.known.color as string,
    };
    const color = status ? colorMap[status] ?? '#bbb' : '#bbb';
    const label = status ?? 'new';
    return (
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#666' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
            {label}
        </span>
    );
}

// ---------------------------------------------------------------------------
// ItemRecommendationCard
// ---------------------------------------------------------------------------

interface ItemCardProps {
    rec:            ItemRecommendation;
    token:          string;
    onSearch:       (displayText: string) => void;
    onPractice:     (language: string) => void;
    language:       string;
    onStatusChange: () => void;
    wordColors?:    WordColorScheme;
    passiveMax?:    number;
}

export function ItemRecommendationCard({
    rec, token, onSearch, onPractice, language, onStatusChange, wordColors, passiveMax = 5,
}: ItemCardProps) {
    const colors = wordColors ?? WORD_COLORS;
    const [status, setStatus] = useState(rec.current_status);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(false);

    const canMarkLearning = status !== 'learning' && status !== 'known';
    const itemTypeLabel = rec.item_type === 'grammar_rule' ? 'grammar' : rec.item_type;

    async function handleMarkLearning() {
        setSaving(true);
        setSaveError(false);
        const prev = status;
        setStatus('learning');
        try {
            await setItemStatus(token, rec.item_type, rec.item_id, 'learning');
            onStatusChange();
        } catch {
            setStatus(prev);
            setSaveError(true);
        } finally {
            setSaving(false);
        }
    }

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            padding: '12px 14px',
            background: '#fff',
            minWidth: '200px',
            maxWidth: '260px',
            flexShrink: 0,
        }}>
            {/* Header row */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '4px' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: '#111', wordBreak: 'break-word' }}>
                    {rec.display_text}
                </span>
                <span style={{
                    fontSize: '10px',
                    fontWeight: 600,
                    color: '#888',
                    background: '#f5f5f5',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    whiteSpace: 'nowrap',
                    marginTop: '3px',
                }}>
                    {itemTypeLabel}
                </span>
            </div>

            {/* Secondary text (lemma) */}
            {rec.secondary_text && (
                <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px' }}>
                    {rec.secondary_text}
                </div>
            )}

            {/* Status + level */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '2px' }}>
                <StatusDot status={status} wordColors={colors} />
                <PassiveLevelPips level={rec.passive_level} max={passiveMax} />
            </div>

            {/* Reason tags */}
            <ReasonRow reasons={rec.reasons} />

            {/* Error */}
            {saveError && (
                <div style={{ fontSize: '11px', color: '#c62828', marginBottom: '4px' }}>
                    Failed to save. Try again.
                </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
                {canMarkLearning && (
                    <ActionButton
                        label={saving ? 'Saving…' : 'Mark Learning'}
                        onClick={handleMarkLearning}
                        primary
                        disabled={saving}
                    />
                )}
                {status === 'learning' && (
                    <span style={{ fontSize: '11px', color: '#2e7d32', fontWeight: 600, alignSelf: 'center' }}>
                        In study list
                    </span>
                )}
                <ActionButton label="Search" onClick={() => onSearch(rec.display_text)} />
                <ActionButton label="Practice" onClick={() => onPractice(language)} />
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// VideoRecommendationCard
// ---------------------------------------------------------------------------

interface VideoCardProps {
    rec:             VideoRecommendation;
    onWatch:         (result: SearchResult) => void;
    prefs?:          UserPreferences;
    onChannelAction?: (channelId: string, channelName: string, action: ChannelAction) => Promise<void>;
    onGenreAction?:  (genre: string, action: GenreAction) => Promise<void>;
}

export function VideoRecommendationCard({ rec, onWatch, prefs, onChannelAction, onGenreAction }: VideoCardProps) {
    const [saving, setSaving] = useState(false);

    const reasons: string[] = [];
    if (rec.covered_count > 0) reasons.push(`covers ${rec.covered_count} word${rec.covered_count !== 1 ? 's' : ''}`);

    const result: SearchResult = {
        video_id:       rec.video_id,
        title:          rec.title,
        thumbnail_url:  rec.thumbnail_url,
        language:       rec.language,
        start_time:     rec.start_time,
        start_time_int: rec.start_time_int,
        content:        '',
        surface_form:   null,
        match_type:     'recommendation',
    };

    // Channel preference state derived from prefs
    const channelId   = rec.channel_id ?? null;
    const channelName = rec.channel_name ?? '';
    const genre       = rec.genre ?? null;
    const isFollowed  = channelId ? (prefs?.followed_channels ?? []).includes(channelId) : false;
    const isLikedCh   = channelId ? (prefs?.liked_channels ?? []).includes(channelId) : false;
    const isDislikedCh = channelId ? (prefs?.disliked_channels ?? []).includes(channelId) : false;
    const isLikedG    = genre ? (prefs?.liked_genres ?? []).includes(genre) : false;
    const isDislikedG = genre ? (prefs?.disliked_genres ?? []).includes(genre) : false;

    async function handleChannelAction(action: ChannelAction) {
        if (!channelId || !onChannelAction || saving) return;
        setSaving(true);
        try {
            // Toggle: clicking active action clears it
            const effective = (
                (action === 'follow' && isFollowed) ||
                (action === 'like' && isLikedCh) ||
                (action === 'dislike' && isDislikedCh)
            ) ? 'clear' : action;
            await onChannelAction(channelId, channelName, effective);
        } finally {
            setSaving(false);
        }
    }

    async function handleGenreAction(action: GenreAction) {
        if (!genre || !onGenreAction || saving) return;
        setSaving(true);
        try {
            const effective = (
                (action === 'like' && isLikedG) ||
                (action === 'dislike' && isDislikedG)
            ) ? 'clear' : action;
            await onGenreAction(genre, effective);
        } finally {
            setSaving(false);
        }
    }

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            overflow: 'hidden',
            background: '#fff',
            display: 'flex',
            flexDirection: 'column',
            minWidth: '220px',
            maxWidth: '280px',
            flexShrink: 0,
        }}>
            {/* Thumbnail */}
            <div style={{ position: 'relative', paddingTop: '56.25%', background: '#000', flexShrink: 0 }}>
                <img
                    src={rec.thumbnail_url}
                    alt={rec.title}
                    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.9 }}
                />
                <span style={{
                    position: 'absolute', bottom: '6px', right: '6px',
                    background: 'rgba(0,0,0,0.75)', color: '#fff',
                    padding: '1px 5px', borderRadius: '3px', fontSize: '11px',
                }}>
                    {formatDuration(rec.duration)}
                </span>
            </div>

            <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
                {/* Title */}
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#222', lineHeight: 1.3,
                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}>
                    {rec.title}
                </div>

                {/* Channel name */}
                {channelName && (
                    <div style={{ fontSize: '11px', color: '#888' }}>{channelName}</div>
                )}

                {/* Timestamp */}
                <div style={{ fontSize: '11px', color: '#888' }}>
                    starts at {formatDuration(rec.start_time)}
                </div>

                {/* Reason tags */}
                {reasons.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {reasons.map(r => (
                            <ReasonTag key={r} label={r} variant="coverage" />
                        ))}
                    </div>
                )}

                {/* Channel preference buttons */}
                {channelId && onChannelAction && (
                    <div style={{ display: 'flex', gap: '4px', marginTop: '4px', flexWrap: 'wrap' }}>
                        <PrefButton
                            label="Follow"
                            active={isFollowed}
                            activeColor="#1a237e"
                            onClick={() => handleChannelAction('follow')}
                            disabled={saving}
                        />
                        <PrefButton
                            label="Like"
                            active={isLikedCh}
                            activeColor="#2e7d32"
                            onClick={() => handleChannelAction('like')}
                            disabled={saving}
                        />
                        <PrefButton
                            label="Dislike"
                            active={isDislikedCh}
                            activeColor="#c62828"
                            onClick={() => handleChannelAction('dislike')}
                            disabled={saving}
                        />
                    </div>
                )}

                {/* Genre preference buttons */}
                {genre && onGenreAction && (
                    <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                        <span style={{ fontSize: '10px', color: '#aaa' }}>{genre}:</span>
                        <PrefButton
                            label="Like"
                            active={isLikedG}
                            activeColor="#1565c0"
                            onClick={() => handleGenreAction('like')}
                            disabled={saving}
                        />
                        <PrefButton
                            label="Dislike"
                            active={isDislikedG}
                            activeColor="#c62828"
                            onClick={() => handleGenreAction('dislike')}
                            disabled={saving}
                        />
                    </div>
                )}

                {/* Action */}
                <div style={{ marginTop: '6px' }}>
                    <ActionButton label="Watch" onClick={() => onWatch(result)} primary />
                </div>
            </div>
        </div>
    );
}

function PrefButton({
    label, active, activeColor, onClick, disabled,
}: {
    label: string;
    active: boolean;
    activeColor: string;
    onClick: () => void;
    disabled: boolean;
}) {
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            style={{
                padding: '2px 8px',
                borderRadius: '10px',
                border: `1px solid ${active ? activeColor : '#e0e0e0'}`,
                background: active ? activeColor : '#fff',
                color: active ? '#fff' : '#888',
                fontSize: '10px',
                fontWeight: 600,
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.6 : 1,
                whiteSpace: 'nowrap',
            }}
        >
            {label}
        </button>
    );
}

// ---------------------------------------------------------------------------
// SentenceRecommendationCard
// ---------------------------------------------------------------------------

interface SentenceCardProps {
    rec:        SentenceRecommendation;
    language:   string;
    onWatch:    (result: SearchResult) => void;
    onPractice: (result: SearchResult) => void;
}

export function SentenceRecommendationCard({ rec, language, onWatch, onPractice }: SentenceCardProps) {
    const reasons: string[] = [];
    if (rec.due_count > 0)
        reasons.push(`${rec.due_count} due for review`);
    if (rec.priority_count > 0)
        reasons.push(`${rec.priority_count} priority word${rec.priority_count !== 1 ? 's' : ''}`);
    if (rec.unknown_count > 0)
        reasons.push(`${rec.unknown_count} new word${rec.unknown_count !== 1 ? 's' : ''}`);

    const result: SearchResult = {
        video_id:       rec.video_id,
        title:          rec.video_title,
        thumbnail_url:  rec.thumbnail_url,
        language,
        start_time:     rec.start_time,
        start_time_int: rec.start_time_int,
        content:        rec.content,
        surface_form:   null,
        match_type:     'recommendation',
    };

    function tagVariant(r: string): ReasonVariant {
        if (r.includes('due'))      return 'due';
        if (r.includes('priority')) return 'freq';
        return 'new';
    }

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            padding: '12px 14px',
            background: '#fff',
        }}>
            {/* Sentence text */}
            <div style={{
                fontSize: '15px',
                lineHeight: 1.5,
                color: '#111',
                marginBottom: '6px',
                fontStyle: 'italic',
            }}>
                &ldquo;{rec.content}&rdquo;
            </div>

            {/* Source */}
            <div style={{ fontSize: '11px', color: '#888', marginBottom: '4px' }}>
                {rec.video_title} &middot; at {formatDuration(rec.start_time)}
            </div>

            {/* Reason tags */}
            {reasons.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', margin: '6px 0' }}>
                    {reasons.map(r => (
                        <ReasonTag key={r} label={r} variant={tagVariant(r)} />
                    ))}
                </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                <ActionButton label="Watch" onClick={() => onWatch(result)} primary />
                <ActionButton label="Practice" onClick={() => onPractice(result)} />
            </div>
        </div>
    );
}
