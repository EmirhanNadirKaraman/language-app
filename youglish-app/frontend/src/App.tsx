import { useState, useEffect } from 'react';
import { SearchBar } from './components/SearchBar';
import { PlayerView } from './components/PlayerView';
import { useSearch } from './hooks/useSearch';

export default function App() {
  const { terms, query, addTerm, removeTerm, language, setLanguage, results, total, loading, error, hasMore, loadMore } = useSearch();
  const [resultIdx, setResultIdx] = useState(0);

  // Reset to first result on new search
  useEffect(() => { setResultIdx(0); }, [query, language]);

  const currentResult = results[resultIdx] ?? null;

  const handleNext = () => {
    if (resultIdx === results.length - 1 && hasMore) loadMore();
    setResultIdx(i => Math.min(i + 1, total - 1));
  };

  const handlePrev = () => setResultIdx(i => Math.max(0, i - 1));

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', padding: '24px 16px', fontFamily: 'sans-serif' }}>
      <h1 style={{ fontSize: '24px', marginBottom: '20px' }}>YouGlish Clone</h1>

      <SearchBar
        terms={terms}
        onAddTerm={addTerm}
        onRemoveTerm={removeTerm}
        language={language}
        onLanguageChange={setLanguage}
        loading={loading}
      />

      {error && <p style={{ color: 'red', marginTop: '12px' }}>{error}</p>}

      {query && currentResult && (
        <>
          <p style={{ margin: '20px 0 14px', fontSize: '22px', lineHeight: 1.4, color: '#1a237e' }}>
            Aussprache von{' '}
            <strong style={{ color: '#c0392b' }}>{query}</strong>{' '}
            in {currentResult.language}{' '}
            <span style={{ color: '#666', fontSize: '18px' }}>({resultIdx + 1} von {total}):</span>
          </p>

          <PlayerView
            result={currentResult}
            query={query}
            canPrev={resultIdx > 0}
            canNext={resultIdx < total - 1}
            onPrev={handlePrev}
            onNext={handleNext}
          />
        </>
      )}

      {loading && !currentResult && (
        <p style={{ color: '#888', marginTop: '24px', textAlign: 'center' }}>Searching…</p>
      )}

      {!loading && query && results.length === 0 && (
        <p style={{ color: '#888', marginTop: '24px', textAlign: 'center' }}>No results found.</p>
      )}
    </div>
  );
}
