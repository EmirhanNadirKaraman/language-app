import { useInsights } from '../hooks/useInsights';
import type { InsightCard, InsightItem } from '../types';

interface Props {
    token: string;
    language: string;
    onItemClick: (item: InsightItem) => void;
}

export function InsightsSection({ token, language, onItemClick }: Props) {
    const { cards, loading, error } = useInsights(token, language);

    const hasAnyItems = cards.some(c => c.items.length > 0);

    return (
        <div style={{ marginBottom: '16px' }}>
            <p style={{
                fontSize: '11px', fontWeight: 700, color: '#888',
                textTransform: 'uppercase', letterSpacing: '0.06em',
                margin: '0 0 10px',
            }}>
                Insights
            </p>

            {loading && (
                <p style={{ fontSize: '13px', color: '#aaa', padding: '4px 0' }}>
                    Loading insights…
                </p>
            )}

            {!loading && !error && !hasAnyItems && (
                <p style={{ fontSize: '13px', color: '#aaa', padding: '4px 0' }}>
                    Start practising to see personalised insights here.
                </p>
            )}

            {!loading && hasAnyItems && (
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    {cards.map(card => card.items.length > 0 && (
                        <InsightCardView
                            key={card.card_type}
                            card={card}
                            onItemClick={onItemClick}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// InsightCardView
// ---------------------------------------------------------------------------

function InsightCardView({
    card, onItemClick,
}: {
    card: InsightCard;
    onItemClick: (item: InsightItem) => void;
}) {
    const [primary, ...others] = card.items;

    const isMistake = card.card_type === 'recent_mistakes';
    const borderColor = isMistake ? '#fce4ec' : '#e3f2fd';
    const accentColor = isMistake ? '#c62828' : '#1565c0';

    return (
        <div style={{
            border: `1px solid ${borderColor}`,
            borderRadius: '8px',
            padding: '14px 16px',
            background: '#fff',
            minWidth: '200px',
            maxWidth: '280px',
            flexShrink: 0,
        }}>
            {/* Card header */}
            <div style={{ fontSize: '12px', fontWeight: 700, color: accentColor, marginBottom: '2px' }}>
                {card.title}
            </div>
            <div style={{ fontSize: '11px', color: '#888', marginBottom: '10px', lineHeight: 1.4 }}>
                {card.explanation}
            </div>

            {/* Primary item — large, prominently clickable */}
            <button
                onClick={() => onItemClick(primary)}
                style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    background: '#f8f9ff',
                    border: '1px solid #e8eaf6',
                    borderRadius: '6px',
                    padding: '9px 11px',
                    cursor: 'pointer',
                    marginBottom: '8px',
                }}
            >
                <div style={{ fontSize: '17px', fontWeight: 700, color: '#111', marginBottom: '1px' }}>
                    {primary.display_text}
                </div>
                {primary.secondary_text && (
                    <div style={{ fontSize: '11px', color: '#888' }}>{primary.secondary_text}</div>
                )}
                <SignalRow item={primary} />
            </button>

            {/* Secondary items — compact clickable chips */}
            {others.length > 0 && (
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {others.map(item => (
                        <button
                            key={`${item.item_type}-${item.item_id}`}
                            onClick={() => onItemClick(item)}
                            style={{
                                padding: '4px 10px',
                                borderRadius: '12px',
                                border: '1px solid #e0e0e0',
                                background: '#f5f5f5',
                                fontSize: '13px',
                                fontWeight: 500,
                                color: '#444',
                                cursor: 'pointer',
                            }}
                        >
                            {item.display_text}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// SignalRow — 2-3 small chips showing why this item is surfaced
// ---------------------------------------------------------------------------

function SignalRow({ item }: { item: InsightItem }) {
    const chips: string[] = [];

    if (item.signals.is_due >= 0.5) chips.push('Due');

    const lastFailed = item.extra.last_failed as string | undefined;
    if (lastFailed) {
        const daysSince = Math.round((Date.now() - new Date(lastFailed).getTime()) / 86_400_000);
        chips.push(daysSince <= 1 ? 'Mistaken today' : `Mistaken ${daysSince}d ago`);
    } else if (item.signals.mistake_recency >= 0.4) {
        chips.push('Recent mistake');
    }

    const eventCount = item.extra.event_count as number | undefined;
    if (eventCount && eventCount > 1) {
        chips.push(`Seen ${eventCount}\u00d7`);
    } else if (!eventCount && item.signals.freq_rank >= 0.3) {
        chips.push('Seen often');
    }

    if (chips.length === 0 && item.signals.is_learning >= 0.5) chips.push('Studying');
    if (chips.length === 0) return null;

    return (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '6px' }}>
            {chips.slice(0, 3).map(chip => (
                <span key={chip} style={{
                    fontSize: '10px',
                    padding: '1px 6px',
                    borderRadius: '8px',
                    background: '#e8eaf6',
                    color: '#3949ab',
                    fontWeight: 600,
                }}>
                    {chip}
                </span>
            ))}
        </div>
    );
}
