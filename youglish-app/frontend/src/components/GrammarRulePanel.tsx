import { useState } from 'react';
import type { GrammarRuleRef } from '../types';
import { generateGrammarExplanation } from '../api/insights';
import { setItemStatus } from '../api/words';

interface Props {
    token: string;
    rule: GrammarRuleRef;
    language: string;
    onClose: () => void;
}

const RULE_TYPE_LABELS: Record<string, string> = {
    reflexive_verb:        'Reflexive',
    verb_preposition_case: 'Verb + Preposition',
    separable_verb:        'Separable Verb',
    tense_auxiliary:       'Tense / Auxiliary',
    word_order:            'Word Order',
    adjective_declension:  'Adjective Endings',
};

export function GrammarRulePanel({ token, rule, language, onClose }: Props) {
    const [longExplanation, setLongExplanation] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [adding, setAdding] = useState(false);
    const [added, setAdded] = useState(false);

    async function handleAddToStudy() {
        setAdding(true);
        try {
            await setItemStatus(token, 'grammar_rule', rule.rule_id, 'learning');
            setAdded(true);
        } catch {
            // silently fail — button remains available to retry
        } finally {
            setAdding(false);
        }
    }

    async function handleLearnMore() {
        setLoading(true);
        try {
            const result = await generateGrammarExplanation(token, rule.slug, language);
            setLongExplanation(result.long_explanation);
        } catch {
            // silently fail — button stays visible
        } finally {
            setLoading(false);
        }
    }

    const typeLabel = RULE_TYPE_LABELS[rule.rule_type] ?? rule.rule_type;

    return (
        <div style={{
            border: '1px solid #c8e6c9',
            borderRadius: '6px',
            overflow: 'hidden',
            marginTop: '6px',
        }}>
            {/* Header */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                background: '#f1f8e9',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#1b5e20' }}>
                        {rule.title}
                    </span>
                    <span style={{
                        fontSize: '10px',
                        fontWeight: 600,
                        color: '#388e3c',
                        background: '#c8e6c9',
                        padding: '1px 6px',
                        borderRadius: '8px',
                    }}>
                        {typeLabel}
                    </span>
                </div>
                <button
                    onClick={onClose}
                    style={{
                        background: 'none',
                        border: 'none',
                        color: '#666',
                        fontSize: '16px',
                        cursor: 'pointer',
                        lineHeight: 1,
                        padding: '0 2px',
                    }}
                >
                    ×
                </button>
            </div>

            {/* Body */}
            <div style={{ padding: '10px 12px', background: '#fff' }}>
                {/* Pattern hint */}
                {rule.pattern_hint && (
                    <div style={{
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        color: '#1565c0',
                        background: '#e3f2fd',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        marginBottom: '8px',
                        display: 'inline-block',
                    }}>
                        {rule.pattern_hint}
                    </div>
                )}

                {/* Short explanation — always shown */}
                <p style={{
                    fontSize: '13px',
                    lineHeight: 1.6,
                    color: '#333',
                    margin: '0 0 10px',
                }}>
                    {rule.short_explanation}
                </p>

                {/* Long explanation — shown after generation */}
                {longExplanation && (
                    <div style={{
                        fontSize: '13px',
                        lineHeight: 1.6,
                        color: '#333',
                        borderTop: '1px solid #e8f5e9',
                        paddingTop: '10px',
                        whiteSpace: 'pre-wrap',
                    }}>
                        {longExplanation}
                    </div>
                )}

                {/* Action row: learn more + add to study */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {!longExplanation && (
                        <button
                            onClick={handleLearnMore}
                            disabled={loading}
                            style={{
                                padding: '5px 12px',
                                borderRadius: '5px',
                                border: '1px dashed #a5d6a7',
                                background: '#fff',
                                color: '#2e7d32',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: loading ? 'not-allowed' : 'pointer',
                                opacity: loading ? 0.6 : 1,
                            }}
                        >
                            {loading ? 'Loading…' : 'Learn more →'}
                        </button>
                    )}

                    {added ? (
                        <span style={{ fontSize: '12px', fontWeight: 600, color: '#388e3c' }}>
                            Added to study ✓
                        </span>
                    ) : (
                        <button
                            onClick={handleAddToStudy}
                            disabled={adding}
                            style={{
                                padding: '5px 12px',
                                borderRadius: '5px',
                                border: '1px solid #a5d6a7',
                                background: adding ? '#f1f8e9' : '#e8f5e9',
                                color: '#1b5e20',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: adding ? 'not-allowed' : 'pointer',
                                opacity: adding ? 0.6 : 1,
                            }}
                        >
                            {adding ? 'Adding…' : 'Add to study'}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
