import { useEffect, useRef, useState } from 'react';
import { getReminderSummary, type ReminderSummary } from '../api/reminders';

const CHECK_INTERVAL_MS = 30 * 60 * 1000;   // 30 minutes
const NOTIF_THROTTLE_MS = 4 * 60 * 60 * 1000; // 4 hours

function buildNotificationBody(summary: ReminderSummary): string {
    const parts: string[] = [];
    if (summary.srs_due_count > 0) parts.push(`${summary.srs_due_count} SRS review${summary.srs_due_count > 1 ? 's' : ''}`);
    if (summary.reading_due_count > 0) parts.push(`${summary.reading_due_count} reading unit${summary.reading_due_count > 1 ? 's' : ''}`);
    return parts.join(' and ') + ' due';
}

function canFireNotification(): boolean {
    const last = localStorage.getItem('lastNotificationAt');
    if (!last) return true;
    return Date.now() - parseInt(last, 10) > NOTIF_THROTTLE_MS;
}

function fireNotification(summary: ReminderSummary) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    if (!canFireNotification()) return;
    new Notification('Time to practice!', {
        body: buildNotificationBody(summary),
        tag: 'learning-reminder',
        icon: '/favicon.ico',
    });
    localStorage.setItem('lastNotificationAt', String(Date.now()));
}

function isDismissedToday(): boolean {
    const dismissed = localStorage.getItem('reminderDismissedAt');
    if (!dismissed) return false;
    const date = new Date(parseInt(dismissed, 10));
    const today = new Date();
    return date.getFullYear() === today.getFullYear()
        && date.getMonth() === today.getMonth()
        && date.getDate() === today.getDate();
}

export interface UseRemindersResult {
    summary: ReminderSummary | null;
    showBanner: boolean;
    dismissBanner: () => void;
}

export function useReminders(token: string | null, enabled: boolean): UseRemindersResult {
    const [summary, setSummary] = useState<ReminderSummary | null>(null);
    const [showBanner, setShowBanner] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    function dismissBanner() {
        setShowBanner(false);
        localStorage.setItem('reminderDismissedAt', String(Date.now()));
    }

    async function check(fireNotif: boolean) {
        if (!token || !enabled) return;
        try {
            const data = await getReminderSummary(token);
            setSummary(data);
            if (data.has_anything_due) {
                if (!isDismissedToday()) setShowBanner(true);
                if (fireNotif) fireNotification(data);
            }
        } catch {
            // non-fatal — silently ignore
        }
    }

    useEffect(() => {
        if (!token || !enabled) {
            setSummary(null);
            setShowBanner(false);
            return;
        }

        // On mount: fetch but don't fire notification (user just opened the app)
        check(false);

        // Periodic background check: only fires notification when tab is hidden
        intervalRef.current = setInterval(() => {
            if (document.visibilityState === 'hidden') {
                check(true);
            } else {
                check(false);
            }
        }, CHECK_INTERVAL_MS);

        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token, enabled]);

    return { summary, showBanner, dismissBanner };
}
