import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getPage, getPageImageUrl, patchBlock, repairBlock, batchRepairPage,
} from '../api/books';
import { getPageWordStatuses, getPageSelections, listAllSelections } from '../api/reading';
import type { BookDocument, BookPageDetail, BookBlock, ReadingSelection } from '../types';
import { SelectionPanel } from './SelectionPanel';
import type { SelectedToken } from './SelectionPanel';
import { SelectionReviewPanel } from './SelectionReviewPanel';
import { WORD_COLORS } from '../config/wordColors';

interface Props {
  token: string;
  doc: BookDocument;
  onClose: () => void;
}

// ── Tokenizer ─────────────────────────────────────────────────────────────────

interface BlockToken {
  index: number;
  text: string;
  isWord: boolean;
}

/** Split block text into word and non-word tokens, preserving all characters. */
function tokenizeBlock(text: string): BlockToken[] {
  // Split on runs of Unicode letters (including German umlauts, accents)
  const parts = text.split(/(\p{L}[\p{L}\p{M}'-]*)/u);
  let index = 0;
  return parts
    .filter(p => p.length > 0)
    .map(p => ({
      index: index++,
      text: p,
      isWord: /^\p{L}/u.test(p),
    }));
}

// ── Interactive block component ───────────────────────────────────────────────

interface InteractiveBlockProps {
  block: BookBlock;
  selectedKeys: Set<string>;
  savedAnchorKeys: Set<string>;
  wordStatuses: Record<string, string>;
  onTokenClick: (blockId: number, tokenIndex: number, text: string) => void;
}

function InteractiveBlock({
  block,
  selectedKeys,
  savedAnchorKeys,
  wordStatuses,
  onTokenClick,
}: InteractiveBlockProps) {
  const tokens = useMemo(() => tokenizeBlock(block.display_text), [block.display_text]);

  return (
    <div style={{
      marginBottom: '1em',
      opacity: block.is_header_footer ? 0.4 : 1,
      fontSize: block.is_header_footer ? '12px' : '16px',
      lineHeight: 1.8,
      color: '#222',
      wordBreak: 'break-word',
    }}>
      {tokens.map(tok => {
        if (!tok.isWord) {
          return <span key={tok.index}>{tok.text}</span>;
        }

        const key = `${block.block_id}:${tok.index}`;
        const isSelected = selectedKeys.has(key);
        const isSaved = savedAnchorKeys.has(key);
        const status = wordStatuses[tok.text.toLowerCase()];

        let tokenStyle: React.CSSProperties = {
          cursor: 'pointer',
          borderRadius: '3px',
          padding: '0 1px',
        };

        if (isSelected) {
          // Blue highlight for active selection (highest priority)
          tokenStyle = {
            ...tokenStyle,
            background: '#c5cae9',
            color: '#1a237e',
            outline: '1px solid #7986cb',
          };
        } else if (isSaved) {
          // Amber highlight for already-saved tokens
          tokenStyle = {
            ...tokenStyle,
            background: '#fff8e1',
            color: '#e65100',
          };
        } else if (status === 'known') {
          tokenStyle = { ...tokenStyle, ...WORD_COLORS.known };
        } else if (status === 'learning') {
          tokenStyle = { ...tokenStyle, ...WORD_COLORS.learning };
        } else if (status === 'unknown') {
          tokenStyle = { ...tokenStyle, ...WORD_COLORS.unknown };
        }

        return (
          <span
            key={tok.index}
            style={tokenStyle}
            onClick={() => onTokenClick(block.block_id, tok.index, tok.text)}
            title={isSaved ? 'Saved' : undefined}
          >
            {tok.text}
          </span>
        );
      })}
    </div>
  );
}

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfBadge({ conf }: { conf: number | null }) {
  if (conf === null) return null;
  const color = conf >= 0.8 ? '#388e3c' : conf >= 0.65 ? '#f57c00' : '#d32f2f';
  return (
    <span style={{
      fontSize: '10px', color, border: `1px solid ${color}`,
      borderRadius: '3px', padding: '1px 4px', marginLeft: '6px',
    }}>
      {Math.round(conf * 100)}%
    </span>
  );
}

// ── Diff view ─────────────────────────────────────────────────────────────────

function DiffView({ original, corrected }: { original: string; corrected: string }) {
  if (original === corrected) {
    return <span style={{ color: '#388e3c', fontSize: '13px' }}>No changes needed.</span>;
  }
  return (
    <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
      <div>
        <span style={{ color: '#888', fontSize: '11px' }}>Original OCR:</span>
        <div style={{ background: '#ffebee', padding: '6px 8px', borderRadius: '4px', marginTop: '2px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {original}
        </div>
      </div>
      <div style={{ marginTop: '6px' }}>
        <span style={{ color: '#888', fontSize: '11px' }}>Suggested correction:</span>
        <div style={{ background: '#e8f5e9', padding: '6px 8px', borderRadius: '4px', marginTop: '2px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {corrected}
        </div>
      </div>
    </div>
  );
}

// ── Block review row ──────────────────────────────────────────────────────────

interface BlockRowProps {
  block: BookBlock;
  token: string;
  docId: string;
  onUpdated: (b: BookBlock) => void;
  onPageReload: () => void;
}

function BlockRow({ block, token, docId, onUpdated, onPageReload }: BlockRowProps) {
  const [editing, setEditing]     = useState(false);
  const [editText, setEditText]   = useState(block.user_text_override ?? block.clean_text ?? '');
  const [repairing, setRepairing] = useState(false);
  const [repairErr, setRepairErr] = useState<string | null>(null);

  const isIgnored     = block.block_type === 'ignored';
  const hasSuggestion = block.correction_status === 'suggested' && block.corrected_text;
  const isLowConf     = block.ocr_confidence !== null && block.ocr_confidence < 0.65;

  async function toggleIgnore() {
    const updated = await patchBlock(token, docId, block.block_id, {
      block_type: isIgnored ? 'text' : 'ignored',
    });
    onUpdated(updated);
  }

  async function saveEdit() {
    const updated = await patchBlock(token, docId, block.block_id, { user_text_override: editText });
    onUpdated(updated);
    setEditing(false);
  }

  async function clearOverride() {
    const updated = await patchBlock(token, docId, block.block_id, { user_text_override: '' });
    onUpdated(updated);
    setEditing(false);
  }

  async function handleRepair() {
    setRepairing(true);
    setRepairErr(null);
    try {
      await repairBlock(token, docId, block.block_id);
      onPageReload();
    } catch (e) {
      setRepairErr((e as Error).message);
    } finally {
      setRepairing(false);
    }
  }

  async function handleApprove() {
    const updated = await patchBlock(token, docId, block.block_id, { correction_status: 'approved' });
    onUpdated(updated);
  }

  async function handleReject() {
    const updated = await patchBlock(token, docId, block.block_id, { correction_status: 'rejected' });
    onUpdated(updated);
  }

  return (
    <div style={{
      padding: '8px 10px',
      borderBottom: '1px solid #f0f0f0',
      opacity: isIgnored ? 0.4 : 1,
      background: block.is_header_footer ? '#fafafa' : '#fff',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '10px', color: '#aaa' }}>#{block.block_index}</span>
        {block.is_header_footer && (
          <span style={{ fontSize: '10px', color: '#888', background: '#f5f5f5', borderRadius: '3px', padding: '1px 5px' }}>
            header/footer
          </span>
        )}
        <ConfBadge conf={block.ocr_confidence} />
        {block.user_text_override !== null && (
          <span style={{ fontSize: '10px', color: '#1565c0', background: '#e3f2fd', borderRadius: '3px', padding: '1px 5px' }}>
            manual edit
          </span>
        )}
        {block.correction_status === 'approved' && (
          <span style={{ fontSize: '10px', color: '#388e3c', background: '#e8f5e9', borderRadius: '3px', padding: '1px 5px' }}>
            LLM approved
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px' }}>
          <button
            onClick={toggleIgnore}
            style={{ fontSize: '11px', padding: '2px 7px', border: '1px solid #ddd', borderRadius: '3px', cursor: 'pointer', background: isIgnored ? '#fff3e0' : '#fff' }}
          >
            {isIgnored ? 'Restore' : 'Ignore'}
          </button>
          <button
            onClick={() => { setEditing(e => !e); setEditText(block.user_text_override ?? block.clean_text ?? ''); }}
            style={{ fontSize: '11px', padding: '2px 7px', border: '1px solid #ddd', borderRadius: '3px', cursor: 'pointer', background: editing ? '#e8eaf6' : '#fff' }}
          >
            Edit
          </button>
          {isLowConf && block.correction_status === 'none' && (
            <button
              onClick={handleRepair}
              disabled={repairing}
              style={{ fontSize: '11px', padding: '2px 7px', border: '1px solid #ffe082', borderRadius: '3px', cursor: repairing ? 'wait' : 'pointer', background: '#fffde7' }}
            >
              {repairing ? 'Repairing…' : 'AI Fix'}
            </button>
          )}
        </div>
      </div>

      {!editing && (
        <div style={{ fontSize: '13px', lineHeight: 1.5, color: '#333', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {block.display_text || <em style={{ color: '#aaa' }}>(empty)</em>}
        </div>
      )}

      {editing && (
        <div style={{ marginTop: '4px' }}>
          <textarea
            value={editText}
            onChange={e => setEditText(e.target.value)}
            rows={4}
            style={{ width: '100%', fontSize: '13px', padding: '6px', border: '1px solid #90caf9', borderRadius: '4px', resize: 'vertical', boxSizing: 'border-box' }}
          />
          <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
            <button onClick={saveEdit} style={btnStyle('#1a237e', '#fff')}>Save</button>
            <button onClick={() => setEditing(false)} style={btnStyle('#eee', '#333')}>Cancel</button>
            {block.user_text_override !== null && (
              <button onClick={clearOverride} style={btnStyle('#ffebee', '#d32f2f')}>Clear override</button>
            )}
          </div>
        </div>
      )}

      {hasSuggestion && (
        <div style={{ marginTop: '8px', padding: '8px', background: '#fffde7', borderRadius: '5px', border: '1px solid #ffe082' }}>
          <DiffView original={block.ocr_text ?? ''} corrected={block.corrected_text!} />
          <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
            <button onClick={handleApprove} style={btnStyle('#e8f5e9', '#388e3c')}>Approve</button>
            <button onClick={handleReject}  style={btnStyle('#ffebee', '#d32f2f')}>Reject</button>
          </div>
        </div>
      )}

      {repairErr && (
        <p style={{ color: '#d32f2f', fontSize: '12px', margin: '4px 0 0' }}>{repairErr}</p>
      )}
    </div>
  );
}

function btnStyle(bg: string, color: string) {
  return {
    padding: '4px 10px', background: bg, color, border: `1px solid ${color}20`,
    borderRadius: '4px', fontSize: '12px', cursor: 'pointer',
  } as const;
}

// ── Main reader ───────────────────────────────────────────────────────────────

export function BookReaderPage({ token, doc, onClose }: Props) {
  const [pageNum, setPageNum]       = useState(1);
  const [inputPage, setInputPage]   = useState('1');
  const [pageData, setPageData]     = useState<BookPageDetail | null>(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [showImage, setShowImage]         = useState(false);
  const [showReview, setShowReview]       = useState(false);
  const [showSaved, setShowSaved]         = useState(false);
  const [allDocSelections, setAllDocSelections] = useState<ReadingSelection[]>([]);
  const [savedLoading, setSavedLoading]   = useState(false);
  const [batchLoading, setBatchLoading]   = useState(false);
  const [batchMsg, setBatchMsg]     = useState<string | null>(null);

  // ── Interactive reading state ──────────────────────────────────────────────
  const [selectedKeys, setSelectedKeys]       = useState<Set<string>>(new Set());
  const [wordStatuses, setWordStatuses]       = useState<Record<string, string>>({});
  const [savedSelections, setSavedSelections] = useState<ReadingSelection[]>([]);

  const totalPages = doc.total_pages ?? 1;

  // Load page + word statuses + saved selections
  const loadPage = useCallback(async (n: number) => {
    setLoading(true);
    setError(null);
    setPageData(null);
    setSelectedKeys(new Set());
    setWordStatuses({});
    setSavedSelections([]);
    try {
      const data = await getPage(token, doc.doc_id, n);
      setPageData(data);

      // Load in parallel — failures are non-fatal
      const [statuses, sels] = await Promise.all([
        getPageWordStatuses(token, doc.doc_id, n, doc.language).catch(() => ({})),
        getPageSelections(token, doc.doc_id, n).catch(() => []),
      ]);
      setWordStatuses(statuses);
      setSavedSelections(sels);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token, doc.doc_id, doc.language]);

  useEffect(() => {
    loadPage(pageNum);
    setInputPage(String(pageNum));
    setBatchMsg(null);
  }, [pageNum, loadPage]);

  function navigate(delta: number) {
    const next = Math.max(1, Math.min(totalPages, pageNum + delta));
    setPageNum(next);
  }

  function handlePageInput(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      const n = parseInt(inputPage, 10);
      if (!isNaN(n) && n >= 1 && n <= totalPages) setPageNum(n);
      else setInputPage(String(pageNum));
    }
  }

  function updateBlock(updated: BookBlock) {
    if (!pageData) return;
    setPageData(prev => prev ? {
      ...prev,
      blocks: prev.blocks.map(b => b.block_id === updated.block_id ? updated : b),
    } : prev);
  }

  async function handleBatchRepair() {
    setBatchLoading(true);
    setBatchMsg(null);
    try {
      const result = await batchRepairPage(token, doc.doc_id, pageNum);
      setBatchMsg(`Repaired ${result.repaired} block(s) of ${result.total_candidates} candidates.`);
      await loadPage(pageNum);
    } catch (e) {
      setBatchMsg(`Error: ${(e as Error).message}`);
    } finally {
      setBatchLoading(false);
    }
  }

  // ── Selection logic ────────────────────────────────────────────────────────

  function handleTokenClick(blockId: number, tokenIndex: number, _text: string) {
    const key = `${blockId}:${tokenIndex}`;
    setSelectedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function clearSelection() {
    setSelectedKeys(new Set());
  }

  // Lazy-load all doc selections when the Saved panel is opened for the first time
  async function openSavedPanel() {
    const willShow = !showSaved;
    setShowSaved(willShow);
    setShowReview(false);
    if (willShow) {
      clearSelection();
      setSavedLoading(true);
      try {
        const sels = await listAllSelections(token, doc.doc_id);
        setAllDocSelections(sels);
      } catch {
        // non-fatal — panel still opens with empty state
      } finally {
        setSavedLoading(false);
      }
    }
  }

  // Build SelectedToken list from the current selection keys
  const selectedTokens: SelectedToken[] = useMemo(() => {
    if (!pageData || selectedKeys.size === 0) return [];
    const tokens: SelectedToken[] = [];
    pageData.blocks.forEach((block, blockOrder) => {
      const toks = tokenizeBlock(block.display_text);
      toks.forEach(tok => {
        const key = `${block.block_id}:${tok.index}`;
        if (selectedKeys.has(key) && tok.isWord) {
          tokens.push({
            blockId: block.block_id,
            tokenIndex: tok.index,
            text: tok.text,
            blockOrder,
          });
        }
      });
    });
    return tokens;
  }, [selectedKeys, pageData]);

  // Sentence text = display_text of the block containing the first selected token
  const sentenceText = useMemo(() => {
    if (selectedTokens.length === 0 || !pageData) return '';
    const first = selectedTokens[0];
    const block = pageData.blocks.find(b => b.block_id === first.blockId);
    return block?.display_text ?? '';
  }, [selectedTokens, pageData]);

  // Set of "blockId:tokenIndex" keys for already-saved selections (for amber highlighting)
  const savedAnchorKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const sel of savedSelections) {
      for (const anchor of sel.anchors) {
        keys.add(`${anchor.block_id}:${anchor.token_index}`);
      }
    }
    return keys;
  }, [savedSelections]);

  const hasSelection    = selectedKeys.size > 0 && selectedTokens.length > 0;
  const visibleBlocks   = pageData?.blocks.filter(b => b.block_type !== 'ignored') ?? [];
  const hasLowConf      = pageData?.blocks.some(
    b => b.ocr_confidence !== null && b.ocr_confidence < 0.65 && b.correction_status === 'none',
  ) ?? false;

  // Right panel priority: active selection > saved review > OCR block review
  const showRightPanel = hasSelection || showSaved || showReview;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: '#fff', zIndex: 900,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        padding: '10px 16px', borderBottom: '1px solid #eee',
        background: '#f8f9ff', flexShrink: 0, flexWrap: 'wrap',
      }}>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', fontSize: '16px', cursor: 'pointer', color: '#1a237e', fontWeight: 700 }}
        >
          ← Back
        </button>
        <span style={{ fontWeight: 700, fontSize: '15px', color: '#1a237e', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {doc.title}
        </span>

        {/* Mode hint */}
        {!hasSelection && (
          <span style={{ fontSize: '11px', color: '#9fa8da' }}>
            Click words to select
          </span>
        )}

        <div style={{ display: 'flex', gap: '6px' }}>
          {pageData?.has_image && (
            <button
              onClick={() => setShowImage(s => !s)}
              style={topBtnStyle(showImage)}
            >
              Scan
            </button>
          )}
          <button
            onClick={openSavedPanel}
            style={topBtnStyle(showSaved && !hasSelection)}
          >
            Saved{allDocSelections.length > 0 ? ` (${allDocSelections.length})` : ''}
          </button>
          <button
            onClick={() => { setShowReview(s => !s); setShowSaved(false); if (hasSelection) clearSelection(); }}
            style={topBtnStyle(showReview && !hasSelection && !showSaved)}
          >
            Edit
          </button>
        </div>
      </div>

      {/* Page navigation bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '8px 16px', borderBottom: '1px solid #eee',
        background: '#fafafa', flexShrink: 0,
      }}>
        <button onClick={() => navigate(-1)} disabled={pageNum <= 1} style={navBtnStyle(pageNum > 1)}>
          ◀
        </button>
        <span style={{ fontSize: '13px', color: '#555' }}>Page</span>
        <input
          type="text"
          value={inputPage}
          onChange={e => setInputPage(e.target.value)}
          onKeyDown={handlePageInput}
          onBlur={() => setInputPage(String(pageNum))}
          style={{ width: '48px', textAlign: 'center', padding: '3px 6px', border: '1px solid #ccc', borderRadius: '4px', fontSize: '13px' }}
        />
        <span style={{ fontSize: '13px', color: '#555' }}>of {totalPages}</span>
        <button onClick={() => navigate(1)} disabled={pageNum >= totalPages} style={navBtnStyle(pageNum < totalPages)}>
          ▶
        </button>
        {pageData?.is_scanned && (
          <span style={{ fontSize: '11px', color: '#f57c00', marginLeft: '8px' }}>OCR page</span>
        )}
        {hasLowConf && (
          <button
            onClick={handleBatchRepair}
            disabled={batchLoading}
            style={{
              marginLeft: 'auto', padding: '4px 12px', border: '1px solid #ffe082',
              borderRadius: '5px', background: '#fffde7', color: '#f57c00',
              fontSize: '12px', cursor: batchLoading ? 'wait' : 'pointer',
            }}
          >
            {batchLoading ? 'Repairing…' : 'AI Fix all'}
          </button>
        )}
        {batchMsg && <span style={{ fontSize: '12px', color: '#388e3c' }}>{batchMsg}</span>}
      </div>

      {/* Content area */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Reading pane */}
        <div style={{
          flex: showRightPanel ? '1 1 55%' : '1 1 100%',
          overflowY: 'auto',
          padding: showImage ? '0' : '24px',
          transition: 'flex 0.2s',
        }}>
          {loading && (
            <p style={{ color: '#888', textAlign: 'center', marginTop: '48px' }}>Loading page…</p>
          )}
          {error && (
            <p style={{ color: '#d32f2f', textAlign: 'center', marginTop: '48px' }}>{error}</p>
          )}

          {!loading && !error && pageData && (
            <>
              {/* Page image (scan view) */}
              {showImage && pageData.has_image && (
                <img
                  src={`${getPageImageUrl(doc.doc_id, pageNum)}?t=${Date.now()}`}
                  alt={`Page ${pageNum}`}
                  style={{ width: '100%', display: 'block' }}
                />
              )}

              {/* Interactive text blocks */}
              {!showImage && (
                <div style={{ maxWidth: '680px', margin: '0 auto' }}>
                  {visibleBlocks.length === 0 && (
                    <p style={{ color: '#888', textAlign: 'center', marginTop: '48px' }}>
                      No text content on this page.
                    </p>
                  )}
                  {visibleBlocks.map(block => (
                    <InteractiveBlock
                      key={block.block_id}
                      block={block}
                      selectedKeys={selectedKeys}
                      savedAnchorKeys={savedAnchorKeys}
                      wordStatuses={wordStatuses}
                      onTokenClick={handleTokenClick}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Right panel: selection > saved review > OCR block edit */}
        {showRightPanel && pageData && (
          hasSelection ? (
            <SelectionPanel
              token={token}
              docId={doc.doc_id}
              language={doc.language}
              selectedTokens={selectedTokens}
              sentenceText={sentenceText}
              savedSelections={savedSelections}
              onSaved={sel => {
                // Keep per-page list and all-doc list in sync
                const upsert = (prev: ReadingSelection[]) => {
                  const idx = prev.findIndex(s => s.selection_id === sel.selection_id);
                  if (idx >= 0) {
                    const next = [...prev]; next[idx] = sel; return next;
                  }
                  return [sel, ...prev];
                };
                setSavedSelections(upsert);
                setAllDocSelections(upsert);
              }}
              onDeleted={id => {
                setSavedSelections(prev => prev.filter(s => s.selection_id !== id));
                setAllDocSelections(prev => prev.filter(s => s.selection_id !== id));
              }}
              onClear={clearSelection}
            />
          ) : showSaved ? (
            <SelectionReviewPanel
              token={token}
              selections={allDocSelections}
              loading={savedLoading}
              onReviewed={updated => {
                setAllDocSelections(prev =>
                  prev.map(s => s.selection_id === updated.selection_id ? updated : s),
                );
              }}
              onDeleted={id => {
                setAllDocSelections(prev => prev.filter(s => s.selection_id !== id));
                setSavedSelections(prev => prev.filter(s => s.selection_id !== id));
              }}
              onClose={() => setShowSaved(false)}
            />
          ) : (
            /* OCR block edit panel */
            <div style={{
              flex: '0 0 340px', borderLeft: '1px solid #eee',
              overflowY: 'auto', background: '#fafafa',
            }}>
              <div style={{ padding: '10px 14px', borderBottom: '1px solid #eee', background: '#f0f0ff' }}>
                <span style={{ fontWeight: 600, fontSize: '13px', color: '#1a237e' }}>
                  Edit — Page {pageNum}
                </span>
                <span style={{ fontSize: '12px', color: '#888', marginLeft: '8px' }}>
                  {pageData.blocks.length} blocks
                </span>
              </div>
              {pageData.blocks.map(block => (
                <BlockRow
                  key={block.block_id}
                  block={block}
                  token={token}
                  docId={doc.doc_id}
                  onUpdated={updateBlock}
                  onPageReload={() => loadPage(pageNum)}
                />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}

// ── Style helpers ─────────────────────────────────────────────────────────────

function navBtnStyle(enabled: boolean) {
  return {
    padding: '4px 10px', border: '1px solid #ddd', borderRadius: '4px',
    cursor: enabled ? 'pointer' : 'not-allowed', background: '#fff',
    color: enabled ? '#1a237e' : '#ccc', fontSize: '14px',
  } as const;
}

function topBtnStyle(active: boolean) {
  return {
    padding: '5px 12px', border: '1px solid #c5cae9',
    borderRadius: '5px', background: active ? '#e8eaf6' : '#fff',
    color: '#1a237e', fontSize: '12px', cursor: 'pointer',
  } as const;
}
