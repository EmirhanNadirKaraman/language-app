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
  tokenIndex: number;
  text: string;
  // Block-order position in the page (for sorting)
  blockOrder: number;
}

interface Props {
  token: string;
  docId: string;
  language: string;
  selectedTokens: SelectedToken[];
  sentenceText: string;
  savedSelections: ReadingSelection[];
  onSaved: (sel: ReadingSelection) => void;
  onDeleted: (selectionId: string) => void;
  onClear: () => void;
  dk?: boolean;
}

// ── Surface text construction ─────────────────────────────────────────────────

function buildSurfaceText(tokens: SelectedToken[]): string {
  // Sort by block order, then token index
  const sorted = [...tokens].sort(
    (a, b) => a.blockOrder - b.blockOrder || a.tokenIndex - b.tokenIndex,
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
  onSaved,
  onDeleted,
  onClear,
  dk = false,
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
        .sort((a, b) => a.blockOrder - b.blockOrder || a.tokenIndex - b.tokenIndex)
        .map(t => ({
          block_id: t.blockId,
          token_index: t.tokenIndex,
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
      borderLeft: `1px solid ${dk ? '#333' : '#e8eaf6'}`,
      overflowY: 'auto',
      background: dk ? '#1a1a2e' : '#f8f9ff',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        padding: '10px 14px',
        borderBottom: `1px solid ${dk ? '#333' : '#e8eaf6'}`,
        background: dk ? '#2a2a4e' : '#e8eaf6',
        flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, fontSize: '13px', color: dk ? '#9fa8da' : '#1a237e', flex: 1 }}>
          Selection
        </span>
        <span style={{ fontSize: '11px', color: '#7986cb', marginRight: '10px' }}>
          {selectedTokens.length} token{selectedTokens.length !== 1 ? 's' : ''}
        </span>
        <button
          onClick={onClear}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#9fa8da', fontSize: '18px', lineHeight: 1, padding: 0,
          }}
          title="Clear selection"
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
            color: dk ? '#9fa8da' : '#1a237e',
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
            color: dk ? '#aaa' : '#666',
            fontStyle: 'italic',
            lineHeight: 1.6,
            background: dk ? '#1e1e2e' : '#fff',
            border: `1px solid ${dk ? '#333' : '#e8eaf6'}`,
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
              style={llmBtnStyle('#1565c0', translating, dk)}
            >
              {translating ? 'Translating…' : 'Translate sentence'}
            </button>
          ) : (
            <div style={llmResultStyle(dk ? '#0d253f' : '#e3f2fd', dk ? '#90caf9' : '#0d47a1')}>
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
              style={llmBtnStyle('#2e7d32', explaining, dk)}
            >
              {explaining ? 'Explaining…' : 'Explain in context'}
            </button>
          ) : (
            <div style={llmResultStyle(dk ? '#0d2a12' : '#e8f5e9', dk ? '#a5d6a7' : '#1b5e20')}>
              <div style={{ fontSize: '10px', color: '#66bb6a', marginBottom: '4px', fontStyle: 'normal', fontWeight: 600 }}>
                Explanation
              </div>
              {explanation}
            </div>
          )}
        </div>

        {/* Note */}
        <div>
          <label style={{ fontSize: '11px', color: dk ? '#aaa' : '#888', display: 'block', marginBottom: '4px' }}>
            Note (optional)
          </label>
          <textarea
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
            placeholder="Add a note…"
            style={{
              width: '100%',
              fontSize: '13px',
              padding: '6px 8px',
              border: `1px solid ${dk ? '#444' : '#c5cae9'}`,
              borderRadius: '4px',
              resize: 'vertical',
              boxSizing: 'border-box',
              fontFamily: 'inherit',
              background: dk ? '#1e1e2e' : '#fff',
              color: dk ? '#e0e0e0' : undefined,
            }}
          />
        </div>

        {/* Error */}
        {error && (
          <p style={{ margin: 0, fontSize: '12px', color: '#d32f2f' }}>{error}</p>
        )}

        {/* Actions */}
        {!alreadySaved ? (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleSave}
              disabled={saving || saved}
              style={{
                flex: 1,
                padding: '8px',
                borderRadius: '5px',
                border: 'none',
                background: saved ? '#e8f5e9' : '#1a237e',
                color: saved ? '#388e3c' : '#fff',
                fontSize: '13px',
                fontWeight: 600,
                cursor: saving || saved ? 'default' : 'pointer',
              }}
            >
              {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save'}
            </button>
            <button
              onClick={onClear}
              style={{
                padding: '8px 14px',
                borderRadius: '5px',
                border: `1px solid ${dk ? '#444' : '#c5cae9'}`,
                background: dk ? '#1e1e2e' : '#fff',
                color: dk ? '#aaa' : '#555',
                fontSize: '13px',
                cursor: 'pointer',
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
                padding: '8px 14px',
                borderRadius: '5px',
                border: '1px solid #ffcdd2',
                background: '#ffebee',
                color: '#d32f2f',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              Remove
            </button>
            <button
              onClick={onClear}
              style={{
                flex: 1,
                padding: '8px',
                borderRadius: '5px',
                border: `1px solid ${dk ? '#444' : '#c5cae9'}`,
                background: dk ? '#1e1e2e' : '#fff',
                color: dk ? '#aaa' : '#555',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              Clear selection
            </button>
          </div>
        )}

        {/* Saved selections on this page — mini review */}
        {savedSelections.length > 0 && (
          <div style={{ marginTop: '8px', borderTop: `1px solid ${dk ? '#333' : '#e8eaf6'}`, paddingTop: '10px' }}>
            <div style={{ fontSize: '11px', color: dk ? '#aaa' : '#888', marginBottom: '8px' }}>
              Saved on this page ({savedSelections.length})
            </div>
            {savedSelections.map(sel => (
              <SavedSelectionRow
                key={sel.selection_id}
                selection={sel}
                onDelete={() => handleDelete(sel.selection_id)}
                dk={dk}
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
  onDelete,
  dk = false,
}: {
  selection: ReadingSelection;
  onDelete: () => void;
  dk?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{
      background: dk ? '#1e1e2e' : '#fff',
      border: `1px solid ${dk ? '#333' : '#e8eaf6'}`,
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
        <span style={{ fontSize: '13px', fontWeight: 600, color: dk ? '#9fa8da' : '#1a237e', flex: 1 }}>
          {selection.surface_text}
        </span>
        <button
          onClick={e => { e.stopPropagation(); onDelete(); }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#ccc', fontSize: '14px', lineHeight: 1, padding: 0,
          }}
          title="Delete"
        >
          ×
        </button>
        <span style={{ fontSize: '11px', color: '#aaa' }}>{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div style={{ padding: '6px 10px 10px', borderTop: `1px solid ${dk ? '#333' : '#f0f0f0'}`, fontSize: '12px', color: dk ? '#aaa' : '#555' }}>
          {selection.note && (
            <div style={{ marginBottom: '6px', color: dk ? '#ccc' : '#333' }}>
              <em>{selection.note}</em>
            </div>
          )}
          <div style={{ color: '#888', fontStyle: 'italic' }}>
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

function llmBtnStyle(color: string, disabled: boolean, dk = false): React.CSSProperties {
  return {
    width: '100%',
    padding: '7px 12px',
    borderRadius: '5px',
    border: `1px solid ${color}40`,
    background: disabled ? (dk ? '#2a2a2a' : '#f5f5f5') : `${color}10`,
    color: disabled ? '#aaa' : color,
    fontSize: '13px',
    fontWeight: 600,
    cursor: disabled ? 'wait' : 'pointer',
    textAlign: 'left',
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
