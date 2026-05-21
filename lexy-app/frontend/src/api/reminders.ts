import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';

export interface ReminderSummary {
    srs_due_count: number;
    reading_due_count: number;
    learning_item_count: number;
    total_due: number;
    has_anything_due: boolean;
}

export async function getReminderSummary(token: string): Promise<ReminderSummary> {
    const res = await fetch(apiUrl('/api/v1/reminders/summary'), {
        headers: { Authorization: `Bearer ${token}` },
    });
    return assertOkJson<ReminderSummary>(res, 'Failed to fetch reminder summary');
}
