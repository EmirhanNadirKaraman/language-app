import React, { useEffect, useState } from 'react';
import type { ReadingSelection } from '../types';
import {
  saveSelection,
  translateSentence,
  explainInContext,
  deleteSelection,
} from '../api/reading';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SelectedToken {
  blockId: number;
  tokenId: string;
  tokenArrayIndex: number;  // position in block.tokens[] for within-block sorting
  text: string;
  blockOrder: number;  // Block-order position in the page (for sorting)
}

interface Props {
  token: string;
  docId: string;
  language: string;
  selectedTokens: SelectedToken[];
  sentenceText: string;
  savedSelections: ReadingSelection[];
  blockTokenMap: Map<number, Set<string>>;  // block_id → Set of valid token_ids
  onSaved: (sel: ReadingSelection) => void;
  onDeleted: (selectionId: string) => void;
  onClear: () => void;
}

// ── Surface text construction ─────────────────────────────────────────────────

function buildSurfaceText(tokens: SelectedToken[]): string {
  // Sort by block order, then token array index (within-block position)
  const sorted = [...tokens].sort(
    (a, b) => a.blockOrder - b.blockOrder || a.tokenArrayIndex - b.tokenArrayIndex,
  );
  return sorted.map(t => t.text).join(' ');
}

// ── Main component ────────────────────────────────────────────────────────────

export function SelectionPanel({
  token,
  docId,
  language,
  selectedTokens,
  sentenceText,
  savedSelections,
  blockTokenMap,
  onSaved,
  onDeleted,
  onClear,
}: Props) {
  const [translation, setTranslation] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [note, setNote]               = useState('');
  const [translating, setTranslating] = useState(false);
  const [explaining, setExplaining]   = useState(false);
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [error, setError]             = useState<string | null>(null);

  const surfaceText = buildSurfaceText(selectedTokens);

  // Check if this selection was already saved (by canonical match)
  const alreadySaved = savedSelections.find(
    s => s.canonical === surfaceText.toLowerCase(),
  ) ?? null;

  // Reset panel state when selection changes
  useEffect(() => {
    setTranslation(null);
    setExplanation(null);
    setNote('');
    setSaved(false);
    setError(null);
  }, [surfaceText]);

  async function handleTranslate() {
    if (!sentenceText) return;
    setTranslating(true);
    setError(null);
    try {
      const t = await translateSentence(token, sentenceText, language);
      setTranslation(t);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setTranslating(false);
    }
  }

  async function handleExplain() {
    if (!sentenceText) return;
    setExplaining(true);
    setError(null);
    try {
      const e = await explainInContext(token, surfaceText, sentenceText, language);
      setExplanation(e);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExplaining(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const anchors = [...selectedTokens]
        .sort((a, b) => a.blockOrder - b.blockOrder || a.tokenArrayIndex - b.tokenArrayIndex)
        .map(t => ({
          block_id: t.blockId,
          token_id: t.tokenId,
          surface: t.text,
        }));

      const sel = await saveSelection(token, docId, {
        canonical: surfaceText.toLowerCase(),
        surface_text: surfaceText,
        sentence_text: sentenceText,
        anchors,
        note: note.trim() || undefined,
      });
      setSaved(true);
      onSaved(sel);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(selectionId: string) {
    try {
      await deleteSelection(token, selectionId);
      onDeleted(selectionId);
      setSaved(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const contextPreview = sentenceText.length > 240
    ? sentenceText.slice(0, 240) + '…'
    : sentenceText;

  return (
    <div style={{
      flex: '0 0 340px',
      borderLeft: '1px solid var(--color-border)',
      overflowY: 'auto',
      background: 'var(--color-surface-sunken)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 14px',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-primary-soft)',
        flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--color-primary-on-soft)', flex: 1 }}>
          Selection
        </span>
        <span style={{ fontSize: '11px', color: '#7986cb', marginRight: '10px' }}>
          {selectedTokens.length} token{selectedTokens.length !== 1 ? 's' : ''}
        </span>
        <button
          onClick={onClear}
          style={{
            // 340px sidebar context — 36×36 keeps the header tidy while still tappable.
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--color-primary-on-soft)', fontSize: '20px', lineHeight: 1,
            minWidth: '36px', minHeight: '36px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 0,
            touchAction: 'manipulation',
          }}
          title="Clear selection"
          aria-label="Clear selection"
        >
          ×
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>

        {/* Selected text */}
        <div>
          <div style={{
            fontSize: '22px',
            fontWeight: 700,
            color: 'var(--color-primary-on-soft)',
            lineHeight: 1.3,
            wordBreak: 'break-word',
          }}>
            {surfaceText}
          </div>
          {alreadySaved && (
            <span style={{
              display: 'inline-block',
              marginTop: '4px',
              fontSize: '11px',
              color: '#f57c00',
              background: '#fff3e0',
              borderRadius: '8px',
              padding: '2px 8px',
            }}>
              Already saved
            </span>
          )}
        </div>

        {/* Sentence context */}
        {sentenceText && (
          <div style={{
            fontSize: '12px',
            color: 'var(--color-text-muted)',
            fontStyle: 'italic',
            lineHeight: 1.6,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: '5px',
            padding: '8px 10px',
          }}>
            {contextPreview}
          </div>
        )}

        {/* Translate */}
        <div>
          {!translation ? (
            <button
              onClick={handleTranslate}
              disabled={translating || !sentenceText}
              style={llmBtnStyle('#1565c0', translating)}
            >
              {translating ? 'Translating…' : 'Translate sentence'}
            </button>
          ) : (
            <div style={llmResultStyle('var(--color-primary-soft)', 'var(--color-primary-on-soft)')}>
              <div style={{ fontSize: '10px', color: '#42a5f5', marginBottom: '4px', fontStyle: 'normal', fontWeight: 600 }}>
                Translation
              </div>
              {translation}
            </div>
          )}
        </div>

        {/* Explain */}
        <div>
          {!explanation ? (
            <button
              onClick={handleExplain}
              disabled={explaining || !sentenceText}
              style={llmBtnStyle('#2e7d32', explaining)}
            >
              {explaining ? 'Explaining…' : 'Explain in context'}
            </button>
          ) : (
            <div style={llmResultStyle('var(--color-success-bg)', 'var(--color-success)')}>
              <div style={{ fontSize: '10px', color: '#66bb6a', marginBottom: '4px', fontStyle: 'normal', fontWeight: 600 }}>
                Explanation
              </div>
              {explanation}
            </div>
          )}
        </div>

        {/* Note */}
        <div>
          <label style={{ fontSize: '11px', color: 'var(--color-text-muted)', display: 'block', marginBottom: '4px' }}>
            Note (optional)
          </label>
          <textarea
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
            placeholder="Add a note…"
            // fontSize: 16px blocks iOS Safari focus-zoom on textareas.
            style={{
              width: '100%',
              fontSize: '16px',
              padding: '8px 10px',
              border: '1px solid var(--color-border-accent)',
              borderRadius: '4px',
              resize: 'vertical',
              boxSizing: 'border-box',
              fontFamily: 'inherit',
              background: 'var(--color-input-bg)',
              color: 'var(--color-text)',
            }}
            data-testid="selection-note"
          />
        </div>

        {/* Error */}
        {error && (
          <p style={{ margin: 0, fontSize: '12px', color: 'var(--color-danger)' }}>{error}</p>
        )}

        {/* Actions */}
        {!alreadySaved ? (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleSave}
              disabled={saving || saved}
              style={{
                flex: 1,
                padding: '10px',
                borderRadius: '5px',
                border: 'none',
                background: saved ? 'var(--color-success-bg)' : 'var(--color-primary)',
                color: saved ? 'var(--color-success)' : 'var(--color-primary-text)',
                fontSize: '13px',
                fontWeight: 600,
                cursor: saving || saved ? 'default' : 'pointer',
                minHeight: '40px',
                touchAction: 'manipulation',
              }}
              data-testid="selection-save"
            >
              {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save'}
            </button>
            <button
              onClick={onClear}
              style={{
                padding: '10px 14px',
                borderRadius: '5px',
                border: '1px solid var(--color-border-accent)',
                background: 'var(--color-surface)',
                color: 'var(--color-text-muted)',
                fontSize: '13px',
                cursor: 'pointer',
                minHeight: '40px',
                touchAction: 'manipulation',
              }}
            >
              Clear
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => handleDelete(alreadySaved.selection_id)}
              style={{
                padding: '10px 14px',
                borderRadius: '5px',
                border: '1px solid var(--color-danger-border)',
                background: 'var(--color-danger-bg)',
                color: 'var(--color-danger)',
                fontSize: '13px',
                cursor: 'pointer',
                minHeight: '40px',
                touchAction: 'manipulation',
              }}
            >
              Remove
            </button>
            <button
              onClick={onClear}
              style={{
                flex: 1,
                padding: '10px',
                borderRadius: '5px',
                border: '1px solid var(--color-border-accent)',
                background: 'var(--color-surface)',
                color: 'var(--color-text-muted)',
                fontSize: '13px',
                cursor: 'pointer',
                minHeight: '40px',
                touchAction: 'manipulation',
              }}
            >
              Clear selection
            </button>
          </div>
        )}

        {/* Saved selections on this page — mini review */}
        {savedSelections.length > 0 && (
          <div style={{ marginTop: '8px', borderTop: '1px solid var(--color-border)', paddingTop: '10px' }}>
            <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginBottom: '8px' }}>
              Saved on this page ({savedSelections.length})
            </div>
            {savedSelections.map(sel => (
              <SavedSelectionRow
                key={sel.selection_id}
                selection={sel}
                blockTokenMap={blockTokenMap}
                onDelete={() => handleDelete(sel.selection_id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Saved selection row ───────────────────────────────────────────────────────

function SavedSelectionRow({
  selection,
  blockTokenMap,
  onDelete,
}: {
  selection: ReadingSelection;
  blockTokenMap: Map<number, Set<string>>;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // Detect if this selection has stale anchors
  const isStale = selection.anchors.some(a => {
    const validIds = blockTokenMap.get(a.block_id);
    return validIds !== undefined && !validIds.has(a.token_id);
  });

  return (
    <div style={{
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: '5px',
      marginBottom: '6px',
      overflow: 'hidden',
    }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '6px 10px',
          cursor: 'pointer',
          gap: '8px',
        }}
        onClick={() => setExpanded(e => !e)}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-primary-on-soft)' }}>
              {selection.surface_text}
            </span>
            {isStale && (
              <span style={{
                fontSize: '9px',
                color: 'var(--color-danger)',
                background: 'var(--color-danger-bg)',
                borderRadius: '4px',
                padding: '2px 6px',
              }}>
                Outdated
              </span>
            )}
          </div>
        </div>
        <button
          onClick={e => { e.stopPropagation(); onDelete(); }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--color-text-subtle)', fontSize: '14px', lineHeight: 1, padding: 0,
          }}
          title="Delete"
        >
          ×
        </button>
        <span style={{ fontSize: '11px', color: 'var(--color-text-subtle)' }}>{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div style={{ padding: '6px 10px 10px', borderTop: '1px solid var(--color-border-subtle)', fontSize: '12px', color: 'var(--color-text-muted)' }}>
          {selection.note && (
            <div style={{ marginBottom: '6px', color: 'var(--color-text)' }}>
              <em>{selection.note}</em>
            </div>
          )}
          <div style={{ color: 'var(--color-text-subtle)', fontStyle: 'italic' }}>
            {selection.sentence_text.length > 120
              ? selection.sentence_text.slice(0, 120) + '…'
              : selection.sentence_text}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Style helpers ─────────────────────────────────────────────────────────────

function llmBtnStyle(color: string, disabled: boolean): React.CSSProperties {
  return {
    width: '100%',
    padding: '10px 12px',
    borderRadius: '5px',
    border: `1px solid ${color}40`,
    background: disabled ? 'var(--color-surface-muted)' : `${color}10`,
    color: disabled ? 'var(--color-text-subtle)' : color,
    fontSize: '13px',
    fontWeight: 600,
    cursor: disabled ? 'wait' : 'pointer',
    textAlign: 'left',
    minHeight: '40px',
    touchAction: 'manipulation',
  };
}

function llmResultStyle(bg: string, color: string): React.CSSProperties {
  return {
    background: bg,
    borderRadius: '5px',
    padding: '8px 10px',
    fontSize: '13px',
    color,
    lineHeight: 1.6,
    fontStyle: 'italic',
  };
}
