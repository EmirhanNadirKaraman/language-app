import { forwardRef, useEffect, useRef, useImperativeHandle } from 'react';

export interface YoutubeEmbedHandle {
  seekTo: (seconds: number) => void;
  getCurrentTime: () => number;
  pauseVideo: () => void;
}

interface Props {
  videoId: string;
  startTime: number;
  autoplay?: boolean;
}

// Minimal YT IFrame API types
interface YTPlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  getCurrentTime(): number;
  pauseVideo(): void;
  loadVideoById(opts: { videoId: string; startSeconds?: number }): void;
  cueVideoById(opts: { videoId: string; startSeconds?: number }): void;
  destroy(): void;
}
declare global {
  interface Window {
    YT: { Player: new (el: HTMLElement, opts: object) => YTPlayer };
    onYouTubeIframeAPIReady?: () => void;
  }
}

// Load the script once for the entire app lifetime
let apiPromise: Promise<void> | null = null;
function loadYTApi(): Promise<void> {
  if (apiPromise) return apiPromise;
  apiPromise = new Promise(resolve => {
    if (window.YT?.Player) { resolve(); return; }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { prev?.(); resolve(); };
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(tag);
  });
  return apiPromise;
}

export const YoutubeEmbed = forwardRef<YoutubeEmbedHandle, Props>(
  ({ videoId, startTime, autoplay = false }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<YTPlayer | null>(null);
    const readyRef = useRef(false);
    // Track videoId seen at creation so the change effect can skip the first render
    const prevVideoIdRef = useRef(videoId);

    useImperativeHandle(ref, () => ({
      seekTo: (seconds) => playerRef.current?.seekTo(seconds, true),
      getCurrentTime: () => typeof playerRef.current?.getCurrentTime === 'function'
        ? playerRef.current.getCurrentTime()
        : 0,
      pauseVideo: () => playerRef.current?.pauseVideo(),
    }));

    // Create player on mount, destroy on unmount
    useEffect(() => {
      let cancelled = false;
      loadYTApi().then(() => {
        if (cancelled || !containerRef.current) return;
        playerRef.current = new window.YT.Player(containerRef.current, {
          videoId,
          playerVars: { start: Math.floor(startTime), autoplay: autoplay ? 1 : 0, rel: 0, modestbranding: 1 },
          events: { onReady: () => { readyRef.current = true; } },
        });
      });
      return () => {
        cancelled = true;
        playerRef.current?.destroy();
        playerRef.current = null;
        readyRef.current = false;
      };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // React to videoId changes after initial mount — no iframe reload needed
    useEffect(() => {
      if (prevVideoIdRef.current === videoId) return;
      prevVideoIdRef.current = videoId;
      if (!readyRef.current || !playerRef.current) return;
      const method = autoplay ? 'loadVideoById' : 'cueVideoById';
      playerRef.current[method]({ videoId, startSeconds: Math.floor(startTime) });
    }, [videoId, startTime, autoplay]);

    return (
      // Modern responsive 16:9 container. `aspectRatio` is supported on all
      // modern browsers including iOS Safari 14.5+. The container grows to its
      // parent's width — on mobile that's the full PlayerView width; on desktop
      // it's capped by the 900px Layout maxWidth.
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '16 / 9',
          background: '#000',
        }}
      >
        <div
          ref={containerRef}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
        />
      </div>
    );
  }
);
