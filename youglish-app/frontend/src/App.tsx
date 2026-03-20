import { useState, useEffect } from 'react';
import { SearchBar } from './components/SearchBar';
import { PlayerView } from './components/PlayerView';
import { LoginForm } from './components/LoginForm';
import { FreeChatPage } from './components/FreeChatPage';
import { GuidedChatPage } from './components/GuidedChatPage';
import { SettingsPanel } from './components/SettingsPanel';
import { useSearch } from './hooks/useSearch';
import { usePreferences } from './hooks/usePreferences';
import { getToken } from './auth';

export default function App() {
  const { terms, query, addTerm, removeTerm, results, total, loading, error, hasMore, loadMore } = useSearch();
  const [resultIdx, setResultIdx] = useState(0);
  const [token, setToken] = useState<string | null>(getToken);
  const [showChat, setShowChat] = useState<'free' | 'guided' | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const { prefs, savePreferences } = usePreferences(token);
  const wordColors = {
    known:    { color: prefs.known_word_color },
    learning: { color: prefs.learning_word_color },
    unknown:  { color: prefs.unknown_word_color },
  };

  // Reset to first result on new search; close chat when result changes
  useEffect(() => { setResultIdx(0); setShowChat(null); }, [query]);
  useEffect(() => { setShowChat(null); }, [resultIdx]);

  const currentResult = results[resultIdx] ?? null;

  const handleNext = () => {
    if (resultIdx === results.length - 1 && hasMore) loadMore();
    setResultIdx(i => Math.min(i + 1, total - 1));
  };

  const handlePrev = () => setResultIdx(i => Math.max(0, i - 1));

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', padding: '24px 16px', fontFamily: 'sans-serif' }}>

      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '10px' }}>
        <h1 style={{ fontSize: '24px', margin: 0 }}>YouGlish Clone</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {token && (
            <button
              onClick={() => setShowSettings(s => !s)}
              style={{
                padding: '6px 14px', borderRadius: '6px',
                border: '1px solid #c5cae9', background: showSettings ? '#e8eaf6' : '#fff',
                color: '#1a237e', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}
            >
              Settings
            </button>
          )}
          <LoginForm
            token={token}
            onLogin={newToken => { setToken(newToken); setShowSettings(false); }}
            onLogout={() => { setToken(null); setShowSettings(false); }}
          />
        </div>
      </div>

      {token && showSettings && (
        <SettingsPanel
          prefs={prefs}
          onSave={savePreferences}
          onClose={() => setShowSettings(false)}
        />
      )}

      <SearchBar
        terms={terms}
        onAddTerm={addTerm}
        onRemoveTerm={removeTerm}
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
            token={token}
            canPrev={resultIdx > 0}
            canNext={resultIdx < total - 1}
            onPrev={handlePrev}
            onNext={handleNext}
            wordColors={wordColors}
          />

          {token && !showChat && (
            <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
              <button
                onClick={() => setShowChat('free')}
                style={{
                  padding: '8px 20px', borderRadius: '6px',
                  border: '1px solid #c5cae9', background: '#fff',
                  color: '#1a237e', fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                }}
              >
                Free Chat
              </button>
              <button
                onClick={() => setShowChat('guided')}
                style={{
                  padding: '8px 20px', borderRadius: '6px',
                  border: '1px solid #ffe082', background: '#fff',
                  color: '#e65100', fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                }}
              >
                Guided Practice
              </button>
            </div>
          )}

          {token && showChat === 'free' && (
            <FreeChatPage
              result={currentResult}
              token={token}
              onClose={() => setShowChat(null)}
            />
          )}

          {token && showChat === 'guided' && (
            <GuidedChatPage
              result={currentResult}
              token={token}
              onClose={() => setShowChat(null)}
            />
          )}
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
