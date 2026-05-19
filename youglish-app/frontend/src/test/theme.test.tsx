/**
 * #20 — Theme system regression guards.
 *
 * Verifies:
 *   - Representative components use var(--color-*) instead of hardcoded dark
 *     ternaries.
 *   - The SettingsPanel dark-mode toggle flips
 *     `document.documentElement.dataset.theme` immediately (no save round-trip).
 *
 * The CSS-variable declarations themselves live in `src/index.css`; jsdom does
 * not compute CSS, so we assert the literal `var(...)` value on component
 * inline styles rather than the resolved color.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { NotificationContainer } from '../components/NotificationToast';
import { ContentRequestPage } from '../components/ContentRequestPage';
import * as contentRequestsApi from '../api/contentRequests';

describe('Components use CSS variables (#20)', () => {
    it('NotificationToast dismiss button uses var(--color-text-muted)', () => {
        const onDismiss = vi.fn();
        render(
            <NotificationContainer
                notifications={[{
                    id: 'n1',
                    type: 'video_done',
                    payload: { title: 'Test', videos_added: 1 },
                }]}
                onDismiss={onDismiss}
            />,
        );
        const dismiss = screen.getByTestId('notification-dismiss') as HTMLElement;
        // jsdom returns the literal var() expression.
        expect(dismiss.style.color).toContain('var(--color-text-muted)');
    });

    it('ContentRequestPage container uses var(--color-surface) / var(--color-text)', () => {
        vi.spyOn(contentRequestsApi, 'listContentRequests').mockResolvedValue([]);
        const { container } = render(<ContentRequestPage token="t" onClose={() => {}} />);
        const panel = container.firstElementChild as HTMLElement;
        expect(panel.style.background).toContain('var(--color-surface)');
        expect(panel.style.color).toContain('var(--color-text)');
        vi.restoreAllMocks();
    });

    it('ContentRequestPage input uses var(--color-input-bg) + var(--color-input-border)', () => {
        vi.spyOn(contentRequestsApi, 'listContentRequests').mockResolvedValue([]);
        render(<ContentRequestPage token="t" onClose={() => {}} />);
        const input = screen.getByTestId('content-request-input') as HTMLInputElement;
        expect(input.style.background).toContain('var(--color-input-bg)');
        // jsdom normalises shorthand `border: 1px solid var(--x)` into `borderColor` etc;
        // either path contains the var reference.
        const borderText = `${input.style.borderColor} ${input.style.border}`;
        expect(borderText).toContain('var(--color-input-border)');
        vi.restoreAllMocks();
    });

    // #20b — newly converted components.
    it('PlayerControls button uses var(--color-surface) + var(--color-input-border)', async () => {
        const { PlayerControls } = await import('../components/PlayerControls');
        const { container } = render(
            <PlayerControls
                onPrevVideo={() => {}}
                onPrevMatch={() => {}}
                onReplay={() => {}}
                onNextMatch={() => {}}
                onNextVideo={() => {}}
                disablePrevVideo={false}
                disablePrevMatch={false}
                disableNextMatch={false}
                disableNextVideo={false}
                sentenceIdx={0}
                sentenceCount={1}
            />,
        );
        const btn = container.querySelector('button') as HTMLElement;
        expect(btn.style.background).toContain('var(--color-surface)');
        const borderText = `${btn.style.borderColor} ${btn.style.border}`;
        expect(borderText).toContain('var(--color-input-border)');
    });

    it('LoginForm primary submit uses var(--color-primary)', async () => {
        const { LoginForm } = await import('../components/LoginForm');
        render(<LoginForm token={null} onLogin={() => {}} onLogout={() => {}} />);
        // Open the inline form.
        fireEvent.click(screen.getByTestId('login-signin-toggle'));
        const submit = screen.getByTestId('login-submit') as HTMLElement;
        expect(submit.style.background).toContain('var(--color-primary)');
        expect(submit.style.color).toContain('var(--color-primary-text)');
    });

    it('MessageInput textarea uses var(--color-input-bg) + var(--color-text)', async () => {
        const { MessageInput } = await import('../components/MessageInput');
        render(<MessageInput onSend={() => {}} disabled={false} />);
        const ta = screen.getByTestId('chat-input') as HTMLTextAreaElement;
        expect(ta.style.background).toContain('var(--color-input-bg)');
        expect(ta.style.color).toContain('var(--color-text)');
    });

    it('ReminderBanner background uses var(--color-warning-bg)', async () => {
        const { ReminderBanner } = await import('../components/ReminderBanner');
        const { container } = render(
            <ReminderBanner
                summary={{
                    srs_due_count: 1, reading_due_count: 0,
                    learning_item_count: 1, total_due: 1, has_anything_due: true,
                }}
                onDismiss={() => {}}
                onOpenRecs={() => {}}
            />,
        );
        const banner = container.firstElementChild as HTMLElement;
        expect(banner.style.background).toContain('var(--color-warning-bg)');
    });
});

describe('Theme attribute (#20)', () => {
    it('SettingsPanel dark-mode toggle flips document.documentElement.dataset.theme', async () => {
        // Inline import to avoid pulling in SettingsPanel's network deps at top level.
        const { SettingsPanel } = await import('../components/SettingsPanel');
        const { PREFERENCE_DEFAULTS } = await import('../api/settings');
        const searchApi = await import('../api/search');
        vi.spyOn(searchApi, 'fetchCategories').mockResolvedValue([]);

        // Force a known starting state.
        document.documentElement.dataset.theme = 'light';

        render(
            <SettingsPanel
                prefs={PREFERENCE_DEFAULTS}
                onSave={vi.fn().mockResolvedValue(undefined)}
                onClose={() => {}}
            />,
        );
        const toggle = screen.getByLabelText('Dark mode') as HTMLInputElement;
        fireEvent.click(toggle);
        expect(document.documentElement.dataset.theme).toBe('dark');
        fireEvent.click(toggle);
        expect(document.documentElement.dataset.theme).toBe('light');

        vi.restoreAllMocks();
        delete document.documentElement.dataset.theme;
    });
});
