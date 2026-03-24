import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  getPage, listPages, patchBlock, repairBlock, batchRepairPage, deletePage, patchPageSentenceCount,
} from '../api/books';
import { getPageWordStatuses, getPageSelections, listAllSelections, translateSentence } from '../api/reading';
import type { BookDocument, BookPageDetail, BookBlock, ReadingSelection } from '../types';
import { SelectionPanel } from './SelectionPanel';
import type { SelectedToken } from './SelectionPanel';
import { SelectionReviewPanel } from './SelectionReviewPanel';
import { WORD_COLORS } from '../config/wordColors';
import { useWordStatus } from '../hooks/useWordStatus';
import { WordStatusPicker } from './WordStatusPicker';

interface Props {
  token: string;
  doc: BookDocument;
  onClose: () => void;
  darkMode?: boolean;
  autoMarkKnown?: boolean;
}

// ── Tokenizer ─────────────────────────────────────────────────────────────────

interface BlockToken {
  index: number;
  text: string;
  isWord: boolean;
}

function tokenizeBlock(text: string): BlockToken[] {
  const parts = text.split(/(\p{L}[\p{L}\p{M}'-]*)/u);
  let index = 0;
  return parts
    .filter(p => p.length > 0)
    .map(p => ({ index: index++, text: p, isWord: /^\p{L}/u.test(p) }));
}

// Split a block's display_text into sentence-like segments (split on . ! ? followed by space or end)
function splitSentences(text: string): string[] {
  const parts = text.split(/(?<=[.!?])\s+/u);
  return parts.map(s => s.trim()).filter(Boolean);
}

// ── Interactive block component ───────────────────────────────────────────────

interface InteractiveBlockProps {
  block: BookBlock;
  selectedKeys: Set<string>;
  savedAnchorKeys: Set<string>;
  wordStatuses: Record<string, string>;
  onTokenClick: (blockId: number, tokenIndex: number, text: string) => void;
  onWordRightClick?: (word: string) => void;
  translation?: string | null;
  showTranslation: boolean;
  onRequestTranslation: () => void;
  translating: boolean;
  dk?: boolean;
}

function InteractiveBlock({
  block, selectedKeys, savedAnchorKeys, wordStatuses, onTokenClick, onWordRightClick,
  translation, showTranslation, onRequestTranslation, translating, dk,
}: InteractiveBlockProps) {
  const tokens = useMemo(() => tokenizeBlock(block.display_text), [block.display_text]);

  return (
    <div style={{ marginBottom: '1.2em' }}>
      <div style={{
        opacity: block.is_header_footer ? 0.4 : 1,
        fontSize: block.is_header_footer ? '12px' : '16px',
        lineHeight: 1.8,
        color: dk ? '#ccc' : '#222',
        wordBreak: 'break-word',
      }}>
        {tokens.map(tok => {
          if (!tok.isWord) return <span key={tok.index}>{tok.text}</span>;
          const key = `${block.block_id}:${tok.index}`;
          const isSelected = selectedKeys.has(key);
          const isSaved = savedAnchorKeys.has(key);
          const status = wordStatuses[tok.text.toLowerCase()];

          let tokenStyle: React.CSSProperties = { cursor: 'pointer', borderRadius: '3px', padding: '0 1px' };
          if (isSelected) {
            tokenStyle = { ...tokenStyle, background: '#c5cae9', color: '#1a237e', outline: '1px solid #7986cb' };
          } else if (isSaved) {
            tokenStyle = { ...tokenStyle, background: '#fff8e1', color: '#e65100' };
          } else if (status === 'known') {
            tokenStyle = { ...tokenStyle, ...WORD_COLORS.known };
          } else if (status === 'learning') {
            tokenStyle = { ...tokenStyle, ...WORD_COLORS.learning };
          } else if (status === 'unknown') {
            tokenStyle = { ...tokenStyle, ...WORD_COLORS.unknown };
          }

          return (
            <span key={tok.index} style={tokenStyle}
              onClick={() => onTokenClick(block.block_id, tok.index, tok.text)}
              onContextMenu={onWordRightClick ? (e => { e.preventDefault(); onWordRightClick(tok.text); }) : undefined}
              title={isSaved ? 'Saved' : undefined}
            >
              {tok.text}
            </span>
          );
        })}
      </div>

      {/* Translation row */}
      {!block.is_header_footer && (
        <div style={{ marginTop: '4px' }}>
          {showTranslation && translation ? (
            <div style={{ fontSize: '13px', color: '#5c6bc0', fontStyle: 'italic', lineHeight: 1.5, paddingLeft: '2px' }}>
              {translation}
            </div>
          ) : (
            <button
              onClick={onRequestTranslation}
              disabled={translating}
              style={{
                background: 'none', border: 'none', cursor: translating ? 'wait' : 'pointer',
                fontSize: '11px', color: '#9fa8da', padding: '0 2px',
              }}
            >
              {translating ? 'Translating…' : 'Translate'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sentence-mode block component ─────────────────────────────────────────────

interface SentenceCardProps {
  sentence: string;
  blockId: number;
  language: string;
  token: string;
  wordStatuses: Record<string, string>;
  onSkip: (sentence: string) => void;
  onNext: () => void;
  isLast: boolean;
  dk?: boolean;
  autoMark?: boolean;
  onTokenClick?: (blockId: number, tokenIndex: number, text: string) => void;
  onWordRightClick?: (word: string) => void;
  selectedKeys?: Set<string>;
  savedAnchorKeys?: Set<string>;
}

function SentenceCard({ sentence, blockId, language, token, wordStatuses, onSkip, onNext, isLast, dk, autoMark, onTokenClick, onWordRightClick, selectedKeys, savedAnchorKeys }: SentenceCardProps) {
  const [translation, setTranslation] = useState<string | null>(null);
  const [translating, setTranslating] = useState(false);

  const tokens = useMemo(() => tokenizeBlock(sentence), [sentence]);

  async function handleTranslate() {
    setTranslating(true);
    try {
      const t = await translateSentence(token, sentence, language);
      setTranslation(t);
    } catch { /* ignore */ }
    finally { setTranslating(false); }
  }

  return (
    <div style={{
      background: dk ? '#1e1e2e' : '#fff', border: `1px solid ${dk ? '#333' : '#e8eaf6'}`, borderRadius: '10px',
      padding: '20px 24px', maxWidth: '620px', margin: '0 auto',
    }}>
      <div style={{ fontSize: '18px', lineHeight: 1.9, color: dk ? '#c5cae9' : '#1a237e', marginBottom: '10px', wordBreak: 'break-word' }}>
        {tokens.map(tok => {
          if (!tok.isWord) return <span key={tok.index}>{tok.text}</span>;
          const key = `${blockId}:${tok.index}`;
          const isSelected = selectedKeys?.has(key) ?? false;
          const isSaved = savedAnchorKeys?.has(key) ?? false;
          const status = wordStatuses[tok.text.toLowerCase()];
          let style: React.CSSProperties = { borderRadius: '2px', padding: '0 1px' };
          if (onTokenClick) style.cursor = 'pointer';
          if (isSelected) {
            style = { ...style, background: '#c5cae9', color: '#1a237e', outline: '1px solid #7986cb' };
          } else if (isSaved) {
            style = { ...style, background: '#fff8e1', color: '#e65100' };
          } else if (status === 'known') {
            style = { ...style, ...WORD_COLORS.known };
          } else if (status === 'learning') {
            style = { ...style, ...WORD_COLORS.learning };
          } else if (status === 'unknown') {
            style = { ...style, ...WORD_COLORS.unknown };
          }
          return (
            <span key={tok.index} style={style}
              onClick={onTokenClick ? () => onTokenClick(blockId, tok.index, tok.text) : undefined}
              onContextMenu={onWordRightClick ? (e => { e.preventDefault(); onWordRightClick(tok.text); }) : undefined}
            >
              {tok.text}
            </span>
          );
        })}
      </div>

      {translation ? (
        <div style={{ fontSize: '14px', color: '#5c6bc0', fontStyle: 'italic', marginBottom: '14px', lineHeight: 1.5 }}>
          {translation}
        </div>
      ) : (
        <button
          onClick={handleTranslate}
          disabled={translating}
          style={{ background: 'none', border: 'none', fontSize: '12px', color: '#9fa8da', cursor: 'pointer', marginBottom: '14px', padding: 0 }}
        >
          {translating ? 'Translating…' : 'Show translation'}
        </button>
      )}

      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          onClick={onNext}
          style={{ padding: '7px 20px', background: '#1a237e', color: '#fff', border: 'none', borderRadius: '6px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
        >
          {isLast ? 'Done' : 'Next →'}
        </button>
        <button
          onClick={() => onSkip(sentence)}
          style={{ padding: '7px 14px', background: dk ? '#2a2a3e' : '#fff', color: '#888', border: `1px solid ${dk ? '#444' : '#ddd'}`, borderRadius: '6px', fontSize: '13px', cursor: 'pointer' }}
          title={autoMark ? 'Mark all words as passively learned' : 'Skip without marking'}
        >
          {autoMark ? 'Skip (mark seen)' : 'Skip'}
        </button>
      </div>
    </div>
  );
}

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfBadge({ conf }: { conf: number | null }) {
  if (conf === null) return null;
  const color = conf >= 0.8 ? '#388e3c' : conf >= 0.65 ? '#f57c00' : '#d32f2f';
  return (
    <span style={{ fontSize: '10px', color, border: `1px solid ${color}`, borderRadius: '3px', padding: '1px 4px', marginLeft: '6px' }}>
      {Math.round(conf * 100)}%
    </span>
  );
}

// ── Diff view ─────────────────────────────────────────────────────────────────

function DiffView({ original, corrected }: { original: string; corrected: string }) {
  if (original === corrected) return <span style={{ color: '#388e3c', fontSize: '13px' }}>No changes needed.</span>;
  return (
    <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
      <div>
        <span style={{ color: '#888', fontSize: '11px' }}>Original OCR:</span>
        <div style={{ background: '#ffebee', padding: '6px 8px', borderRadius: '4px', marginTop: '2px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{original}</div>
      </div>
      <div style={{ marginTop: '6px' }}>
        <span style={{ color: '#888', fontSize: '11px' }}>Suggested correction:</span>
        <div style={{ background: '#e8f5e9', padding: '6px 8px', borderRadius: '4px', marginTop: '2px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{corrected}</div>
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
  dk?: boolean;
}

function BlockRow({ block, token, docId, onUpdated, onPageReload, dk }: BlockRowProps) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(block.user_text_override ?? block.clean_text ?? '');
  const [repairing, setRepairing] = useState(false);
  const [repairErr, setRepairErr] = useState<string | null>(null);

  const isIgnored     = block.block_type === 'ignored';
  const hasSuggestion = block.correction_status === 'suggested' && block.corrected_text;
  const isLowConf     = block.ocr_confidence !== null && block.ocr_confidence < 0.65;

  async function toggleIgnore() {
    const updated = await patchBlock(token, docId, block.block_id, { block_type: isIgnored ? 'text' : 'ignored' });
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
      padding: '8px 10px', borderBottom: `1px solid ${dk ? '#333' : '#f0f0f0'}`,
      opacity: isIgnored ? 0.4 : 1, background: dk ? '#1e1e2e' : (block.is_header_footer ? '#fafafa' : '#fff'),
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '10px', color: '#aaa' }}>#{block.block_index}</span>
        {block.is_header_footer && (
          <span style={{ fontSize: '10px', color: '#888', background: '#f5f5f5', borderRadius: '3px', padding: '1px 5px' }}>header/footer</span>
        )}
        <ConfBadge conf={block.ocr_confidence} />
        {block.user_text_override !== null && (
          <span style={{ fontSize: '10px', color: '#1565c0', background: '#e3f2fd', borderRadius: '3px', padding: '1px 5px' }}>manual edit</span>
        )}
        {block.correction_status === 'approved' && (
          <span style={{ fontSize: '10px', color: '#388e3c', background: '#e8f5e9', borderRadius: '3px', padding: '1px 5px' }}>LLM approved</span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px' }}>
          <button onClick={toggleIgnore} style={{ fontSize: '11px', padding: '2px 7px', border: '1px solid #ddd', borderRadius: '3px', cursor: 'pointer', color: '#444', background: isIgnored ? '#fff3e0' : '#fff' }}>
            {isIgnored ? 'Restore' : 'Ignore'}
          </button>
          <button onClick={() => { setEditing(e => !e); setEditText(block.user_text_override ?? block.clean_text ?? ''); }}
            style={{ fontSize: '11px', padding: '2px 7px', border: '1px solid #ddd', borderRadius: '3px', cursor: 'pointer', color: '#444', background: editing ? '#e8eaf6' : '#fff' }}>
            Edit
          </button>
          {isLowConf && block.correction_status === 'none' && (
            <button onClick={handleRepair} disabled={repairing}
              style={{ fontSize: '11px', padding: '2px 7px', border: '1px solid #ffe082', borderRadius: '3px', cursor: repairing ? 'wait' : 'pointer', color: '#f57c00', background: '#fffde7' }}>
              {repairing ? 'Repairing…' : 'AI Fix'}
            </button>
          )}
        </div>
      </div>

      {!editing && (
        <div style={{ fontSize: '13px', lineHeight: 1.5, color: dk ? '#ccc' : '#333', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {block.display_text || <em style={{ color: '#aaa' }}>(empty)</em>}
        </div>
      )}

      {editing && (
        <div style={{ marginTop: '4px' }}>
          <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={4}
            style={{ width: '100%', fontSize: '13px', padding: '6px', border: '1px solid #90caf9', borderRadius: '4px', resize: 'vertical', boxSizing: 'border-box' }} />
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

      {repairErr && <p style={{ color: '#d32f2f', fontSize: '12px', margin: '4px 0 0' }}>{repairErr}</p>}
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

export function BookReaderPage({ token, doc, onClose, darkMode, autoMarkKnown }: Props) {
  const [dk, setDk] = useState(darkMode ?? false);
  const th = {
    bg:     dk ? '#121212' : '#fff',
    bgBar:  dk ? '#1a1a2e' : '#f8f9ff',
    bgSub:  dk ? '#1e1e2e' : '#fafafa',
    text:   dk ? '#e0e0e0' : '#222',
    accent: dk ? '#7986cb' : '#1a237e',
    border: dk ? '#333'    : '#eee',
    muted:  dk ? '#aaa'    : '#888',
  } as const;
  const [pageNum, setPageNum]       = useState(1);
  const [inputPage, setInputPage]   = useState('1');
  const [pageData, setPageData]     = useState<BookPageDetail | null>(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);
  const [showImage, setShowImage]         = useState(false);
  const [showReview, setShowReview]       = useState(false);
  const [showSaved, setShowSaved]         = useState(false);
  const [allDocSelections, setAllDocSelections] = useState<ReadingSelection[]>([]);
  const [savedLoading, setSavedLoading]   = useState(false);
  const [batchLoading, setBatchLoading]   = useState(false);
  const [batchMsg, setBatchMsg]     = useState<string | null>(null);

  // Reading mode
  const [readingMode, setReadingMode] = useState<'page' | 'sentence'>('page');
  const [sentenceIdx, setSentenceIdx] = useState(0);

  // Translations: keyed by block_id
  const [translations, setTranslations] = useState<Record<number, string>>({});
  const [translating, setTranslating]   = useState<Record<number, boolean>>({});
  const [shownTranslations, setShownTranslations] = useState<Set<number>>(new Set());

  // Page deletion confirm
  const [deletePageConfirm, setDeletePageConfirm] = useState(false);
  const [deletingPage, setDeletingPage] = useState(false);

  // Ordered list of surviving DB page numbers; empty until loaded
  const [pageList, setPageList] = useState<number[]>([]);
  // Bump to force page reload when pageNum stays same but actualPageNumber changes (e.g. after deletion)
  const [pageLoadTrigger, setPageLoadTrigger] = useState(0);
  // Gate: don't call loadPage until we know the real page numbers
  const [pageListLoaded, setPageListLoaded] = useState(false);
  // Sentence count per actual page number — populated from DB, then filled by background preloader
  const [sentenceCountMap, setSentenceCountMap] = useState<Record<number, number>>({});

  // Auto-mark words on skip — initialized from global pref, overridable per session
  const [autoMark, setAutoMark] = useState(autoMarkKnown ?? false);

  // Page image — fetched with auth headers as a blob URL
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const imagePageRef = useRef<number | null>(null);

  // Ref for keyboard navigation — always has the latest navigate logic without stale closure
  const navigateRef = useRef<(delta: number) => void>(() => {});

  // Word status picker (right-click)
  const { selected: wsSelected, state: wsState, selectWord, updateStatus, dismiss: wsDismiss } = useWordStatus(token, doc.language);

  // Interactive reading state
  const [selectedKeys, setSelectedKeys]       = useState<Set<string>>(new Set());
  const [wordStatuses, setWordStatuses]       = useState<Record<string, string>>({});
  const [savedSelections, setSavedSelections] = useState<ReadingSelection[]>([]);

  // Actual DB page_number for the current display position
  const actualPageNumber = pageList.length > 0
    ? (pageList[pageNum - 1] ?? pageList[pageList.length - 1])
    : pageNum;
  const totalPages = pageList.length || doc.total_pages || 1;

  const loadPage = useCallback(async (n: number) => {
    setLoading(true);
    setError(null);
    setPageData(null);
    setSelectedKeys(new Set());
    setWordStatuses({});
    setSavedSelections([]);
    setTranslations({});
    setShownTranslations(new Set());
    setSentenceIdx(0);
    try {
      const data = await getPage(token, doc.doc_id, n);
      setPageData(data);
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

  // Load the ordered page list once on mount; loadPage is gated on this
  useEffect(() => {
    listPages(token, doc.doc_id)
      .then(pages => {
        setPageList(pages.map(p => p.page_number));
        // Seed sentence counts already saved in DB
        const known: Record<number, number> = {};
        for (const p of pages) {
          if (p.sentence_count != null) known[p.page_number] = p.sentence_count;
        }
        if (Object.keys(known).length > 0) setSentenceCountMap(known);
      })
      .catch(() => {})
      .finally(() => setPageListLoaded(true));
  }, [token, doc.doc_id]);

  // Background preloader: compute and persist sentence counts for pages not yet cached
  useEffect(() => {
    if (!pageListLoaded || pageList.length === 0) return;
    const abort = { cancelled: false };
    (async () => {
      for (const pNum of pageList) {
        if (abort.cancelled) break;
        // Skip if already cached from DB
        if (sentenceCountMap[pNum] !== undefined) continue; // eslint-disable-line react-hooks/exhaustive-deps
        try {
          const data = await getPage(token, doc.doc_id, pNum);
          if (abort.cancelled) break;
          const count = data.blocks
            .filter(b => !b.is_header_footer && b.display_text && b.block_type !== 'ignored')
            .flatMap(b => splitSentences(b.display_text))
            .length;
          setSentenceCountMap(prev => ({ ...prev, [pNum]: count }));
          patchPageSentenceCount(token, doc.doc_id, pNum, count).catch(() => {});
        } catch { /* skip */ }
      }
    })();
    return () => { abort.cancelled = true; };
  }, [pageListLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!pageListLoaded) return; // wait for real page numbers before fetching
    loadPage(actualPageNumber); // eslint-disable-line react-hooks/exhaustive-deps
    setInputPage(String(pageNum));
    setBatchMsg(null);
    setDeletePageConfirm(false);
    // Reset image and re-fetch if Edit or Scan mode is already active
    setImageSrc(null);
    imagePageRef.current = null;
    if (showReview || showImage) loadPageImage(); // eslint-disable-line react-hooks/exhaustive-deps
  }, [pageNum, pageLoadTrigger, loadPage, pageListLoaded]); // actualPageNumber/showReview/showImage via closure

  async function loadPageImage() {
    if (imagePageRef.current === actualPageNumber) return;
    imagePageRef.current = actualPageNumber;
    try {
      const res = await fetch(`/api/v1/books/${doc.doc_id}/pages/${actualPageNumber}/image`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const blob = await res.blob();
      setImageSrc(URL.createObjectURL(blob));
    } catch { /* ignore */ }
  }

  function navigate(delta: number) {
    const next = Math.max(1, Math.min(totalPages, pageNum + delta));
    setPageNum(next);
    setSentenceIdx(0);
  }

  // Keep navigateRef current so the keyboard handler never has stale closures
  navigateRef.current = (delta: number) => {
    if (readingMode === 'sentence') {
      if (delta > 0) {
        if (sentenceIdx === allSentences.length - 1) {
          if (pageNum < totalPages) navigate(1);
          else setSentenceIdx(0);
        } else {
          setSentenceIdx(i => i + 1);
        }
      } else {
        if (sentenceIdx === 0) {
          if (pageNum > 1) navigate(-1);
        } else {
          setSentenceIdx(i => i - 1);
        }
      }
    } else {
      navigate(delta);
    }
  };

  // Register A/D keyboard navigation once
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as Element).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'a' || e.key === 'A' || e.key === 'ArrowLeft')  navigateRef.current(-1);
      if (e.key === 'd' || e.key === 'D' || e.key === 'ArrowRight') navigateRef.current(1);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []); // empty — ref handles fresh state

  function handlePageInput(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      const n = parseInt(inputPage, 10);
      if (!isNaN(n) && n >= 1 && n <= totalPages) { setPageNum(n); setSentenceIdx(0); }
      else setInputPage(String(pageNum));
    }
  }

  function updateBlock(updated: BookBlock) {
    if (!pageData) return;
    setPageData(prev => prev ? {
      ...prev, blocks: prev.blocks.map(b => b.block_id === updated.block_id ? updated : b),
    } : prev);
  }

  async function handleBatchRepair() {
    setBatchLoading(true);
    setBatchMsg(null);
    try {
      const result = await batchRepairPage(token, doc.doc_id, actualPageNumber);
      setBatchMsg(`Repaired ${result.repaired} block(s) of ${result.total_candidates} candidates.`);
      await loadPage(actualPageNumber);
    } catch (e) {
      setBatchMsg(`Error: ${(e as Error).message}`);
    } finally {
      setBatchLoading(false);
    }
  }

  async function handleDeletePage() {
    setDeletingPage(true);
    try {
      await deletePage(token, doc.doc_id, actualPageNumber);
      // Re-fetch authoritative page list; fall back to local filter if request fails
      const freshPages = await listPages(token, doc.doc_id).catch(() => null);
      const newPageList = freshPages
        ? freshPages.map(p => p.page_number)
        : pageList.filter(n => n !== actualPageNumber);
      setPageList(newPageList);
      if (newPageList.length === 0) {
        // Book is empty — nothing to show
        setPageData(null);
        setError('No pages remaining.');
      } else if (pageNum > newPageList.length) {
        setPageNum(newPageList.length);
      } else {
        setPageLoadTrigger(t => t + 1);
      }
    } catch { /* ignore */ }
    finally {
      setDeletingPage(false);
      setDeletePageConfirm(false);
    }
  }

  // Translation helpers
  async function requestTranslation(blockId: number, text: string) {
    if (translations[blockId]) {
      setShownTranslations(prev => { const s = new Set(prev); s.add(blockId); return s; });
      return;
    }
    setTranslating(prev => ({ ...prev, [blockId]: true }));
    try {
      const t = await translateSentence(token, text, doc.language);
      setTranslations(prev => ({ ...prev, [blockId]: t }));
      setShownTranslations(prev => { const s = new Set(prev); s.add(blockId); return s; });
    } catch { /* ignore */ }
    finally { setTranslating(prev => ({ ...prev, [blockId]: false })); }
  }

  // Sentence mode: flat list of all sentences across all visible blocks
  const visibleBlocks = useMemo(() => pageData?.blocks.filter(b => b.block_type !== 'ignored') ?? [], [pageData]);

  const allSentences = useMemo((): { sentence: string; blockId: number }[] => {
    const out: { sentence: string; blockId: number }[] = [];
    for (const block of visibleBlocks) {
      if (!block.is_header_footer && block.display_text) {
        const sents = splitSentences(block.display_text);
        for (const s of sents) out.push({ sentence: s, blockId: block.block_id });
      }
    }
    return out;
  }, [visibleBlocks]);

  // Skip sentence: optionally mark unknown words as "learning" (passive), then advance
  async function handleSkipSentence(sentence: string) {
    if (autoMark) {
      const words = sentence.match(/\p{L}[\p{L}\p{M}'-]*/gu) ?? [];
      const uniqueUnknown = [...new Set(
        words
          .filter(w => { const s = wordStatuses[w.toLowerCase()]; return !s || s === 'unknown'; })
          .map(w => w.toLowerCase()),
      )];
      if (uniqueUnknown.length > 0) {
        const update: Record<string, string> = {};
        for (const w of uniqueUnknown) update[w] = 'learning';
        setWordStatuses(prev => ({ ...prev, ...update }));
      }
    }
    setSentenceIdx(i => Math.min(i + 1, allSentences.length - 1));
  }

  // Selection logic
  function handleTokenClick(blockId: number, tokenIndex: number, _text: string) {
    const key = `${blockId}:${tokenIndex}`;
    setSelectedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function clearSelection() { setSelectedKeys(new Set()); }

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
      } catch { /* non-fatal */ }
      finally { setSavedLoading(false); }
    }
  }

  const selectedTokens: SelectedToken[] = useMemo(() => {
    if (!pageData || selectedKeys.size === 0) return [];
    const tokens: SelectedToken[] = [];
    pageData.blocks.forEach((block, blockOrder) => {
      const toks = tokenizeBlock(block.display_text);
      toks.forEach(tok => {
        const key = `${block.block_id}:${tok.index}`;
        if (selectedKeys.has(key) && tok.isWord) {
          tokens.push({ blockId: block.block_id, tokenIndex: tok.index, text: tok.text, blockOrder });
        }
      });
    });
    return tokens;
  }, [selectedKeys, pageData]);

  const sentenceText = useMemo(() => {
    if (selectedTokens.length === 0 || !pageData) return '';
    const first = selectedTokens[0];
    const block = pageData.blocks.find(b => b.block_id === first.blockId);
    return block?.display_text ?? '';
  }, [selectedTokens, pageData]);

  const savedAnchorKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const sel of savedSelections) {
      for (const anchor of sel.anchors) keys.add(`${anchor.block_id}:${anchor.token_index}`);
    }
    return keys;
  }, [savedSelections]);

  const hasSelection  = selectedKeys.size > 0 && selectedTokens.length > 0;
  const hasLowConf    = pageData?.blocks.some(b => b.ocr_confidence !== null && b.ocr_confidence < 0.65 && b.correction_status === 'none') ?? false;
  const showRightPanel = hasSelection || showSaved; // Edit panel is now annotation split view

  // Global sentence counter
  const sentencesBefore = pageList.slice(0, pageNum - 1).reduce((acc, pNum) => acc + (sentenceCountMap[pNum] ?? 0), 0);
  const globalSentenceIdx = sentencesBefore + sentenceIdx + 1;
  const allPagesCounted = pageList.length > 0 && pageList.every(pNum => sentenceCountMap[pNum] !== undefined);
  const totalSentences = allPagesCounted ? pageList.reduce((acc, pNum) => acc + (sentenceCountMap[pNum] ?? 0), 0) : null;

  return (
    <div style={{ position: 'fixed', inset: 0, background: th.bg, zIndex: 900, display: 'flex', flexDirection: 'column', overflow: 'hidden', color: th.text }}>

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 16px', borderBottom: `1px solid ${th.border}`, background: th.bgBar, flexShrink: 0, flexWrap: 'wrap' }}>
        <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '16px', cursor: 'pointer', color: th.accent, fontWeight: 700 }}>
          ← Back
        </button>
        <span style={{ fontWeight: 700, fontSize: '15px', color: th.accent, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {doc.title}
        </span>

        {/* Mode toggle */}
        <div style={{ display: 'flex', border: `1px solid ${dk ? '#4a4a6a' : '#c5cae9'}`, borderRadius: '6px', overflow: 'hidden' }}>
          {(['page', 'sentence'] as const).map(m => (
            <button key={m} onClick={() => { setReadingMode(m); setSentenceIdx(0); }}
              style={{
                padding: '4px 12px', fontSize: '12px', border: 'none',
                background: readingMode === m ? (dk ? '#2a2a4e' : '#e8eaf6') : (dk ? '#1e1e2e' : '#fff'),
                color: readingMode === m ? (dk ? '#9fa8da' : '#1a237e') : (dk ? '#666' : '#888'),
                cursor: 'pointer', fontWeight: readingMode === m ? 600 : 400,
              }}>
              {m === 'page' ? 'Page' : 'Sentence'}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: th.muted, cursor: 'pointer', userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={autoMark}
              onChange={e => setAutoMark(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            Auto-mark
          </label>
          <button onClick={() => setDk(d => !d)} style={topBtnStyle(dk, dk)}>{dk ? 'Light' : 'Dark'}</button>
          {pageData?.has_image && (
            <button onClick={() => { setShowImage(s => !s); if (!showImage) loadPageImage(); }} style={topBtnStyle(showImage, dk)}>Scan</button>
          )}
          <button onClick={openSavedPanel} style={topBtnStyle(showSaved && !hasSelection, dk)}>
            Saved{allDocSelections.length > 0 ? ` (${allDocSelections.length})` : ''}
          </button>
          <button onClick={() => { const next = !showReview; setShowReview(next); setShowSaved(false); if (hasSelection) clearSelection(); if (next) loadPageImage(); }}
            style={topBtnStyle(showReview && !hasSelection && !showSaved, dk)}>
            Edit
          </button>
        </div>
      </div>

      {/* Page navigation bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', borderBottom: `1px solid ${th.border}`, background: th.bgSub, flexShrink: 0, flexWrap: 'wrap' }}>
        <button
          onClick={() => navigateRef.current(-1)}
          disabled={readingMode === 'sentence' ? (sentenceIdx === 0 && pageNum <= 1) : pageNum <= 1}
          style={navBtnStyle(readingMode === 'sentence' ? (sentenceIdx > 0 || pageNum > 1) : pageNum > 1, dk)}
        >◀</button>
        <span style={{ fontSize: '13px', color: th.muted }}>Page</span>
        <input type="text" value={inputPage}
          onChange={e => setInputPage(e.target.value)}
          onKeyDown={handlePageInput}
          onBlur={() => setInputPage(String(pageNum))}
          style={{ width: '48px', textAlign: 'center', padding: '3px 6px', border: `1px solid ${dk ? '#444' : '#ccc'}`, borderRadius: '4px', fontSize: '13px', background: dk ? '#1e1e2e' : '#fff', color: th.text }}
        />
        <span style={{ fontSize: '13px', color: th.muted }}>of {totalPages}</span>
        <button
          onClick={() => navigateRef.current(1)}
          disabled={readingMode === 'sentence' ? (sentenceIdx === allSentences.length - 1 && pageNum >= totalPages) : pageNum >= totalPages}
          style={navBtnStyle(readingMode === 'sentence' ? (sentenceIdx < allSentences.length - 1 || pageNum < totalPages) : pageNum < totalPages, dk)}
        >▶</button>
        {pageData?.is_scanned && <span style={{ fontSize: '11px', color: '#f57c00', marginLeft: '8px' }}>OCR page</span>}

        {/* Page delete */}
        {showReview && (
          deletePageConfirm ? (
            <>
              <button onClick={handleDeletePage} disabled={deletingPage}
                style={{ marginLeft: 'auto', padding: '4px 12px', background: '#d32f2f', color: '#fff', border: 'none', borderRadius: '5px', fontSize: '12px', cursor: 'pointer' }}>
                {deletingPage ? 'Deleting…' : 'Confirm delete'}
              </button>
              <button onClick={() => setDeletePageConfirm(false)}
                style={{ padding: '4px 10px', background: '#eee', color: '#444', border: '1px solid #ddd', borderRadius: '5px', fontSize: '12px', cursor: 'pointer' }}>
                Cancel
              </button>
            </>
          ) : (
            <button onClick={() => setDeletePageConfirm(true)}
              style={{ marginLeft: 'auto', padding: '4px 12px', border: '1px solid #ffcdd2', borderRadius: '5px', background: '#fff', color: '#d32f2f', fontSize: '12px', cursor: 'pointer' }}>
              Delete page
            </button>
          )
        )}

        {hasLowConf && !showReview && (
          <button onClick={handleBatchRepair} disabled={batchLoading}
            style={{ marginLeft: 'auto', padding: '4px 12px', border: '1px solid #ffe082', borderRadius: '5px', background: '#fffde7', color: '#f57c00', fontSize: '12px', cursor: batchLoading ? 'wait' : 'pointer' }}>
            {batchLoading ? 'Repairing…' : 'AI Fix all'}
          </button>
        )}
        {batchMsg && <span style={{ fontSize: '12px', color: '#388e3c' }}>{batchMsg}</span>}
      </div>

      {/* Content area */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', background: th.bg }}>

        {/* ── Annotation split view (Edit mode) ─────────────────────────────── */}
        {showReview && !hasSelection && !showSaved && pageData && (
          <>
            {/* Left: block annotation list */}
            <div style={{ flex: '1 1 50%', overflowY: 'auto', borderRight: `1px solid ${th.border}`, background: th.bgSub }}>
              <div style={{ padding: '10px 14px', borderBottom: `1px solid ${th.border}`, background: dk ? '#2a2a3e' : '#f0f0ff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 600, fontSize: '13px', color: th.accent }}>Annotation — Page {pageNum}</span>
                <span style={{ fontSize: '12px', color: th.muted }}>{pageData.blocks.length} blocks</span>
              </div>
              {pageData.blocks.map(block => (
                <BlockRow
                  key={block.block_id}
                  block={block}
                  token={token}
                  docId={doc.doc_id}
                  onUpdated={updateBlock}
                  onPageReload={() => loadPage(actualPageNumber)}
                  dk={dk}
                />
              ))}
            </div>
            {/* Right: scanned page image */}
            <div style={{ flex: '0 0 50%', overflowY: 'auto', background: dk ? '#1a1a1a' : '#f5f5f5', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              {imageSrc ? (
                <img src={imageSrc} alt={`Page ${pageNum} scan`} style={{ width: '100%', display: 'block' }} />
              ) : pageData.has_image ? (
                <p style={{ color: th.muted, marginTop: '48px', fontSize: '14px' }}>Loading scan…</p>
              ) : (
                <p style={{ color: th.muted, marginTop: '48px', fontSize: '14px' }}>No scan available for this page.</p>
              )}
            </div>
          </>
        )}

        {/* ── Normal reading pane (non-edit) ────────────────────────────────── */}
        {!(showReview && !hasSelection && !showSaved) && (<>
        <div style={{ flex: (hasSelection || showSaved) ? '1 1 55%' : showImage ? '1 1 55%' : '1 1 100%', overflowY: 'auto', padding: '24px', transition: 'flex 0.2s' }}>
          {loading && <p style={{ color: th.muted, textAlign: 'center', marginTop: '48px' }}>Loading page…</p>}
          {error   && <p style={{ color: '#d32f2f', textAlign: 'center', marginTop: '48px' }}>{error}</p>}

          {!loading && !error && pageData && (
            <>
              {readingMode === 'page' && (
                <div style={{ maxWidth: '680px', margin: '0 auto' }}>
                  {visibleBlocks.length === 0 && (
                    <p style={{ color: th.muted, textAlign: 'center', marginTop: '48px' }}>No text content on this page.</p>
                  )}
                  {visibleBlocks.map(block => (
                    <InteractiveBlock
                      key={block.block_id}
                      block={block}
                      selectedKeys={selectedKeys}
                      savedAnchorKeys={savedAnchorKeys}
                      wordStatuses={wordStatuses}
                      onTokenClick={handleTokenClick}
                      onWordRightClick={selectWord}
                      translation={translations[block.block_id] ?? null}
                      showTranslation={shownTranslations.has(block.block_id)}
                      onRequestTranslation={() => requestTranslation(block.block_id, block.display_text)}
                      translating={translating[block.block_id] ?? false}
                      dk={dk}
                    />
                  ))}
                </div>
              )}

              {readingMode === 'sentence' && (
                <div style={{ padding: '32px 16px' }}>
                  {allSentences.length === 0 ? (
                    <p style={{ color: th.muted, textAlign: 'center' }}>No sentences on this page.</p>
                  ) : sentenceIdx < allSentences.length ? (
                    <>
                      <div style={{ textAlign: 'center', marginBottom: '16px', fontSize: '12px', color: th.muted }}>
                        {totalSentences !== null
                          ? `${globalSentenceIdx} / ${totalSentences}`
                          : `${globalSentenceIdx} / …`}
                      </div>
                      <SentenceCard
                        sentence={allSentences[sentenceIdx].sentence}
                        blockId={allSentences[sentenceIdx].blockId}
                        language={doc.language}
                        token={token}
                        wordStatuses={wordStatuses}
                        onSkip={handleSkipSentence}
                        onNext={() => {
                          if (sentenceIdx === allSentences.length - 1) {
                            // Last sentence done — auto-navigate to next page
                            if (pageNum < totalPages) navigate(1);
                            else setSentenceIdx(0); // last page: restart from top
                          } else {
                            setSentenceIdx(i => i + 1);
                          }
                        }}
                        isLast={sentenceIdx === allSentences.length - 1}
                        dk={dk}
                        autoMark={autoMark}
                        onTokenClick={handleTokenClick}
                        onWordRightClick={selectWord}
                        selectedKeys={selectedKeys}
                        savedAnchorKeys={savedAnchorKeys}
                      />
                    </>
                  ) : null}
                </div>
              )}
            </>
          )}
        </div>

        {/* Scan image panel — side by side with text */}
        {showImage && (imageSrc || pageData?.has_image) && (
          <div style={{ flex: '0 0 42%', overflowY: 'auto', borderLeft: `1px solid ${th.border}`, background: dk ? '#1a1a1a' : '#f0f0f0', display: 'flex', alignItems: 'flex-start', justifyContent: 'center' }}>
            {imageSrc
              ? <img src={imageSrc} alt={`Page ${pageNum} scan`} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', display: 'block' }} />
              : <p style={{ color: th.muted, padding: '24px', textAlign: 'center' }}>Loading scan…</p>
            }
          </div>
        )}

        {/* Right panel — selections and saved (only in non-edit mode) */}
        {(hasSelection || showSaved) && pageData && (
          hasSelection ? (
            <SelectionPanel
              token={token}
              docId={doc.doc_id}
              language={doc.language}
              selectedTokens={selectedTokens}
              sentenceText={sentenceText}
              savedSelections={savedSelections}
              onSaved={sel => {
                const upsert = (prev: ReadingSelection[]) => {
                  const idx = prev.findIndex(s => s.selection_id === sel.selection_id);
                  if (idx >= 0) { const next = [...prev]; next[idx] = sel; return next; }
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
              dk={dk}
            />
          ) : (
            <SelectionReviewPanel
              token={token}
              selections={allDocSelections}
              loading={savedLoading}
              onReviewed={updated => {
                setAllDocSelections(prev => prev.map(s => s.selection_id === updated.selection_id ? updated : s));
              }}
              onDeleted={id => {
                setAllDocSelections(prev => prev.filter(s => s.selection_id !== id));
                setSavedSelections(prev => prev.filter(s => s.selection_id !== id));
              }}
              onClose={() => setShowSaved(false)}
              dk={dk}
            />
          )
        )}
        </>)} {/* end normal reading pane conditional */}
      </div>

      {/* Word status picker — shown at bottom when a word is right-clicked */}
      {wsSelected && (
        <WordStatusPicker
          word={wsSelected}
          lookup={wsState.lookup}
          loading={wsState.loading}
          saving={wsState.saving}
          onSelect={async (wordId, status) => {
            await updateStatus(wordId, status);
            setWordStatuses(prev => ({ ...prev, [wsSelected.toLowerCase()]: status }));
          }}
          onDismiss={wsDismiss}
        />
      )}
    </div>
  );
}

function navBtnStyle(enabled: boolean, dk = false) {
  return {
    padding: '4px 10px', border: `1px solid ${dk ? '#444' : '#ddd'}`, borderRadius: '4px',
    cursor: enabled ? 'pointer' : 'not-allowed', background: dk ? '#1e1e2e' : '#fff',
    color: enabled ? (dk ? '#9fa8da' : '#1a237e') : (dk ? '#555' : '#ccc'), fontSize: '14px',
  } as const;
}

function topBtnStyle(active: boolean, dk = false) {
  return {
    padding: '5px 12px', border: `1px solid ${dk ? '#4a4a6a' : '#c5cae9'}`, borderRadius: '5px',
    background: active ? (dk ? '#2a2a4e' : '#e8eaf6') : (dk ? '#1e1e2e' : '#fff'),
    color: dk ? '#9fa8da' : '#1a237e', fontSize: '12px', cursor: 'pointer',
  } as const;
}
