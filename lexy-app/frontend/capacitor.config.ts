import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor configuration.
 *
 * - appId is a PLACEHOLDER — change to the registered bundle ID before
 *   App Store submission. The Apple convention is reverse-DNS of a domain
 *   you actually own (e.g. com.yourcompany.lexy).
 * - webDir points at the Vite build output; `npx cap sync ios` copies
 *   the contents of dist/ into ios/App/App/public/ on every run.
 * - server.url is intentionally NOT set for production. If a future
 *   live-reload dev workflow is desired, override via a separate config
 *   file or env var so the production wrap never accidentally points at
 *   localhost.
 * - VITE_API_BASE_URL (build-time, .env.production) is the mechanism that
 *   makes API calls reach the hosted backend from inside the WebView —
 *   capacitor.config does not need to know the backend URL.
 *
 * See docs/CAPACITOR_READINESS.md §§5, 9 for the full setup + CORS rules.
 */
const config: CapacitorConfig = {
  appId: 'com.lexy.learning',
  appName: 'Lexy',
  webDir: 'dist',
};

export default config;
