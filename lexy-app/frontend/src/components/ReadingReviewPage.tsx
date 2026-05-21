/**
 * ReadingReviewPage — review queue for saved reading selections (#5).
 *
 * Consumes GET /api/v1/reading/selections/due and POSTs each outcome to
 * /api/v1/reading/selections/{id}/review.
 *
 * Outcome semantics (mirrored backend-side):
 *   - "still_learning"  reset reading schedule; passive_review_incorrect on
 *                       the catalog-linked word/phrase (if matched).
 *   - "got_it"          advance reading schedule; passive_review_correct on
 *                       catalog match.
 *   - "mastered"        exit reading rotation; status_marked_known with
 *                       status_override="known" on catalog match. Per #5 policy:
 *                       this is manual known *confidence*, not active production —
 *                       active_level is NOT bumped, no active SRS card is created.
 */
import { useCallback, useEffect, useState } from 'react';
import { getDueSelections, recordReview } from '../api/reading';
import type { DueSelectionItem } from '../types';

interface Props {
  token: string | null;
  onClose: () => void;
}

type Outcome = 'still_learning' | 'got_it' | 'mastered';

export function ReadingReviewPage({ token, onClose }: Props) {
  const [items, setItems] = useState<DueSelectionItem[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<Outcome | null>(null);
  const [reviewed, setReviewed] = useState(0);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setIndex(0);
    setReviewed(0);
    try {
      const data = await getDueSelections(token, 30);
      setItems(data);
    } catch (e) {
      setError((e as Error).message || 'Could not load reading review queue.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  async function submit(outcome: Outcome) {
    if (!token) return;
    const current = items[index];
    if (!current) return;
    setSubmitting(outcome);
    setError(null);
    try {
      await recordReview(token, current.selection_id, outcome);
      setReviewed(r => r + 1);
      setIndex(i => i + 1);
    } catch (e) {
      setError((e as Error).message || 'Could not record review.');
    } finally {
      setSubmitting(null);
    }
  }

  const total = items.length;
  const done = !loading && (total === 0 || index >= total);
  const current = !done ? items[index] : null;
  const progress = total > 0 ? Math.round((index / total) * 100) : 0;

  return (
    <div
      data-testid="reading-review-page"
      style={{
        border: '1px solid var(--color-border-accent)',
        borderRadius: '8px',
        padding: 'clamp(12px, 4vw, 20px)',
        background: 'var(--color-surface-muted)',
        marginBottom: '16px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h2 style={{ margin: 0, fontSize: '16px', color: 'var(--color-text-strong)' }}>
          Reading Review{total > 0 && !done ? ` (${total - index} left)` : ''}
        </h2>
        <button
          data-testid="reading-review-close"
          onClick={onClose}
          style={{
            minWidth: '44px', minHeight: '44px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'none', border: 'none',
            fontSize: '20px', cursor: 'pointer', color: 'var(--color-text-muted)',
            padding: 0,
            touchAction: 'manipulation',
          }}
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* Reload */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <button
          onClick={load}
          disabled={loading}
          style={{
            padding: '6px 14px', minHeight: '44px',
            border: '1px solid var(--color-border-accent)',
            borderRadius: '5px', background: 'var(--color-surface)',
            color: 'var(--color-primary-on-soft)', fontSize: '14px', fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.5 : 1,
            touchAction: 'manipulation',
          }}
        >
          {loading ? 'Loading…' : 'Reload'}
        </button>
        <span style={{ fontSize: '12px', color: 'var(--color-text-subtle)' }}>
          Saved selections from your books, due for review.
        </span>
      </div>

      {error && (
        <p
          data-testid="reading-review-error"
          style={{ fontSize: '13px', color: 'var(--color-danger)', margin: '8px 0' }}
        >
          {error}
        </p>
      )}

      {/* Empty / done states */}
      {!loading && done && total === 0 && reviewed === 0 && (
        <div data-testid="reading-review-empty" style={{ textAlign: 'center', padding: '32px 0' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>✓</div>
          <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-success)', margin: '0 0 4px' }}>
            Nothing due right now
          </p>
          <p style={{ fontSize: '13px', color: 'var(--color-text-subtle)', margin: 0 }}>
            Open a book and save more selections to grow your reading review queue.
          </p>
        </div>
      )}

      {!loading && done && reviewed > 0 && (
        <div data-testid="reading-review-session-complete" style={{ textAlign: 'center', padding: '32px 0' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>✓</div>
          <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-text-strong)', margin: '0 0 4px' }}>
            Session complete!
          </p>
          <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', margin: '0 0 16px' }}>
            {reviewed} selection{reviewed !== 1 ? 's' : ''} reviewed
          </p>
          <button
            onClick={load}
            style={{
              padding: '8px 20px', minHeight: '44px', borderRadius: '6px',
              border: '1px solid var(--color-border-accent)', background: 'var(--color-surface)',
              color: 'var(--color-primary-on-soft)', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              touchAction: 'manipulation',
            }}
          >
            Check for more
          </button>
        </div>
      )}

      {/* Review card */}
      {current && (
        <>
          <div style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--color-text-subtle)', marginBottom: '4px' }}>
              <span>{index + 1} of {total}</span>
              <span>{reviewed} reviewed this session</span>
            </div>
            <div style={{ height: '4px', background: 'var(--color-border-accent)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: '2px',
                background: 'var(--color-primary)',
                width: `${progress}%`,
                transition: 'width 0.3s ease',
              }} />
            </div>
          </div>

          <div
            data-testid="reading-review-card"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '8px',
              padding: 'clamp(16px, 4vw, 24px)',
              marginBottom: '16px',
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
            }}
          >
            <div style={{ fontSize: '11px', color: 'var(--color-text-subtle)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              From {current.doc_title}
            </div>
            <div
              data-testid="reading-review-canonical"
              style={{
                fontSize: 'clamp(22px, 6vw, 28px)',
                fontWeight: 700,
                color: 'var(--color-text-strong)',
                marginBottom: '8px',
              }}
            >
              {current.canonical}
            </div>
            {current.surface_text && current.surface_text !== current.canonical && (
              <div style={{ fontSize: '14px', color: 'var(--color-text-muted)', marginBottom: '10px' }}>
                Selected: <em>{current.surface_text}</em>
              </div>
            )}
            {current.sentence_text && (
              <div
                data-testid="reading-review-sentence"
                style={{
                  fontSize: '14px', color: 'var(--color-text)',
                  background: 'var(--color-surface-muted)',
                  borderLeft: '3px solid var(--color-primary)',
                  padding: '8px 12px',
                  borderRadius: '4px',
                  marginBottom: current.note ? '10px' : 0,
                }}
              >
                {current.sentence_text}
              </div>
            )}
            {current.note && (
              <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                Note: {current.note}
              </div>
            )}
          </div>

          {/* Action row — wraps on narrow phones; all buttons ≥44px */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              data-testid="reading-review-still-learning"
              onClick={() => submit('still_learning')}
              disabled={submitting !== null}
              style={{
                flex: '1 1 140px', minHeight: '44px',
                padding: '8px 14px', borderRadius: '6px',
                border: '1px solid var(--color-danger)',
                background: 'var(--color-surface)',
                color: 'var(--color-danger)',
                fontSize: '14px', fontWeight: 600,
                cursor: submitting !== null ? 'not-allowed' : 'pointer',
                opacity: submitting !== null ? 0.5 : 1,
                touchAction: 'manipulation',
              }}
            >
              {submitting === 'still_learning' ? 'Saving…' : 'Still learning'}
            </button>
            <button
              data-testid="reading-review-got-it"
              onClick={() => submit('got_it')}
              disabled={submitting !== null}
              style={{
                flex: '1 1 140px', minHeight: '44px',
                padding: '8px 14px', borderRadius: '6px',
                border: '1px solid var(--color-success)',
                background: 'var(--color-surface)',
                color: 'var(--color-success)',
                fontSize: '14px', fontWeight: 600,
                cursor: submitting !== null ? 'not-allowed' : 'pointer',
                opacity: submitting !== null ? 0.5 : 1,
                touchAction: 'manipulation',
              }}
            >
              {submitting === 'got_it' ? 'Saving…' : 'Got it'}
            </button>
            <button
              data-testid="reading-review-mastered"
              onClick={() => submit('mastered')}
              disabled={submitting !== null}
              style={{
                flex: '1 1 140px', minHeight: '44px',
                padding: '8px 14px', borderRadius: '6px',
                border: '1px solid var(--color-primary)',
                background: 'var(--color-primary)',
                color: 'var(--color-primary-text)',
                fontSize: '14px', fontWeight: 600,
                cursor: submitting !== null ? 'not-allowed' : 'pointer',
                opacity: submitting !== null ? 0.5 : 1,
                touchAction: 'manipulation',
              }}
            >
              {submitting === 'mastered' ? 'Saving…' : 'Mastered'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
