import { useState, useEffect } from 'react';
import { SearchBar } from './components/SearchBar';
import { PlayerView } from './components/PlayerView';
import { LoginForm } from './components/LoginForm';
import { FreeChatPage } from './components/FreeChatPage';
import { GuidedChatPage } from './components/GuidedChatPage';
import { SettingsPanel } from './components/SettingsPanel';
import { RecommendationsPanel } from './components/RecommendationsPanel';
import { PlaylistPanel } from './components/PlaylistPanel';
import { BookLibraryPage } from './components/BookLibraryPage';
import { BookReaderPage } from './components/BookReaderPage';
import { ReminderBanner } from './components/ReminderBanner';
import { SRSReviewPage } from './components/SRSReviewPage';
import { useSearch } from './hooks/useSearch';
import { useReminders } from './hooks/useReminders';
import { usePreferences } from './hooks/usePreferences';
import { getToken } from './auth';
import type { SearchResult, BookDocument } from './types';

export default function App() {
  const { terms, query, addTerm, removeTerm, results, total, loading, error, hasMore, loadMore } = useSearch();
  const [resultIdx, setResultIdx] = useState(0);
  const [token, setToken] = useState<string | null>(getToken);
  const [showChat, setShowChat] = useState<'free' | 'guided' | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showRecs, setShowRecs] = useState(false);
  const [showPlaylist, setShowPlaylist] = useState(false);
  const [showBooks, setShowBooks]       = useState(false);
  const [showReview, setShowReview]     = useState(false);
  const [activeBook, setActiveBook]     = useState<BookDocument | null>(null);
  const [recLanguage, setRecLanguage] = useState<string>(
    () => localStorage.getItem('recLanguage') ?? '',
  );
  const [recResult, setRecResult] = useState<SearchResult | null>(null);
  const [guidedTarget, setGuidedTarget] = useState<{ itemId: number; itemType: string } | null>(null);

  const { prefs, savePreferences, channelAction, genreAction } = usePreferences(token);
  const { summary: reminderSummary, showBanner: showReminderBanner, dismissBanner } =
    useReminders(token, prefs.reminders_enabled);
  const wordColors = {
    known:    { color: prefs.known_word_color },
    learning: { color: prefs.learning_word_color },
    unknown:  { color: prefs.unknown_word_color },
  };

  // Reset to first result on new search; close chat when result changes
  useEffect(() => { setResultIdx(0); setShowChat(null); setRecResult(null); setGuidedTarget(null); }, [query]);
  useEffect(() => { setShowChat(null); }, [resultIdx]);

  const currentResult = results[resultIdx] ?? null;
  // Recommended result takes priority over search result for the player
  const activeResult = recResult ?? currentResult;

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
              onClick={() => { setShowRecs(s => !s); setShowSettings(false); setShowPlaylist(false); setShowBooks(false); setShowReview(false); }}
              style={{
                padding: '6px 14px', borderRadius: '6px',
                border: '1px solid #c5cae9', background: showRecs ? '#e8eaf6' : '#fff',
                color: '#1a237e', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}
            >
              For You
            </button>
          )}
          {token && (
            <button
              onClick={() => { setShowPlaylist(s => !s); setShowSettings(false); setShowRecs(false); setShowBooks(false); setShowReview(false); }}
              style={{
                padding: '6px 14px', borderRadius: '6px',
                border: '1px solid #c5cae9', background: showPlaylist ? '#e8eaf6' : '#fff',
                color: '#1a237e', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}
            >
              Playlist
            </button>
          )}
          {token && (
            <button
              onClick={() => { setShowBooks(s => !s); setShowSettings(false); setShowRecs(false); setShowPlaylist(false); setShowReview(false); }}
              style={{
                padding: '6px 14px', borderRadius: '6px',
                border: '1px solid #c5cae9', background: showBooks ? '#e8eaf6' : '#fff',
                color: '#1a237e', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}
            >
              Books
            </button>
          )}
          {token && (
            <button
              onClick={() => { setShowReview(s => !s); setShowSettings(false); setShowRecs(false); setShowPlaylist(false); setShowBooks(false); }}
              style={{
                padding: '6px 14px', borderRadius: '6px',
                border: '1px solid #c8e6c9', background: showReview ? '#e8f5e9' : '#fff',
                color: '#2e7d32', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              }}
            >
              Review
            </button>
          )}
          {token && (
            <button
              onClick={() => { setShowSettings(s => !s); setShowRecs(false); setShowPlaylist(false); setShowBooks(false); setShowReview(false); }}
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
            onLogin={newToken => { setToken(newToken); setShowSettings(false); setShowRecs(false); setShowPlaylist(false); setShowBooks(false); setShowReview(false); }}
            onLogout={() => { setToken(null); setShowSettings(false); setShowRecs(false); setShowPlaylist(false); setShowBooks(false); setShowReview(false); setActiveBook(null); setRecResult(null); }}
          />
        </div>
      </div>

      {token && showReminderBanner && reminderSummary && (
        <ReminderBanner
          summary={reminderSummary}
          onDismiss={dismissBanner}
          onOpenRecs={() => {
            dismissBanner();
            setShowRecs(true);
            setShowSettings(false);
            setShowPlaylist(false);
            setShowBooks(false);
            setShowReview(false);
          }}
        />
      )}

      {token && showSettings && (
        <SettingsPanel
          prefs={prefs}
          onSave={savePreferences}
          onClose={() => setShowSettings(false)}
        />
      )}

      {token && showReview && (
        <SRSReviewPage
          token={token}
          language={recLanguage}
          onLanguageChange={(lang) => {
            setRecLanguage(lang);
            localStorage.setItem('recLanguage', lang);
          }}
          onClose={() => setShowReview(false)}
        />
      )}

      {token && showPlaylist && (
        <PlaylistPanel
          token={token}
          language={recLanguage}
          onLanguageChange={(lang) => {
            setRecLanguage(lang);
            localStorage.setItem('recLanguage', lang);
          }}
          onWatch={(result) => {
            setRecResult(result);
            setShowPlaylist(false);
            setShowChat(null);
          }}
          onClose={() => setShowPlaylist(false)}
        />
      )}

      {token && showRecs && (
        <RecommendationsPanel
          token={token}
          language={recLanguage}
          onLanguageChange={(lang) => {
            setRecLanguage(lang);
            localStorage.setItem('recLanguage', lang);
          }}
          onWatch={(result) => {
            setRecResult(result);
            setShowRecs(false);
            setShowChat(null);
          }}
          onPractice={(lang) => {
            setGuidedTarget(null);
            setRecResult({
              video_id: '', title: '', thumbnail_url: '',
              language: lang, start_time: 0, start_time_int: 0,
              content: '', surface_form: null, match_type: 'recommendation',
            });
            setShowRecs(false);
            setShowChat('guided');
          }}
          onPracticeItem={(itemId, itemType, lang) => {
            setGuidedTarget({ itemId, itemType });
            setRecResult({
              video_id: '', title: '', thumbnail_url: '',
              language: lang, start_time: 0, start_time_int: 0,
              content: '', surface_form: null, match_type: 'recommendation',
            });
            setShowRecs(false);
            setShowChat('guided');
          }}
          onPracticeSentence={(result) => {
            setGuidedTarget(null);
            setRecResult(result);
            setShowRecs(false);
            setShowChat('guided');
          }}
          onSearch={(term) => { addTerm(term); setShowRecs(false); }}
          onClose={() => setShowRecs(false)}
          onOpenBooks={() => { setShowBooks(true); setShowRecs(false); setShowSettings(false); setShowPlaylist(false); setShowReview(false); }}
          wordColors={wordColors}
          passiveMax={prefs.passive_reps_for_known}
          prefs={prefs}
          onChannelAction={channelAction}
          onGenreAction={genreAction}
        />
      )}

      {token && showBooks && !activeBook && (
        <BookLibraryPage
          token={token}
          onOpen={(doc) => { setActiveBook(doc); setShowBooks(false); }}
          onClose={() => setShowBooks(false)}
        />
      )}

      {token && activeBook && (
        <BookReaderPage
          token={token}
          doc={activeBook}
          onClose={() => setActiveBook(null)}
        />
      )}

      <SearchBar
        terms={terms}
        onAddTerm={addTerm}
        onRemoveTerm={removeTerm}
        loading={loading}
      />

      {error && <p style={{ color: 'red', marginTop: '12px' }}>{error}</p>}

      {activeResult && (
        <>
          {query && currentResult && !recResult && (
            <p style={{ margin: '20px 0 14px', fontSize: '22px', lineHeight: 1.4, color: '#1a237e' }}>
              Aussprache von{' '}
              <strong style={{ color: '#c0392b' }}>{query}</strong>{' '}
              in {currentResult.language}{' '}
              <span style={{ color: '#666', fontSize: '18px' }}>({resultIdx + 1} von {total}):</span>
            </p>
          )}

          <PlayerView
            result={activeResult}
            query={query}
            token={token}
            canPrev={!recResult && resultIdx > 0}
            canNext={!recResult && resultIdx < total - 1}
            onPrev={handlePrev}
            onNext={handleNext}
            wordColors={wordColors}
            passiveMax={prefs.passive_reps_for_known}
            activeMax={prefs.active_reps_for_known}
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
              result={activeResult}
              token={token}
              onClose={() => setShowChat(null)}
            />
          )}

          {token && showChat === 'guided' && (
            <GuidedChatPage
              result={activeResult}
              token={token}
              targetItemId={guidedTarget?.itemId}
              targetItemType={guidedTarget?.itemType}
              onClose={() => { setShowChat(null); setGuidedTarget(null); }}
              onSessionComplete={() => {
                setShowChat(null);
                setGuidedTarget(null);
                setShowRecs(true);
              }}
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
