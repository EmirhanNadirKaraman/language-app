import { useRef, useState } from 'react';
import type { PlaylistResult, PlaylistVideo, SearchResult } from '../types';
import { fetchItemRecommendations } from '../api/recommendations';
import { lookupWord } from '../api/words';
import { generatePlaylist } from '../api/playlists';
import { formatDuration } from '../utils/recommendationUtils';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LANGUAGES = [
    { code: 'de', label: 'German' },
    { code: 'en', label: 'English' },
    { code: 'fr', label: 'French' },
    { code: 'es', label: 'Spanish' },
    { code: 'it', label: 'Italian' },
    { code: 'pt', label: 'Portuguese' },
    { code: 'ja', label: 'Japanese' },
    { code: 'ru', label: 'Russian' },
    { code: 'ko', label: 'Korean' },
    { code: 'tr', label: 'Turkish' },
    { code: 'pl', label: 'Polish' },
    { code: 'sv', label: 'Swedish' },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Target {
    item_id: number;
    display_text: string;
}

interface Props {
    token: string;
    language: string;
    onLanguageChange: (lang: string) => void;
    onWatch: (result: SearchResult) => void;
    onClose: () => void;
}

// ---------------------------------------------------------------------------
// PlaylistPanel
// ---------------------------------------------------------------------------

export function PlaylistPanel({ token, language, onLanguageChange, onWatch, onClose }: Props) {
    const [view, setView] = useState<'build' | 'result'>('build');
    const [targets, setTargets] = useState<Target[]>([]);
    const [maxVideos, setMaxVideos] = useState(5);
    const [loadingRecs, setLoadingRecs] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<PlaylistResult | null>(null);

    const [addInput, setAddInput] = useState('');
    const [addError, setAddError] = useState<string | null>(null);
    const [addLoading, setAddLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    function addTarget(t: Target) {
        setTargets(prev => prev.some(x => x.item_id === t.item_id) ? prev : [...prev, t]);
    }

    function removeTarget(item_id: number) {
        setTargets(prev => prev.filter(t => t.item_id !== item_id));
    }

    async function handleLoadRecommended() {
        if (!language) return;
        setLoadingRecs(true);
        try {
            const res = await fetchItemRecommendations(token, language, 'word', 20);
            res.items.forEach(item => addTarget({ item_id: item.item_id, display_text: item.display_text }));
        } catch {
            // silently ignore — user can still add manually
        } finally {
            setLoadingRecs(false);
        }
    }

    async function handleAddWord() {
        const text = addInput.trim();
        if (!text || !language) return;
        setAddLoading(true);
        setAddError(null);
        try {
            const res = await lookupWord(token, text, language);
            if (!res) {
                setAddError(`"${text}" not found in vocabulary`);
            } else {
                addTarget({ item_id: res.word_id, display_text: res.lemma });
                setAddInput('');
            }
        } catch {
            setAddError('Lookup failed. Try again.');
        } finally {
            setAddLoading(false);
            inputRef.current?.focus();
        }
    }

    async function handleGenerate() {
        if (!language || targets.length === 0) return;
        setGenerating(true);
        setError(null);
        try {
            const res = await generatePlaylist(token, targets.map(t => t.item_id), language, maxVideos);
            setResult(res);
            setView('result');
        } catch {
            setError('Failed to generate playlist. Try again.');
        } finally {
            setGenerating(false);
        }
    }

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            padding: '16px 20px',
            background: '#fafafa',
            marginBottom: '16px',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {view === 'result' && (
                        <button
                            onClick={() => setView('build')}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1a237e', fontSize: '13px', fontWeight: 600, padding: 0 }}
                        >
                            ← Back
                        </button>
                    )}
                    <h2 style={{ margin: 0, fontSize: '16px', color: '#1a237e' }}>
                        {view === 'build' ? 'Build Playlist' : 'Playlist'}
                    </h2>
                </div>
                <button
                    onClick={onClose}
                    style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#888' }}
                    aria-label="Close"
                >
                    ×
                </button>
            </div>

            {view === 'build' && (
                <BuildView
                    language={language}
                    onLanguageChange={onLanguageChange}
                    targets={targets}
                    onRemoveTarget={removeTarget}
                    maxVideos={maxVideos}
                    onMaxVideosChange={setMaxVideos}
                    addInput={addInput}
                    onAddInputChange={setAddInput}
                    addLoading={addLoading}
                    addError={addError}
                    onAddWord={handleAddWord}
                    inputRef={inputRef}
                    loadingRecs={loadingRecs}
                    onLoadRecommended={handleLoadRecommended}
                    generating={generating}
                    error={error}
                    onGenerate={handleGenerate}
                />
            )}

            {view === 'result' && result && (
                <ResultView result={result} onWatch={onWatch} />
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// BuildView
// ---------------------------------------------------------------------------

interface BuildViewProps {
    language: string;
    onLanguageChange: (lang: string) => void;
    targets: Target[];
    onRemoveTarget: (id: number) => void;
    maxVideos: number;
    onMaxVideosChange: (n: number) => void;
    addInput: string;
    onAddInputChange: (s: string) => void;
    addLoading: boolean;
    addError: string | null;
    onAddWord: () => void;
    inputRef: React.RefObject<HTMLInputElement>;
    loadingRecs: boolean;
    onLoadRecommended: () => void;
    generating: boolean;
    error: string | null;
    onGenerate: () => void;
}

function BuildView({
    language, onLanguageChange,
    targets, onRemoveTarget,
    maxVideos, onMaxVideosChange,
    addInput, onAddInputChange, addLoading, addError, onAddWord, inputRef,
    loadingRecs, onLoadRecommended,
    generating, error, onGenerate,
}: BuildViewProps) {
    const inputStyle: React.CSSProperties = {
        padding: '6px 10px',
        border: '1px solid #ccc',
        borderRadius: '5px',
        fontSize: '13px',
        background: '#fff',
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Language */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <select
                    value={language}
                    onChange={e => onLanguageChange(e.target.value)}
                    style={{ ...inputStyle, cursor: 'pointer' }}
                >
                    <option value="">Select language…</option>
                    {LANGUAGES.map(l => (
                        <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                </select>

                <button
                    onClick={onLoadRecommended}
                    disabled={!language || loadingRecs}
                    style={{
                        padding: '6px 14px',
                        borderRadius: '5px',
                        border: '1px solid #c5cae9',
                        background: '#fff',
                        color: '#1a237e',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: !language || loadingRecs ? 'not-allowed' : 'pointer',
                        opacity: !language || loadingRecs ? 0.5 : 1,
                    }}
                >
                    {loadingRecs ? 'Loading…' : 'Add recommended words'}
                </button>
            </div>

            {/* Manual add */}
            <div>
                <div style={{ display: 'flex', gap: '6px' }}>
                    <input
                        ref={inputRef}
                        style={{ ...inputStyle, flex: 1, minWidth: 0 }}
                        placeholder="Type a word to add…"
                        value={addInput}
                        onChange={e => onAddInputChange(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') onAddWord(); }}
                        disabled={!language || addLoading}
                    />
                    <button
                        onClick={onAddWord}
                        disabled={!addInput.trim() || !language || addLoading}
                        style={{
                            padding: '6px 14px',
                            borderRadius: '5px',
                            border: 'none',
                            background: '#1a237e',
                            color: '#fff',
                            fontSize: '13px',
                            fontWeight: 600,
                            cursor: !addInput.trim() || !language || addLoading ? 'not-allowed' : 'pointer',
                            opacity: !addInput.trim() || !language || addLoading ? 0.5 : 1,
                            flexShrink: 0,
                        }}
                    >
                        {addLoading ? '…' : 'Add'}
                    </button>
                </div>
                {addError && (
                    <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#c62828' }}>{addError}</p>
                )}
            </div>

            {/* Target chips */}
            {targets.length > 0 && (
                <div>
                    <p style={{ margin: '0 0 6px', fontSize: '11px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Targets ({targets.length})
                    </p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {targets.map(t => (
                            <span
                                key={t.item_id}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                    padding: '3px 8px 3px 10px',
                                    background: '#e8eaf6',
                                    borderRadius: '12px',
                                    fontSize: '13px',
                                    color: '#1a237e',
                                    fontWeight: 500,
                                }}
                            >
                                {t.display_text}
                                <button
                                    onClick={() => onRemoveTarget(t.item_id)}
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        cursor: 'pointer',
                                        color: '#7986cb',
                                        fontSize: '14px',
                                        lineHeight: 1,
                                        padding: '0 2px',
                                    }}
                                    aria-label={`Remove ${t.display_text}`}
                                >
                                    ×
                                </button>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Max videos */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <label style={{ fontSize: '13px', color: '#444', fontWeight: 600, whiteSpace: 'nowrap' }}>
                    Max videos
                </label>
                <input
                    type="number"
                    min={1}
                    max={10}
                    value={maxVideos}
                    onChange={e => onMaxVideosChange(Math.max(1, Math.min(10, parseInt(e.target.value, 10) || 1)))}
                    style={{ ...inputStyle, width: '64px' }}
                />
            </div>

            {error && (
                <p style={{ margin: 0, fontSize: '13px', color: '#c62828' }}>{error}</p>
            )}

            {/* Generate */}
            <div>
                <button
                    onClick={onGenerate}
                    disabled={!language || targets.length === 0 || generating}
                    style={{
                        padding: '9px 24px',
                        background: '#1a237e',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '14px',
                        fontWeight: 600,
                        cursor: !language || targets.length === 0 || generating ? 'not-allowed' : 'pointer',
                        opacity: !language || targets.length === 0 || generating ? 0.5 : 1,
                    }}
                >
                    {generating ? 'Generating…' : 'Generate playlist'}
                </button>
                {!language && (
                    <span style={{ marginLeft: '10px', fontSize: '12px', color: '#aaa' }}>Select a language first</span>
                )}
                {language && targets.length === 0 && (
                    <span style={{ marginLeft: '10px', fontSize: '12px', color: '#aaa' }}>Add at least one word</span>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// ResultView
// ---------------------------------------------------------------------------

function ResultView({ result, onWatch }: { result: PlaylistResult; onWatch: (r: SearchResult) => void }) {
    const { coverage, videos } = result;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Coverage summary */}
            <div style={{ background: '#fff', border: '1px solid #e8eaf6', borderRadius: '6px', padding: '12px 14px' }}>
                <div style={{ marginBottom: '6px' }}>
                    <div style={{ display: 'flex', height: '6px', borderRadius: '3px', overflow: 'hidden', background: '#e8e8e8' }}>
                        <div style={{ width: `${coverage.coverage_pct}%`, background: '#3f51b5', transition: 'width 0.4s' }} />
                    </div>
                </div>
                <div style={{ fontSize: '13px', color: '#444' }}>
                    <strong>{coverage.covered_count} of {coverage.target_count}</strong> target words covered
                    {' '}<span style={{ color: '#888' }}>({coverage.coverage_pct}%)</span>
                    {' '}across <strong>{coverage.video_count}</strong> video{coverage.video_count !== 1 ? 's' : ''}
                </div>
                {coverage.uncovered_item_ids.length > 0 && (
                    <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#888' }}>
                        {coverage.uncovered_item_ids.length} word{coverage.uncovered_item_ids.length !== 1 ? 's' : ''} not found in any video
                    </p>
                )}
                {videos.length === 0 && (
                    <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#aaa' }}>
                        No videos found for these words. Try different targets or a different language.
                    </p>
                )}
            </div>

            {/* Video cards */}
            {videos.map((v, i) => (
                <PlaylistVideoCard key={v.video_id} video={v} position={i + 1} onWatch={onWatch} />
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// PlaylistVideoCard
// ---------------------------------------------------------------------------

function PlaylistVideoCard({
    video, position, onWatch,
}: {
    video: PlaylistVideo;
    position: number;
    onWatch: (r: SearchResult) => void;
}) {
    const result: SearchResult = {
        video_id:       video.video_id,
        title:          video.title,
        thumbnail_url:  video.thumbnail_url,
        language:       video.language,
        start_time:     video.start_time,
        start_time_int: video.start_time_int,
        content:        video.content,
        surface_form:   null,
        match_type:     'playlist',
    };

    return (
        <div style={{
            display: 'flex',
            gap: '12px',
            background: '#fff',
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            overflow: 'hidden',
            alignItems: 'stretch',
        }}>
            {/* Position number */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                flexShrink: 0,
                background: '#f5f6ff',
                color: '#9fa8da',
                fontSize: '13px',
                fontWeight: 700,
            }}>
                {position}
            </div>

            {/* Thumbnail */}
            <div style={{ position: 'relative', width: '120px', flexShrink: 0, background: '#000' }}>
                <img
                    src={video.thumbnail_url}
                    alt={video.title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.9, display: 'block' }}
                />
                <span style={{
                    position: 'absolute', bottom: '4px', right: '4px',
                    background: 'rgba(0,0,0,0.75)', color: '#fff',
                    padding: '1px 4px', borderRadius: '3px', fontSize: '10px',
                }}>
                    {formatDuration(video.start_time)}
                </span>
            </div>

            {/* Info */}
            <div style={{ flex: 1, padding: '10px 10px 10px 0', display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 }}>
                <div style={{
                    fontSize: '14px',
                    fontWeight: 600,
                    color: '#222',
                    lineHeight: 1.3,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical' as const,
                    overflow: 'hidden',
                }}>
                    {video.title}
                </div>
                <span style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    background: '#e8eaf6',
                    color: '#3f51b5',
                    borderRadius: '10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    alignSelf: 'flex-start',
                }}>
                    {video.covered_count} word{video.covered_count !== 1 ? 's' : ''}
                </span>
                <div style={{ marginTop: 'auto' }}>
                    <button
                        onClick={() => onWatch(result)}
                        style={{
                            padding: '5px 14px',
                            background: '#1a237e',
                            color: '#fff',
                            border: 'none',
                            borderRadius: '5px',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: 'pointer',
                        }}
                    >
                        Watch
                    </button>
                </div>
            </div>
        </div>
    );
}
