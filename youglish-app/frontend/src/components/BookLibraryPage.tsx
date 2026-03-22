import { useState, useEffect, useRef } from 'react';
import { listBooks, uploadBook, getBook } from '../api/books';
import type { BookDocument } from '../types';

interface Props {
  token: string;
  onOpen: (doc: BookDocument) => void;
  onClose: () => void;
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

export function BookLibraryPage({ token, onOpen, onClose }: Props) {
  const [books, setBooks]       = useState<BookDocument[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [title, setTitle]       = useState('');
  const [language, setLanguage] = useState('de');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Poll for processing books
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    async function refresh() {
      try {
        const data = await listBooks(token);
        setBooks(data);
        setLoading(false);

        const processing = data.filter(b => b.status === 'pending' || b.status === 'processing');
        if (processing.length > 0) {
          timer = setTimeout(refresh, 3000);
        }
      } catch (e) {
        setError((e as Error).message);
        setLoading(false);
      }
    }

    refresh();
    return () => clearTimeout(timer);
  }, [token]);

  // Re-poll a single book when its status changes to processing
  async function pollSingle(docId: string) {
    let attempts = 0;
    const max = 120; // ~6 min at 3s interval
    async function tick() {
      if (attempts++ >= max) return;
      const doc = await getBook(token, docId);
      setBooks(prev => prev.map(b => b.doc_id === docId ? doc : b));
      if (doc.status === 'pending' || doc.status === 'processing') {
        setTimeout(tick, 3000);
      }
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

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: '#fff', borderRadius: '10px',
        width: '640px', maxWidth: '95vw', maxHeight: '90vh',
        display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '16px 20px', borderBottom: '1px solid #eee',
        }}>
          <h2 style={{ margin: 0, fontSize: '18px', color: '#1a237e' }}>My Books</h2>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#666' }}
          >
            ✕
          </button>
        </div>

        {/* Upload form */}
        <form onSubmit={handleUpload} style={{ padding: '16px 20px', borderBottom: '1px solid #eee' }}>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 220px' }}>
              <label style={{ fontSize: '12px', color: '#555', display: 'block', marginBottom: '4px' }}>
                PDF file
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
                style={{ fontSize: '13px', width: '100%' }}
              />
            </div>
            <div style={{ flex: '1 1 160px' }}>
              <label style={{ fontSize: '12px', color: '#555', display: 'block', marginBottom: '4px' }}>
                Title
              </label>
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="Book title"
                style={{
                  width: '100%', padding: '6px 8px', border: '1px solid #ccc',
                  borderRadius: '5px', fontSize: '13px', boxSizing: 'border-box',
                }}
              />
            </div>
            <div style={{ flex: '0 0 80px' }}>
              <label style={{ fontSize: '12px', color: '#555', display: 'block', marginBottom: '4px' }}>
                Language
              </label>
              <select
                value={language}
                onChange={e => setLanguage(e.target.value)}
                style={{
                  width: '100%', padding: '6px 8px', border: '1px solid #ccc',
                  borderRadius: '5px', fontSize: '13px',
                }}
              >
                <option value="de">DE</option>
                <option value="en">EN</option>
                <option value="fr">FR</option>
                <option value="es">ES</option>
                <option value="it">IT</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={!selectedFile || uploading}
              style={{
                padding: '6px 16px', background: '#1a237e', color: '#fff',
                border: 'none', borderRadius: '5px', fontSize: '13px',
                cursor: selectedFile && !uploading ? 'pointer' : 'not-allowed',
                opacity: selectedFile && !uploading ? 1 : 0.5,
                whiteSpace: 'nowrap',
              }}
            >
              {uploading ? 'Uploading…' : 'Upload'}
            </button>
          </div>
          {uploadError && (
            <p style={{ color: '#d32f2f', fontSize: '12px', margin: '6px 0 0' }}>{uploadError}</p>
          )}
        </form>

        {/* Book list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px' }}>
          {loading && (
            <p style={{ color: '#888', textAlign: 'center', marginTop: '24px' }}>Loading…</p>
          )}
          {error && (
            <p style={{ color: '#d32f2f', textAlign: 'center', marginTop: '24px' }}>{error}</p>
          )}
          {!loading && !error && books.length === 0 && (
            <p style={{ color: '#888', textAlign: 'center', marginTop: '24px' }}>
              No books yet. Upload a PDF to get started.
            </p>
          )}
          {books.map(book => (
            <div
              key={book.doc_id}
              style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '10px 0', borderBottom: '1px solid #f0f0f0',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: '14px', color: '#222', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {book.title}
                </div>
                <div style={{ fontSize: '12px', color: '#888', marginTop: '2px' }}>
                  {book.filename}
                  {book.total_pages != null && ` · ${book.total_pages} pages`}
                  {' · '}
                  {book.language.toUpperCase()}
                  {' · '}
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
              {book.status === 'ready' && (
                <button
                  onClick={() => onOpen(book)}
                  style={{
                    padding: '5px 14px', background: '#e8eaf6', color: '#1a237e',
                    border: '1px solid #c5cae9', borderRadius: '5px',
                    fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  Read
                </button>
              )}
              {(book.status === 'pending' || book.status === 'processing') && (
                <span style={{ fontSize: '12px', color: '#f57c00' }}>⏳</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
