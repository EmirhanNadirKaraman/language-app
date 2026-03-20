export const PASSIVE_MAX = 5;
export const ACTIVE_MAX = 3;

/** Returns human-readable due text if due within 7 days, otherwise null. */
export function formatDueDate(iso: string | null): string | null {
    if (!iso) return null;
    const diffMs = new Date(iso).getTime() - Date.now();
    const diffDays = diffMs / (1000 * 60 * 60 * 24);
    if (diffDays <= 0) return 'Review now';
    if (diffDays <= 1) return 'Review today';
    const days = Math.ceil(diffDays);
    if (days <= 7) return `Review in ${days}d`;
    return null;
}

/** Returns filled/empty dot counts for a progress bar capped at max. */
export function progressDots(level: number, max: number): { filled: number; empty: number } {
    const filled = Math.min(level, max);
    return { filled, empty: max - filled };
}
