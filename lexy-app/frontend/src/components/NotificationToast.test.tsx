/**
 * NotificationToast rendering (audit fix A).
 *
 * Covers:
 *   - request_failed renders danger-styled with reason in body
 *   - request_failed gracefully degrades when payload.reason is missing
 *   - video_done still renders success-styled with title
 *   - channel_done still renders success-styled with channel name
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { NotificationContainer } from './NotificationToast';
import type { AppNotification } from '../hooks/useNotifications';

const FAILED_WITH_REASON: AppNotification = {
    id: 'f1',
    type: 'request_failed',
    payload: { reason: 'youtube_dl returned 403' },
};

const FAILED_WITHOUT_REASON: AppNotification = {
    id: 'f2',
    type: 'request_failed',
    payload: {},
};

const VIDEO_DONE: AppNotification = {
    id: 'v1',
    type: 'video_done',
    payload: { title: 'Sample lesson', videos_added: 4 },
};

const CHANNEL_DONE: AppNotification = {
    id: 'c1',
    type: 'channel_done',
    payload: { channel_name: 'DW Nachrichten', videos_added: 12 },
};

describe('NotificationToast — request_failed', () => {
    it('renders with danger-styled failure testid and reason in body', () => {
        render(<NotificationContainer notifications={[FAILED_WITH_REASON]} onDismiss={vi.fn()} />);

        const toast = screen.getByTestId('notification-toast-failure');
        expect(toast).toBeInTheDocument();
        expect(toast.style.borderLeft).toContain('var(--color-danger)');
        expect(toast.style.background).toContain('var(--color-danger-bg)');

        expect(screen.getByText('Request failed')).toBeInTheDocument();
        expect(screen.getByText(/youtube_dl returned 403/)).toBeInTheDocument();
    });

    it('falls back to a sane message when payload.reason is missing', () => {
        render(<NotificationContainer notifications={[FAILED_WITHOUT_REASON]} onDismiss={vi.fn()} />);
        expect(screen.getByTestId('notification-toast-failure')).toBeInTheDocument();
        expect(screen.getByText('Request failed')).toBeInTheDocument();
        // No literal "undefined" leaked through.
        expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
    });
});

describe('NotificationToast — successful types still work', () => {
    it('video_done renders success-styled with the video title', () => {
        render(<NotificationContainer notifications={[VIDEO_DONE]} onDismiss={vi.fn()} />);
        const toast = screen.getByTestId('notification-toast-success');
        expect(toast.style.borderLeft).toContain('var(--color-success)');
        expect(screen.getByText('Video processed')).toBeInTheDocument();
        expect(screen.getByText(/Sample lesson/)).toBeInTheDocument();
    });

    it('channel_done renders success-styled with the channel name', () => {
        render(<NotificationContainer notifications={[CHANNEL_DONE]} onDismiss={vi.fn()} />);
        const toast = screen.getByTestId('notification-toast-success');
        expect(toast.style.borderLeft).toContain('var(--color-success)');
        expect(screen.getByText('Channel scan complete')).toBeInTheDocument();
        expect(screen.getByText(/DW Nachrichten/)).toBeInTheDocument();
        expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
    });
});
