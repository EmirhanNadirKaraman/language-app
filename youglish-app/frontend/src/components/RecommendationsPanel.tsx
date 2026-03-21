import { useState } from 'react';
import { useRecommendations } from '../hooks/useRecommendations';
import {
    ItemRecommendationCard,
    VideoRecommendationCard,
    SentenceRecommendationCard,
} from './RecommendationCards';
import { InsightsSection } from './InsightsSection';
import { PrepView } from './PrepView';
import type { InsightItem, SearchResult } from '../types';
import type { WordColorScheme } from '../config/wordColors';

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

interface Props {
    token:              string;
    language:           string;
    onLanguageChange:   (lang: string) => void;
    onWatch:            (result: SearchResult) => void;
    onPractice:         (language: string) => void;
    onPracticeItem:     (itemId: number, itemType: string, language: string) => void;
    onPracticeSentence: (result: SearchResult) => void;
    onSearch:           (term: string) => void;
    onClose:            () => void;
    wordColors?:        WordColorScheme;
    passiveMax?:        number;
}

export function RecommendationsPanel({
    token, language, onLanguageChange,
    onWatch, onPractice, onPracticeItem, onPracticeSentence, onSearch, onClose, wordColors, passiveMax,
}: Props) {
    const { items, phrases, videos, sentences, noTargetItems, loading, error, refresh } =
        useRecommendations(token, language);
    const [prepItem, setPrepItem] = useState<InsightItem | null>(null);

    const sectionLabel: React.CSSProperties = {
        fontSize: '11px',
        fontWeight: 700,
        color: '#888',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        margin: '16px 0 8px',
    };

    const emptyText: React.CSSProperties = {
        fontSize: '13px',
        color: '#aaa',
        padding: '8px 0',
    };

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            padding: '16px 20px',
            background: '#fafafa',
            marginBottom: '16px',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h2 style={{ margin: 0, fontSize: '16px', color: '#1a237e' }}>For You</h2>
                <button
                    onClick={onClose}
                    style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#888' }}
                    aria-label="Close"
                >
                    ×
                </button>
            </div>

            {/* Controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <select
                    value={language}
                    onChange={e => onLanguageChange(e.target.value)}
                    style={{
                        padding: '5px 10px',
                        border: '1px solid #ccc',
                        borderRadius: '5px',
                        fontSize: '13px',
                        background: '#fff',
                        cursor: 'pointer',
                    }}
                >
                    <option value="">Select language…</option>
                    {LANGUAGES.map(l => (
                        <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                </select>

                <button
                    onClick={refresh}
                    disabled={loading || !language}
                    style={{
                        padding: '5px 14px',
                        border: '1px solid #c5cae9',
                        borderRadius: '5px',
                        background: '#fff',
                        color: '#1a237e',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: loading || !language ? 'not-allowed' : 'pointer',
                        opacity: loading || !language ? 0.5 : 1,
                    }}
                >
                    {loading ? 'Loading…' : 'Refresh'}
                </button>
            </div>

            {/* No language selected */}
            {!language && (
                <p style={emptyText}>Select a language above to see recommendations.</p>
            )}

            {/* Error */}
            {error && (
                <p style={{ fontSize: '13px', color: '#c62828', marginTop: '10px' }}>{error}</p>
            )}

            {/* Prep view — replaces panel content when an insight item is selected */}
            {language && prepItem && (
                <PrepView
                    token={token}
                    item={prepItem}
                    language={language}
                    onClose={() => setPrepItem(null)}
                    onStartPractice={(itemId, itemType, lang) => {
                        setPrepItem(null);
                        onPracticeItem(itemId, itemType, lang);
                    }}
                />
            )}

            {/* Insights section — always visible when language is set and prep is not open */}
            {language && !prepItem && (
                <InsightsSection
                    token={token}
                    language={language}
                    onItemClick={setPrepItem}
                />
            )}

            {/* Content */}
            {language && !loading && !error && !prepItem && (
                <>
                    {/* Words */}
                    <p style={sectionLabel}>Words</p>
                    {items.length === 0 ? (
                        <p style={emptyText}>
                            Mark words as &ldquo;learning&rdquo; while watching videos to get word recommendations.
                        </p>
                    ) : (
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                            {items.map(rec => (
                                <ItemRecommendationCard
                                    key={`${rec.item_type}-${rec.item_id}`}
                                    rec={rec}
                                    token={token}
                                    language={language}
                                    onSearch={onSearch}
                                    onPractice={onPractice}
                                    onStatusChange={refresh}
                                    wordColors={wordColors}
                                    passiveMax={passiveMax}
                                />
                            ))}
                        </div>
                    )}

                    {/* Phrases */}
                    <p style={sectionLabel}>Phrases</p>
                    {phrases.length === 0 ? (
                        <p style={emptyText}>
                            Browse phrases via Search, mark them as &ldquo;learning&rdquo; to start tracking them here.
                        </p>
                    ) : (
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                            {phrases.map(rec => (
                                <ItemRecommendationCard
                                    key={`phrase-${rec.item_id}`}
                                    rec={rec}
                                    token={token}
                                    language={language}
                                    onSearch={onSearch}
                                    onPractice={onPractice}
                                    onStatusChange={refresh}
                                    wordColors={wordColors}
                                    passiveMax={passiveMax}
                                />
                            ))}
                        </div>
                    )}

                    {/* Videos */}
                    <p style={sectionLabel}>Videos</p>
                    {videos.length === 0 ? (
                        <p style={emptyText}>
                            {noTargetItems
                                ? 'Watch videos and mark words to get video recommendations.'
                                : 'No video recommendations yet.'}
                        </p>
                    ) : (
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                            {videos.map(rec => (
                                <VideoRecommendationCard
                                    key={rec.video_id}
                                    rec={rec}
                                    onWatch={onWatch}
                                />
                            ))}
                        </div>
                    )}

                    {/* Sentences */}
                    <p style={sectionLabel}>Sentences</p>
                    {sentences.length === 0 ? (
                        <p style={emptyText}>
                            No matching sentences found. Try marking more words as &ldquo;learning&rdquo;.
                        </p>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {sentences.map(rec => (
                                <SentenceRecommendationCard
                                    key={rec.sentence_id}
                                    rec={rec}
                                    language={language}
                                    onWatch={onWatch}
                                    onPractice={onPracticeSentence}
                                />
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
