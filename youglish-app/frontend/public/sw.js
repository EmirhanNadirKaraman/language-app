/**
 * Conservative PWA shell service worker — v1.
 *
 * Strategy:
 *   - Precache app shell (index.html, manifest, favicon, offline.html) on install.
 *   - Navigation requests: network-first; fall back to cached index.html (SPA
 *     shell) or offline.html if shell itself is unavailable.
 *   - Hashed Vite assets (/assets/*): cache-first (filenames are content-hashed
 *     by Vite, so cached entries can never collide with a future build).
 *   - API requests (/api/*): bypass the worker entirely. Never cache, never
 *     intercept. Specifically protects SSE (/api/v1/notifications/stream) from
 *     being buffered by the worker, and keeps auth POSTs out of the cache.
 *   - Cross-origin requests (YouTube embeds, etc): bypass entirely.
 *   - Non-GET requests: bypass entirely.
 *   - Auth/session: token + email live in localStorage, untouched by the SW.
 *
 * Update strategy: skipWaiting + clients.claim. Small frontend, no long-lived
 * in-page state that would break on controller swap. Bump CACHE_VERSION below
 * to invalidate old caches when the strategy shape changes.
 */
const CACHE_VERSION = 'v1';
const SHELL_CACHE = `youglish-shell-${CACHE_VERSION}`;
const ASSET_CACHE = `youglish-assets-${CACHE_VERSION}`;

const SHELL_PATHS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.svg',
  '/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Best-effort precache: a single missing path shouldn't fail install.
      await Promise.all(
        SHELL_PATHS.map((path) =>
          cache.add(path).catch(() => { /* ignore — runtime fetch will fill it */ })
        )
      );
      await self.skipWaiting();
    })()
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== ASSET_CACHE)
          .map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Bypass non-GET (POST /api/v1/auth/login, PUT, PATCH, DELETE).
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Bypass cross-origin (YouTube iframe, external CDNs).
  if (url.origin !== self.location.origin) return;

  // Bypass /api/* — let network handle. Critical for SSE and uncached LLM calls.
  if (url.pathname.startsWith('/api/')) return;

  // Navigation: network-first, fall back to cached shell then offline page.
  if (req.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          return await fetch(req);
        } catch {
          const shell = await caches.match('/index.html');
          if (shell) return shell;
          const offline = await caches.match('/offline.html');
          if (offline) return offline;
          // Last-resort minimal response so the browser shows something.
          return new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
        }
      })()
    );
    return;
  }

  // Hashed Vite assets — cache-first (immutable filenames).
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        try {
          const res = await fetch(req);
          if (res.ok) {
            const clone = res.clone();
            const cache = await caches.open(ASSET_CACHE);
            cache.put(req, clone).catch(() => { /* quota — ignore */ });
          }
          return res;
        } catch {
          // Asset miss while offline: surface a 504 so the page can degrade.
          return new Response('', { status: 504 });
        }
      })()
    );
    return;
  }

  // Static files in public/ (favicon, manifest, offline.html) — cache-first.
  event.respondWith(
    (async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      try {
        return await fetch(req);
      } catch {
        return new Response('', { status: 504 });
      }
    })()
  );
});
