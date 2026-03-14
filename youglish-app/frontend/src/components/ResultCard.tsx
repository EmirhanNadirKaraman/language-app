import { useState } from 'react';
import type { SearchResult, VideoSentence } from '../types';
import { YoutubeEmbed } from './YoutubeEmbed';
import { fetchVideoSentences } from '../api/search';

interface Props {
  result: SearchResult;
  query: string;
  language: string | null;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function highlightText(text: string, terms: string[]): React.ReactNode {
  if (!terms.length) return text;
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = escaped.join('|');
  const parts = text.split(new RegExp(`(${pattern})`, 'gi'));
  return parts.map((part, i) =>
    terms.some(t => part.toLowerCase() === t.toLowerCase())
      ? <mark key={i} style={{ background: '#fff176', padding: 0 }}>{part}</mark>
      : part
  );
}

export function ResultCard({ result, query, language }: Props) {
  const [playing, setPlaying] = useState(false);
  const [sentences, setSentences] = useState<VideoSentence[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);

  const highlightTerms = result.surface_form
    ? [result.surface_form]
    : query.split(' ').filter(t => t.length > 0);

  const current = sentences[currentIdx];
  const displayContent = current?.content ?? result.content;
  const displayStartTime = current?.start_time_int ?? result.start_time_int;

  const handlePlay = async () => {
    setPlaying(true);
    try {
      const data = await fetchVideoSentences(result.video_id, query, language);
      setSentences(data);
      const idx = data.findIndex(s => s.start_time_int === result.start_time_int);
      setCurrentIdx(idx >= 0 ? idx : 0);
    } catch {
      // Keep playing without navigation if fetch fails
    }
  };

  const canPrev = currentIdx > 0;
  const canNext = currentIdx < sentences.length - 1;

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: '8px', overflow: 'hidden', background: '#fff' }}>
      {playing ? (
        <YoutubeEmbed key={displayStartTime} videoId={result.video_id} startTime={displayStartTime} autoplay />
      ) : (
        <div
          style={{ position: 'relative', paddingTop: '56.25%', cursor: 'pointer', background: '#000' }}
          onClick={handlePlay}
        >
          <img
            src={result.thumbnail_url}
            alt={result.title}
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.85 }}
          />
          <div style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            width: '60px', height: '60px', background: 'rgba(255,0,0,0.85)', borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <span style={{ color: '#fff', fontSize: '24px', marginLeft: '4px' }}>▶</span>
          </div>
          <div style={{
            position: 'absolute', bottom: '8px', right: '8px',
            background: 'rgba(0,0,0,0.75)', color: '#fff', padding: '2px 6px',
            borderRadius: '4px', fontSize: '13px',
          }}>
            {formatTime(result.start_time)}
          </div>
        </div>
      )}

      {/* Big subtitle */}
      <p style={{
        margin: 0,
        padding: '16px 20px',
        fontSize: '22px',
        fontWeight: 500,
        lineHeight: 1.5,
        textAlign: 'center',
        color: '#111',
        minHeight: '64px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {highlightText(displayContent, highlightTerms)}
      </p>

      {/* Navigation */}
      {playing && sentences.length > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', padding: '0 16px 12px' }}>
          <button
            onClick={() => setCurrentIdx(i => i - 1)}
            disabled={!canPrev}
            style={{ padding: '6px 14px', fontSize: '16px', cursor: canPrev ? 'pointer' : 'default', opacity: canPrev ? 1 : 0.3, border: '1px solid #ccc', borderRadius: '4px', background: '#fff' }}
          >←</button>
          <span style={{ fontSize: '13px', color: '#666', minWidth: '60px', textAlign: 'center' }}>
            {currentIdx + 1} / {sentences.length}
          </span>
          <button
            onClick={() => setCurrentIdx(i => i + 1)}
            disabled={!canNext}
            style={{ padding: '6px 14px', fontSize: '16px', cursor: canNext ? 'pointer' : 'default', opacity: canNext ? 1 : 0.3, border: '1px solid #ccc', borderRadius: '4px', background: '#fff' }}
          >→</button>
        </div>
      )}

      {/* Footer */}
      <div style={{ padding: '8px 12px 12px', borderTop: '1px solid #f0f0f0' }}>
        <div style={{ fontWeight: 600, fontSize: '13px', color: '#333', marginBottom: '4px' }}>
          {result.title}
          <span style={{ marginLeft: '8px', fontSize: '11px', background: '#eee', padding: '2px 6px', borderRadius: '4px', fontWeight: 400 }}>
            {result.language}
          </span>
        </div>
        <a
          href={`https://youtu.be/${result.video_id}?t=${displayStartTime}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: '12px', color: '#1a73e8' }}
        >
          Open on YouTube at {formatTime(displayStartTime)} ↗
        </a>
      </div>
    </div>
  );
}
