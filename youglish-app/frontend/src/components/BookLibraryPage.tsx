import { useState, useEffect, useRef } from 'react';
import { listBooks, uploadBook, getBook, deleteBook } from '../api/books';
import type { BookDocument } from '../types';

interface Props {
  token: string;
  onOpen: (doc: BookDocument) => void;
  onClose: () => void;
  darkMode?: boolean;
}

const STATUS_LABELS: Record<string, string> = {
  pending:    'Queued',
  processing: 'Processing…',
  ready:      'Ready',
  error:      'Error',
};

const STATUS_COLORS: Record<string, string> = {
  pending:    '#888',
  processing: '#f57c00',
  ready:      '#388e3c',
  error:      '#d32f2f',
};

const LANG_LABELS: Record<string, string> = {
  de: 'German', en: 'English', fr: 'French', es: 'Spanish',
  it: 'Italian', pt: 'Portuguese', ja: 'Japanese', ru: 'Russian',
  ko: 'Korean', tr: 'Turkish', pl: 'Polish', sv: 'Swedish',
};

type SortKey = 'newest' | 'oldest' | 'az' | 'za' | 'language' | 'status';

function sortBooks(books: BookDocument[], key: SortKey): BookDocument[] {
  const sorted = [...books];
  switch (key) {
    case 'newest':
      return sorted.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    case 'oldest':
      return sorted.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    case 'az':
      return sorted.sort((a, b) => a.title.localeCompare(b.title));
    case 'za':
      return sorted.sort((a, b) => b.title.localeCompare(a.title));
    case 'language':
      return sorted.sort((a, b) => a.language.localeCompare(b.language) || a.title.localeCompare(b.title));
    case 'status': {
      const order: Record<string, number> = { ready: 0, processing: 1, pending: 2, error: 3 };
      return sorted.sort((a, b) => (order[a.status] ?? 4) - (order[b.status] ?? 4));
    }
    default:
      return sorted;
  }
}

export function BookLibraryPage({ token, onOpen, onClose, darkMode }: Props) {
  const dk = darkMode ?? false;
  const th = {
    bg:     dk ? '#1e1e2e' : '#fff',
    bgSub:  dk ? '#2a2a3e' : '#fafbff',
    text:   dk ? '#e0e0e0' : '#1a237e',
    muted:  dk ? '#aaa'    : '#999',
    border: dk ? '#333'    : '#eee',
    card:   dk ? '#2a2a3e' : '#fff',
  } as const;
  const [books, setBooks]       = useState<BookDocument[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [title, setTitle]       = useState('');
  const [language, setLanguage] = useState('de');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sortKey, setSortKey]   = useState<SortKey>('newest');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null); // doc_id pending delete
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const data = await listBooks(token);
        setBooks(data);
        setLoading(false);
        const processing = data.filter(b => b.status === 'pending' || b.status === 'processing');
        if (processing.length > 0) timer = setTimeout(refresh, 3000);
      } catch (e) {
        setError((e as Error).message);
        setLoading(false);
      }
    }
    refresh();
    return () => clearTimeout(timer);
  }, [token]);

  async function pollSingle(docId: string) {
    let attempts = 0;
    async function tick() {
      if (attempts++ >= 120) return;
      const doc = await getBook(token, docId);
      setBooks(prev => prev.map(b => b.doc_id === docId ? doc : b));
      if (doc.status === 'pending' || doc.status === 'processing') setTimeout(tick, 3000);
    }
    setTimeout(tick, 3000);
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setUploadError(null);
    try {
      const doc = await uploadBook(
        token,
        selectedFile,
        title.trim() || selectedFile.name.replace(/\.pdf$/i, ''),
        language,
      );
      setBooks(prev => [doc, ...prev]);
      setSelectedFile(null);
      setTitle('');
      if (fileRef.current) fileRef.current.value = '';
      pollSingle(doc.doc_id);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(docId: string) {
    setDeleting(docId);
    try {
      await deleteBook(token, docId);
      setBooks(prev => prev.filter(b => b.doc_id !== docId));
    } catch {
      // silently ignore — book may already be gone
    } finally {
      setDeleting(null);
      setDeleteConfirm(null);
    }
  }

  const sortedBooks = sortBooks(books, sortKey);

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: th.bg, borderRadius: '12px',
        width: '680px', maxWidth: '96vw', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        boxShadow: '0 12px 40px rgba(0,0,0,0.4)',
        color: dk ? '#e0e0e0' : undefined,
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '18px 22px 14px', borderBottom: `1px solid ${th.border}`,
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '18px', color: th.text }}>My Books</h2>
            {books.length > 0 && (
              <span style={{ fontSize: '12px', color: th.muted }}>
                {books.filter(b => b.status === 'ready').length} ready · {books.length} total
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: th.muted, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        {/* Upload form */}
        <form onSubmit={handleUpload} style={{ padding: '14px 22px', borderBottom: `1px solid ${th.border}`, background: th.bgSub }}>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 200px' }}>
              <label style={{ fontSize: '11px', color: '#666', display: 'block', marginBottom: '4px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                PDF File
              </label>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                onChange={e => {
                  const f = e.target.files?.[0] ?? null;
                  setSelectedFile(f);
                  if (f && !title) setTitle(f.name.replace(/\.pdf$/i, ''));
                }}
                style={{ fontSize: '12px', width: '100%' }}
              />
            </div>
            <div style={{ flex: '1 1 150px' }}>
              <label style={{ fontSize: '11px', color: '#666', display: 'block', marginBottom: '4px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Title
              </label>
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="Book title"
                style={{ width: '100%', padding: '6px 8px', border: '1px solid #ccc', borderRadius: '6px', fontSize: '13px', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ flex: '0 0 90px' }}>
              <label style={{ fontSize: '11px', color: '#666', display: 'block', marginBottom: '4px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Language
              </label>
              <select
                value={language}
                onChange={e => setLanguage(e.target.value)}
                style={{ width: '100%', padding: '6px 8px', border: '1px solid #ccc', borderRadius: '6px', fontSize: '13px' }}
              >
                {Object.entries(LANG_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={!selectedFile || uploading}
              style={{
                padding: '7px 18px', background: '#1a237e', color: '#fff',
                border: 'none', borderRadius: '6px', fontSize: '13px', fontWeight: 600,
                cursor: selectedFile && !uploading ? 'pointer' : 'not-allowed',
                opacity: selectedFile && !uploading ? 1 : 0.5,
                whiteSpace: 'nowrap', flexShrink: 0,
              }}
            >
              {uploading ? 'Uploading…' : 'Upload'}
            </button>
          </div>
          {uploadError && (
            <p style={{ color: '#d32f2f', fontSize: '12px', margin: '6px 0 0' }}>{uploadError}</p>
          )}
        </form>

        {/* Sort bar */}
        {books.length > 1 && (
          <div style={{ padding: '8px 22px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: '8px', background: '#fff' }}>
            <span style={{ fontSize: '11px', color: '#999', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
              Sort
            </span>
            {([
              ['newest', 'Newest'],
              ['oldest', 'Oldest'],
              ['az', 'A → Z'],
              ['za', 'Z → A'],
              ['language', 'Language'],
              ['status', 'Status'],
            ] as [SortKey, string][]).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setSortKey(key)}
                style={{
                  padding: '3px 10px', fontSize: '12px', borderRadius: '12px',
                  border: '1px solid ' + (sortKey === key ? '#1a237e' : '#ddd'),
                  background: sortKey === key ? '#e8eaf6' : '#fff',
                  color: sortKey === key ? '#1a237e' : '#555',
                  cursor: 'pointer', fontWeight: sortKey === key ? 600 : 400,
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {/* Book list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 22px', background: th.bg }}>
          {loading && (
            <p style={{ color: '#888', textAlign: 'center', marginTop: '32px' }}>Loading…</p>
          )}
          {error && (
            <p style={{ color: '#d32f2f', textAlign: 'center', marginTop: '32px' }}>{error}</p>
          )}
          {!loading && !error && books.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: '40px', color: '#aaa' }}>
              <div style={{ fontSize: '32px', marginBottom: '10px' }}>📚</div>
              <p style={{ margin: 0, fontSize: '14px' }}>No books yet.</p>
              <p style={{ margin: '4px 0 0', fontSize: '13px' }}>Upload a PDF to get started.</p>
            </div>
          )}

          {sortedBooks.map(book => (
            <div
              key={book.doc_id}
              style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '12px 0', borderBottom: `1px solid ${th.border}`,
              }}
            >
              {/* Book icon */}
              <div style={{
                flexShrink: 0, width: '36px', height: '48px',
                background: '#e8eaf6', borderRadius: '4px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '18px', color: '#5c6bc0',
              }}>
                📖
              </div>

              {/* Info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: '14px', color: th.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {book.title}
                </div>
                <div style={{ fontSize: '12px', color: th.muted, marginTop: '2px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <span>{LANG_LABELS[book.language] ?? book.language.toUpperCase()}</span>
                  {book.total_pages != null && (
                    <span>{book.total_pages} pages</span>
                  )}
                  <span style={{ color: STATUS_COLORS[book.status] ?? '#888', fontWeight: 500 }}>
                    {STATUS_LABELS[book.status] ?? book.status}
                  </span>
                </div>
                {book.status === 'error' && book.error_message && (
                  <div style={{ fontSize: '11px', color: '#d32f2f', marginTop: '2px' }}>
                    {book.error_message}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                {book.status === 'ready' && (
                  <button
                    onClick={() => onOpen(book)}
                    style={{
                      padding: '5px 14px', background: '#1a237e', color: '#fff',
                      border: 'none', borderRadius: '6px',
                      fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    Read
                  </button>
                )}
                {(book.status === 'pending' || book.status === 'processing') && (
                  <span style={{ fontSize: '13px', color: '#f57c00' }}>⏳</span>
                )}
                {deleteConfirm === book.doc_id ? (
                  <>
                    <button
                      onClick={() => handleDelete(book.doc_id)}
                      disabled={deleting === book.doc_id}
                      style={{ padding: '4px 10px', background: '#d32f2f', color: '#fff', border: 'none', borderRadius: '5px', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                    >
                      {deleting === book.doc_id ? '…' : 'Confirm'}
                    </button>
                    <button
                      onClick={() => setDeleteConfirm(null)}
                      style={{ padding: '4px 10px', background: '#eee', color: '#444', border: '1px solid #ddd', borderRadius: '5px', fontSize: '11px', cursor: 'pointer' }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => setDeleteConfirm(book.doc_id)}
                    style={{ padding: '5px 10px', background: '#fff', color: '#d32f2f', border: '1px solid #ffcdd2', borderRadius: '6px', fontSize: '12px', cursor: 'pointer' }}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
