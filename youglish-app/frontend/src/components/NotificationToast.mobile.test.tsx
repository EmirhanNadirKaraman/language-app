/**
 * #27g — NotificationToast dismiss button mobile regression guard.
 *
 * Load-bearing invariants:
 *   - Dismiss × is 44×44.
 *   - Click still calls onDismiss(id).
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { NotificationContainer } from './NotificationToast';
import type { AppNotification } from '../hooks/useNotifications';

const NOTIFICATION: AppNotification = {
    id: 'n1',
    type: 'video_done',
    payload: {
        title: 'Test video',
        videos_added: 3,
    },
};

describe('NotificationToast mobile (#27g)', () => {
    it('dismiss button is 44×44 and fires onDismiss', () => {
        const onDismiss = vi.fn();
        render(<NotificationContainer notifications={[NOTIFICATION]} onDismiss={onDismiss} />);
        const dismiss = screen.getByTestId('notification-dismiss') as HTMLElement;
        expect(dismiss.style.minWidth).toBe('44px');
        expect(dismiss.style.minHeight).toBe('44px');
        fireEvent.click(dismiss);
        expect(onDismiss).toHaveBeenCalledWith('n1');
    });
});
