export interface ReminderSummary {
    srs_due_count: number;
    reading_due_count: number;
    learning_item_count: number;
    total_due: number;
    has_anything_due: boolean;
}

export async function getReminderSummary(token: string): Promise<ReminderSummary> {
    const res = await fetch('/api/v1/reminders/summary', {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to fetch reminder summary');
    return res.json() as Promise<ReminderSummary>;
}
