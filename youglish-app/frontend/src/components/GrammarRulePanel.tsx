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
            border: '1px solid var(--color-success-border)',
            borderRadius: '6px',
            overflow: 'hidden',
            marginTop: '6px',
        }}>
            {/* Header — semantic green for "grammar rule" identity, kept across themes. */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                background: 'var(--color-success-bg)',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-success)' }}>
                        {rule.title}
                    </span>
                    <span style={{
                        fontSize: '10px',
                        fontWeight: 600,
                        color: 'var(--color-success)',
                        background: 'var(--color-success-border)',
                        padding: '1px 6px',
                        borderRadius: '8px',
                    }}>
                        {typeLabel}
                    </span>
                </div>
                <button
                    onClick={onClose}
                    style={{
                        // Inline-panel close — 36×36 keeps the green header tight.
                        background: 'none',
                        border: 'none',
                        color: 'var(--color-text-muted)',
                        fontSize: '18px',
                        cursor: 'pointer',
                        lineHeight: 1,
                        padding: 0,
                        minWidth: '36px',
                        minHeight: '36px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        touchAction: 'manipulation',
                    }}
                    aria-label="Close rule"
                >
                    ×
                </button>
            </div>

            {/* Body */}
            <div style={{ padding: '10px 12px', background: 'var(--color-surface)' }}>
                {/* Pattern hint */}
                {rule.pattern_hint && (
                    <div style={{
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        color: 'var(--color-primary-on-soft)',
                        background: 'var(--color-primary-soft)',
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
                    color: 'var(--color-text)',
                    margin: '0 0 10px',
                }}>
                    {rule.short_explanation}
                </p>

                {/* Long explanation — shown after generation */}
                {longExplanation && (
                    <div style={{
                        fontSize: '13px',
                        lineHeight: 1.6,
                        color: 'var(--color-text)',
                        borderTop: '1px solid var(--color-success-border)',
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
                                padding: '8px 14px',
                                borderRadius: '5px',
                                border: '1px dashed var(--color-success-border)',
                                background: 'var(--color-surface)',
                                color: 'var(--color-success)',
                                fontSize: '13px',
                                fontWeight: 600,
                                cursor: loading ? 'not-allowed' : 'pointer',
                                opacity: loading ? 0.6 : 1,
                                minHeight: '36px',
                                touchAction: 'manipulation',
                            }}
                        >
                            {loading ? 'Loading…' : 'Learn more →'}
                        </button>
                    )}

                    {added ? (
                        <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-success)' }}>
                            Added to study ✓
                        </span>
                    ) : (
                        <button
                            onClick={handleAddToStudy}
                            disabled={adding}
                            style={{
                                padding: '8px 14px',
                                borderRadius: '5px',
                                border: '1px solid var(--color-success-border)',
                                background: 'var(--color-success-bg)',
                                color: 'var(--color-success)',
                                fontSize: '13px',
                                fontWeight: 600,
                                cursor: adding ? 'not-allowed' : 'pointer',
                                opacity: adding ? 0.6 : 1,
                                minHeight: '36px',
                                touchAction: 'manipulation',
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
