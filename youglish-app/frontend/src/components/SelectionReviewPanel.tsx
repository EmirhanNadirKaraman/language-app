import React, { useState } from 'react';
import type { ReadingSelection } from '../types';
import { recordReview, deleteSelection } from '../api/reading';

// ── Helpers ───────────────────────────────────────────────────────────────────

function isDue(sel: ReadingSelection): boolean {
  if (sel.status !== 'learning') return false;
  if (!sel.next_review_at) return true; // never reviewed → immediately due
  return new Date(sel.next_review_at) <= new Date();
}

/** Human-readable label for when this item is next due. */
function dueLabel(sel: ReadingSelection): string | null {
  if (sel.status === 'mastered') return null;
  if (!sel.next_review_at) return 'New';
  if (isDue(sel)) return 'Due';
  const msUntil = new Date(sel.next_review_at).getTime() - Date.now();
  const days = Math.ceil(msUntil / 86_400_000);
  return days <= 1 ? 'Tomorrow' : `In ${days}d`;
}

function sortSelections(sels: ReadingSelection[]): ReadingSelection[] {
  return [...sels].sort((a, b) => {
    const aDue = isDue(a);
    const bDue = isDue(b);
    // Due items first
    if (aDue && !bDue) return -1;
    if (!aDue && bDue) return 1;
    if (aDue && bDue) {
      // Among due: null (new) first, then by next_review_at ascending
      if (!a.next_review_at && !b.next_review_at) return 0;
      if (!a.next_review_at) return -1;
      if (!b.next_review_at) return 1;
      return new Date(a.next_review_at).getTime() - new Date(b.next_review_at).getTime();
    }
    // Both not due: learning before mastered, then by next review date
    if (a.status !== b.status) return a.status === 'learning' ? -1 : 1;
    if (a.next_review_at && b.next_review_at) {
      return new Date(a.next_review_at).getTime() - new Date(b.next_review_at).getTime();
    }
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface Props {
  token: string;
  selections: ReadingSelection[];
  loading?: boolean;
  onReviewed: (updated: ReadingSelection) => void;
  onDeleted: (selectionId: string) => void;
  onClose: () => void;
}

export function SelectionReviewPanel({
  token,
  selections,
  loading,
  onReviewed,
  onDeleted,
  onClose,
}: Props) {
  const dueCount = selections.filter(isDue).length;
  const sorted = sortSelections(selections);

  return (
    <div style={{
      flex: '0 0 340px',
      borderLeft: '1px solid #e8eaf6',
      overflowY: 'auto',
      background: '#f8f9ff',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 14px',
        borderBottom: '1px solid #e8eaf6',
        background: '#e8eaf6',
        flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, fontSize: '13px', color: '#1a237e', flex: 1 }}>
          Saved ({selections.length})
        </span>
        {dueCount > 0 && (
          <span style={{
            fontSize: '10px', fontWeight: 700,
            background: '#f57c00', color: '#fff',
            borderRadius: '10px', padding: '2px 8px', marginRight: '10px',
          }}>
            {dueCount} due
          </span>
        )}
        <button
          onClick={onClose}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#9fa8da', fontSize: '18px', lineHeight: 1, padding: 0,
          }}
          title="Close"
        >
          ×
        </button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && (
          <p style={{ padding: '24px 14px', color: '#aaa', fontSize: '13px', textAlign: 'center' }}>
            Loading…
          </p>
        )}
        {!loading && selections.length === 0 && (
          <p style={{ padding: '24px 14px', color: '#aaa', fontSize: '13px', textAlign: 'center' }}>
            No saved units yet. Click words in the text to select and save them.
          </p>
        )}
        {!loading && sorted.map(sel => (
          <SelectionCard
            key={sel.selection_id}
            token={token}
            sel={sel}
            onReviewed={onReviewed}
            onDeleted={onDeleted}
          />
        ))}
      </div>
    </div>
  );
}

// ── Individual review card ────────────────────────────────────────────────────

function SelectionCard({
  token,
  sel,
  onReviewed,
  onDeleted,
}: {
  token: string;
  sel: ReadingSelection;
  onReviewed: (updated: ReadingSelection) => void;
  onDeleted: (id: string) => void;
}) {
  const due = isDue(sel);
  const label = dueLabel(sel);
  // Auto-expand newly-due items; collapse mastered items
  const [expanded, setExpanded] = useState(due && sel.status !== 'mastered');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const context = sel.sentence_text.length > 200
    ? sel.sentence_text.slice(0, 200) + '…'
    : sel.sentence_text;

  async function handleReview(outcome: 'got_it' | 'still_learning' | 'mastered') {
    setLoading(true);
    setError(null);
    try {
      const updated = await recordReview(token, sel.selection_id, outcome);
      onReviewed(updated);
      if (outcome !== 'still_learning') setExpanded(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    setError(null);
    try {
      await deleteSelection(token, sel.selection_id);
      onDeleted(sel.selection_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div style={{
      borderBottom: '1px solid #e8eaf6',
      background: due && sel.status !== 'mastered' ? '#fff' : '#fafafa',
    }}>
      {/* Row header — always visible */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center',
          padding: '9px 12px', cursor: 'pointer', gap: '8px',
        }}
      >
        <span style={{
          flex: 1, fontSize: '14px', fontWeight: 600,
          color: sel.status === 'mastered' ? '#888' : '#1a237e',
        }}>
          {sel.surface_text}
        </span>

        {label && (
          <span style={{
            fontSize: '10px', fontWeight: 700,
            color: due ? '#f57c00' : '#999',
            background: due ? '#fff3e0' : '#f5f5f5',
            borderRadius: '8px', padding: '2px 7px',
            whiteSpace: 'nowrap',
          }}>
            {label}
          </span>
        )}

        {sel.status === 'mastered' && (
          <span style={{
            fontSize: '10px', fontWeight: 700,
            color: '#388e3c', background: '#e8f5e9',
            borderRadius: '8px', padding: '2px 7px',
          }}>
            Mastered
          </span>
        )}

        <span style={{ fontSize: '11px', color: '#aaa' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{ padding: '4px 12px 12px', borderTop: '1px solid #f0f0f0' }}>
          {/* Sentence context */}
          <div style={{
            fontSize: '12px', color: '#666', fontStyle: 'italic',
            lineHeight: 1.6, marginBottom: '8px',
          }}>
            {context}
          </div>

          {/* Note */}
          {sel.note && (
            <div style={{
              fontSize: '12px', color: '#333',
              background: '#fffde7', border: '1px solid #ffe082',
              borderRadius: '4px', padding: '6px 8px', marginBottom: '8px',
            }}>
              {sel.note}
            </div>
          )}

          {/* Error */}
          {error && (
            <p style={{ margin: '0 0 6px', fontSize: '12px', color: '#d32f2f' }}>{error}</p>
          )}

          {/* Review actions — hidden for mastered items */}
          {sel.status !== 'mastered' && (
            <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
              <button
                onClick={() => handleReview('got_it')}
                disabled={loading}
                style={reviewBtnStyle('#2e7d32', '#e8f5e9', loading)}
              >
                Got it ✓
              </button>
              <button
                onClick={() => handleReview('still_learning')}
                disabled={loading}
                style={reviewBtnStyle('#e65100', '#fff3e0', loading)}
              >
                Not quite
              </button>
              <button
                onClick={() => handleReview('mastered')}
                disabled={loading}
                style={reviewBtnStyle('#1565c0', '#e3f2fd', loading)}
                title="Mark as fully mastered — removes from review queue"
              >
                ★
              </button>
            </div>
          )}

          <button
            onClick={handleDelete}
            disabled={loading}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#d32f2f', fontSize: '11px', padding: 0,
            }}
          >
            Remove
          </button>
        </div>
      )}
    </div>
  );
}

// ── Style helper ──────────────────────────────────────────────────────────────

function reviewBtnStyle(color: string, bg: string, disabled: boolean): React.CSSProperties {
  return {
    flex: 1,
    padding: '6px 4px',
    borderRadius: '5px',
    border: `1px solid ${color}30`,
    background: disabled ? '#f5f5f5' : bg,
    color: disabled ? '#aaa' : color,
    fontSize: '12px',
    fontWeight: 600,
    cursor: disabled ? 'default' : 'pointer',
  };
}
