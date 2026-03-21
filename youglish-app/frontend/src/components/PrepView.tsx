import { useEffect, useState } from 'react';
import type { InsightItem, PrepViewData, GenerateExamplesResponse } from '../types';
import { fetchPrepData, generateExamples } from '../api/insights';

interface Props {
    token: string;
    item: InsightItem;
    language: string;
    onClose: () => void;
    onStartPractice: (itemId: number, itemType: string, language: string) => void;
}

export function PrepView({ token, item, language, onClose, onStartPractice }: Props) {
    const [prep, setPrep] = useState<PrepViewData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [grammarOpen, setGrammarOpen] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [generated, setGenerated] = useState<GenerateExamplesResponse | null>(null);

    useEffect(() => {
        setLoading(true);
        setError(null);
        setGrammarOpen(false);
        setGenerated(null);
        fetchPrepData(token, item.item_id, item.item_type, language)
            .then(data => { setPrep(data); setLoading(false); })
            .catch(() => { setError('Failed to load prep info.'); setLoading(false); });
    }, [token, item.item_id, item.item_type, language]);

    async function handleGenerate() {
        setGenerating(true);
        try {
            const result = await generateExamples(token, item.item_id, item.item_type, language);
            setGenerated(result);
        } catch {
            // silently fail — button stays visible
        } finally {
            setGenerating(false);
        }
    }

    // Merge generated examples into prep data (generated takes precedence)
    const example   = generated?.example   ?? prep?.example   ?? null;
    const templates = generated?.templates ?? prep?.templates  ?? [];
    const hasExamples = generated !== null || (prep?.has_examples ?? false);

    const itemTypeLabel = item.item_type === 'phrase' ? 'phrase' : 'word';

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
            {/* Back button */}
            <button
                onClick={onClose}
                style={{
                    alignSelf: 'flex-start',
                    background: 'none',
                    border: 'none',
                    color: '#1a237e',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    padding: '0 0 12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                }}
            >
                ← Back
            </button>

            {loading && (
                <p style={{ fontSize: '14px', color: '#aaa', padding: '24px 0', textAlign: 'center' }}>
                    Loading prep info…
                </p>
            )}

            {error && (
                <p style={{ fontSize: '13px', color: '#c62828' }}>{error}</p>
            )}

            {!loading && prep && (
                <>
                    {/* Item header */}
                    <div style={{ marginBottom: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '26px', fontWeight: 700, color: '#111' }}>
                                {prep.display_text}
                            </span>
                            <span style={{
                                fontSize: '11px', fontWeight: 600, color: '#888',
                                background: '#f5f5f5', padding: '2px 7px', borderRadius: '4px',
                            }}>
                                {itemTypeLabel}
                            </span>
                        </div>
                        <div style={{ fontSize: '15px', color: '#555', marginTop: '4px' }}>
                            {prep.translation}
                        </div>
                        {prep.grammar_structure && (
                            <div style={{
                                display: 'inline-block',
                                marginTop: '6px',
                                fontSize: '12px',
                                fontWeight: 600,
                                color: '#1565c0',
                                background: '#e3f2fd',
                                padding: '3px 10px',
                                borderRadius: '12px',
                            }}>
                                {prep.grammar_structure}
                            </div>
                        )}
                    </div>

                    {/* Grammar explanation (expand/collapse) */}
                    <div style={{
                        border: '1px solid #e8eaf6',
                        borderRadius: '6px',
                        overflow: 'hidden',
                        marginBottom: '16px',
                    }}>
                        <button
                            onClick={() => setGrammarOpen(o => !o)}
                            style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                width: '100%',
                                padding: '9px 12px',
                                background: '#f8f9ff',
                                border: 'none',
                                cursor: 'pointer',
                                fontSize: '12px',
                                fontWeight: 600,
                                color: '#1a237e',
                            }}
                        >
                            <span>Grammar explanation</span>
                            <span style={{ fontSize: '14px' }}>{grammarOpen ? '▲' : '▼'}</span>
                        </button>
                        {grammarOpen && (
                            <div style={{
                                padding: '10px 12px',
                                fontSize: '13px',
                                lineHeight: 1.6,
                                color: '#333',
                                background: '#fff',
                            }}>
                                {prep.grammar_explanation}
                            </div>
                        )}
                    </div>

                    {/* Examples section */}
                    <div style={{ marginBottom: '20px' }}>
                        <div style={{
                            fontSize: '11px', fontWeight: 700, color: '#888',
                            textTransform: 'uppercase', letterSpacing: '0.06em',
                            marginBottom: '8px',
                        }}>
                            Example
                        </div>

                        {example ? (
                            <div style={{
                                fontSize: '14px',
                                fontStyle: 'italic',
                                color: '#222',
                                lineHeight: 1.5,
                                padding: '8px 12px',
                                background: '#f8f9ff',
                                borderRadius: '6px',
                                borderLeft: '3px solid #c5cae9',
                                marginBottom: '12px',
                            }}>
                                {example}
                            </div>
                        ) : !hasExamples && (
                            <button
                                onClick={handleGenerate}
                                disabled={generating}
                                style={{
                                    padding: '7px 16px',
                                    borderRadius: '6px',
                                    border: '1px dashed #c5cae9',
                                    background: '#fff',
                                    color: '#1a237e',
                                    fontSize: '13px',
                                    fontWeight: 600,
                                    cursor: generating ? 'not-allowed' : 'pointer',
                                    opacity: generating ? 0.6 : 1,
                                    marginBottom: '12px',
                                }}
                            >
                                {generating ? 'Generating…' : 'Generate examples'}
                            </button>
                        )}

                        {templates.length > 0 && (
                            <>
                                <div style={{
                                    fontSize: '11px', fontWeight: 700, color: '#888',
                                    textTransform: 'uppercase', letterSpacing: '0.06em',
                                    marginBottom: '6px',
                                }}>
                                    Templates
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                    {templates.map((t, i) => (
                                        <div key={i} style={{
                                            fontSize: '13px',
                                            color: '#333',
                                            padding: '7px 11px',
                                            background: '#fff8e1',
                                            borderRadius: '6px',
                                            borderLeft: '3px solid #ffe082',
                                            lineHeight: 1.4,
                                        }}>
                                            {t}
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>

                    {/* CTA */}
                    <button
                        onClick={() => onStartPractice(item.item_id, item.item_type, language)}
                        style={{
                            padding: '10px 20px',
                            borderRadius: '7px',
                            border: 'none',
                            background: '#f57f17',
                            color: '#fff',
                            fontSize: '14px',
                            fontWeight: 700,
                            cursor: 'pointer',
                            alignSelf: 'flex-start',
                        }}
                    >
                        Start Guided Practice →
                    </button>
                </>
            )}
        </div>
    );
}
