import { useState, useEffect, useRef } from 'react';
import { Routes, Route, NavLink, Outlet, useOutletContext, useNavigate, useLocation, Navigate } from 'react-router-dom';
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
import { ContentRequestPage } from './components/ContentRequestPage';
import { NotificationContainer } from './components/NotificationToast';
import { useNotifications } from './hooks/useNotifications';
import { useSearch } from './hooks/useSearch';
import { useReminders } from './hooks/useReminders';
import { usePreferences } from './hooks/usePreferences';
import { getToken } from './auth';
import type { UserPreferences, UserPreferencesUpdate, ChannelAction, GenreAction } from './api/settings';
import type { SearchResult, BookDocument } from './types';

type AppCtx = {
  token: string | null;
  prefs: UserPreferences;
  savePreferences: (update: UserPreferencesUpdate) => Promise<void>;
  channelAction: (channelId: string, channelName: string, action: ChannelAction) => Promise<void>;
  genreAction: (genre: string, action: GenreAction) => Promise<void>;
  recLanguage: string;
  setRecLanguage: (l: string) => void;
};

function useAppCtx() {
  return useOutletContext<AppCtx>();
}

function Layout() {
  const [token, setToken] = useState<string | null>(getToken);
  const [recLanguage, setRecLanguage] = useState(() => localStorage.getItem('recLanguage') ?? '');
  const { prefs, savePreferences, channelAction, genreAction } = usePreferences(token);
  const { notifications, dismiss: dismissNotification } = useNotifications(token);
  const { summary: reminderSummary, showBanner: showReminderBanner, dismissBanner } =
    useReminders(token, prefs.reminders_enabled);
  const navigate = useNavigate();
  const darkMode = prefs.dark_mode;

  useEffect(() => {
    document.body.style.background = darkMode ? '#121212' : '';
    return () => { document.body.style.background = ''; };
  }, [darkMode]);

  const ctx: AppCtx = { token, prefs, savePreferences, channelAction, genreAction, recLanguage, setRecLanguage };

  const nl = ({ isActive }: { isActive: boolean }) => ({
    padding: '6px 14px', borderRadius: '6px',
    border: `1px solid ${darkMode ? '#444' : '#c5cae9'}`,
    background: isActive ? (darkMode ? '#1a237e' : '#e8eaf6') : (darkMode ? '#2a2a2a' : '#fff'),
    color: isActive ? (darkMode ? '#fff' : '#1a237e') : (darkMode ? '#aaa' : '#1a237e'),
    fontSize: '13px', fontWeight: 600 as const, cursor: 'pointer', textDecoration: 'none',
    display: 'inline-block',
  });

  const nlReview = ({ isActive }: { isActive: boolean }) => ({
    ...nl({ isActive }),
    border: `1px solid ${darkMode ? '#388e3c' : '#c8e6c9'}`,
    color: darkMode ? '#66bb6a' : '#2e7d32',
    background: isActive ? (darkMode ? '#1b5e20' : '#e8f5e9') : (darkMode ? '#2a2a2a' : '#fff'),
  });

  return (
    <>
      <NotificationContainer notifications={notifications} onDismiss={dismissNotification} darkMode={darkMode} />
      <div style={{ maxWidth: '900px', margin: '0 auto', padding: '24px 16px', fontFamily: 'sans-serif', background: darkMode ? '#121212' : undefined, minHeight: '100vh', color: darkMode ? '#e0e0e0' : undefined }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <NavLink to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
            <h1 style={{ fontSize: '24px', margin: 0 }}>YouGlish Clone</h1>
          </NavLink>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            {token && <NavLink to="/for-you" style={nl}>For You</NavLink>}
            {token && <NavLink to="/playlist" style={nl}>Playlist</NavLink>}
            {token && <NavLink to="/books" style={nl}>Books</NavLink>}
            {token && <NavLink to="/review" style={nlReview}>Review</NavLink>}
            {token && <NavLink to="/add-content" style={nl}>+ Add Content</NavLink>}
            {token && <NavLink to="/settings" style={nl}>Settings</NavLink>}
            <LoginForm
              token={token}
              onLogin={t => { setToken(t); navigate('/'); }}
              onLogout={() => { setToken(null); navigate('/'); }}
            />
          </div>
        </div>

        {token && showReminderBanner && reminderSummary && (
          <ReminderBanner
            summary={reminderSummary}
            onDismiss={dismissBanner}
            onOpenRecs={() => { dismissBanner(); navigate('/for-you'); }}
          />
        )}

        <Outlet context={ctx} />
      </div>
    </>
  );
}

// ---- Pages ----

type HomeNavState = {
  recResult?: SearchResult;
  guidedTarget?: { itemId: number; itemType: string };
  showChat?: 'guided';
  searchTerm?: string;
};

function HomePage() {
  const { token, prefs } = useAppCtx();
  const { terms, query, addTerm, removeTerm, results, total, loading, error, hasMore, loadMore } = useSearch();
  const [resultIdx, setResultIdx] = useState(0);
  const [showChat, setShowChat] = useState<'free' | 'guided' | null>(null);
  const [recResult, setRecResult] = useState<SearchResult | null>(null);
  const [guidedTarget, setGuidedTarget] = useState<{ itemId: number; itemType: string } | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const processedState = useRef(false);

  useEffect(() => {
    if (processedState.current) return;
    const state = location.state as HomeNavState | null;
    if (!state) return;
    processedState.current = true;
    if (state.recResult) setRecResult(state.recResult);
    if (state.guidedTarget) setGuidedTarget(state.guidedTarget);
    if (state.showChat) setShowChat(state.showChat);
    if (state.searchTerm) addTerm(state.searchTerm);
    window.history.replaceState(null, '');
  }, []);

  useEffect(() => { setResultIdx(0); setShowChat(null); setRecResult(null); setGuidedTarget(null); }, [query]);
  useEffect(() => { setShowChat(null); }, [resultIdx]);

  const currentResult = results[resultIdx] ?? null;
  const activeResult = recResult ?? currentResult;

  const handleNext = () => {
    if (resultIdx === results.length - 1 && hasMore) loadMore();
    setResultIdx(i => Math.min(i + 1, total - 1));
  };
  const handlePrev = () => setResultIdx(i => Math.max(0, i - 1));

  const wordColors = {
    known:    { color: prefs.known_word_color },
    learning: { color: prefs.learning_word_color },
    unknown:  { color: prefs.unknown_word_color },
  };

  return (
    <>
      <SearchBar terms={terms} onAddTerm={addTerm} onRemoveTerm={removeTerm} loading={loading} />
      {error && <p style={{ color: 'red', marginTop: '12px' }}>{error}</p>}

      {loading && !currentResult && (
        <p style={{ color: '#888', marginTop: '24px', textAlign: 'center' }}>Searching…</p>
      )}
      {!loading && query && results.length === 0 && (
        <p style={{ color: '#888', marginTop: '24px', textAlign: 'center' }}>No results found.</p>
      )}

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
              <button onClick={() => setShowChat('free')} style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #c5cae9', background: '#fff', color: '#1a237e', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                Free Chat
              </button>
              <button onClick={() => setShowChat('guided')} style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #ffe082', background: '#fff', color: '#e65100', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                Guided Practice
              </button>
            </div>
          )}
          {token && showChat === 'free' && (
            <FreeChatPage result={activeResult} token={token} onClose={() => setShowChat(null)} />
          )}
          {token && showChat === 'guided' && (
            <GuidedChatPage
              result={activeResult}
              token={token}
              targetItemId={guidedTarget?.itemId}
              targetItemType={guidedTarget?.itemType}
              onClose={() => { setShowChat(null); setGuidedTarget(null); }}
              onSessionComplete={() => { setShowChat(null); setGuidedTarget(null); navigate('/for-you'); }}
            />
          )}
        </>
      )}
    </>
  );
}

function ForYouPage() {
  const { token, prefs, recLanguage, setRecLanguage, channelAction, genreAction } = useAppCtx();
  const navigate = useNavigate();
  if (!token) return <Navigate to="/" />;

  const wordColors = {
    known:    { color: prefs.known_word_color },
    learning: { color: prefs.learning_word_color },
    unknown:  { color: prefs.unknown_word_color },
  };
  const blank = (lang: string): SearchResult => ({
    video_id: '', title: '', thumbnail_url: '', language: lang,
    start_time: 0, start_time_int: 0, content: '', surface_form: null, match_type: 'recommendation',
  });

  return (
    <RecommendationsPanel
      token={token}
      language={recLanguage}
      onLanguageChange={lang => { setRecLanguage(lang); localStorage.setItem('recLanguage', lang); }}
      onWatch={result => navigate('/', { state: { recResult: result } })}
      onPractice={lang => navigate('/', { state: { recResult: blank(lang), showChat: 'guided' } })}
      onPracticeItem={(itemId, itemType, lang) => navigate('/', { state: { recResult: blank(lang), guidedTarget: { itemId, itemType }, showChat: 'guided' } })}
      onPracticeSentence={result => navigate('/', { state: { recResult: result, showChat: 'guided' } })}
      onSearch={term => navigate('/', { state: { searchTerm: term } })}
      onClose={() => navigate('/')}
      onOpenBooks={() => navigate('/books')}
      wordColors={wordColors}
      passiveMax={prefs.passive_reps_for_known}
      prefs={prefs}
      onChannelAction={channelAction}
      onGenreAction={genreAction}
    />
  );
}

function PlaylistPage() {
  const { token, recLanguage, setRecLanguage } = useAppCtx();
  const navigate = useNavigate();
  if (!token) return <Navigate to="/" />;
  return (
    <PlaylistPanel
      token={token}
      language={recLanguage}
      onLanguageChange={lang => { setRecLanguage(lang); localStorage.setItem('recLanguage', lang); }}
      onWatch={result => navigate('/', { state: { recResult: result } })}
      onClose={() => navigate('/')}
    />
  );
}

function BooksPage() {
  const { token, prefs } = useAppCtx();
  const [activeBook, setActiveBook] = useState<BookDocument | null>(null);
  const navigate = useNavigate();
  if (!token) return <Navigate to="/" />;
  if (activeBook) {
    return (
      <BookReaderPage
        token={token}
        doc={activeBook}
        onClose={() => setActiveBook(null)}
        darkMode={prefs.dark_mode}
        autoMarkKnown={prefs.auto_mark_known}
      />
    );
  }
  return (
    <BookLibraryPage
      token={token}
      onOpen={setActiveBook}
      onClose={() => navigate('/')}
      darkMode={prefs.dark_mode}
    />
  );
}

function ReviewPage() {
  const { token, recLanguage, setRecLanguage } = useAppCtx();
  const navigate = useNavigate();
  if (!token) return <Navigate to="/" />;
  return (
    <SRSReviewPage
      token={token}
      language={recLanguage}
      onLanguageChange={lang => { setRecLanguage(lang); localStorage.setItem('recLanguage', lang); }}
      onClose={() => navigate('/')}
    />
  );
}

function AddContentPage() {
  const { token, prefs } = useAppCtx();
  const navigate = useNavigate();
  if (!token) return <Navigate to="/" />;
  return <ContentRequestPage token={token} onClose={() => navigate('/')} darkMode={prefs.dark_mode} />;
}

function SettingsPage() {
  const { token, prefs, savePreferences } = useAppCtx();
  const navigate = useNavigate();
  if (!token) return <Navigate to="/" />;
  return <SettingsPanel prefs={prefs} onSave={savePreferences} onClose={() => navigate('/')} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="for-you" element={<ForYouPage />} />
        <Route path="playlist" element={<PlaylistPage />} />
        <Route path="books" element={<BooksPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="add-content" element={<AddContentPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
