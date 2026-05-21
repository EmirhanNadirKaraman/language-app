// Privacy policy page. Plain text rendered as React for now — no MDX dep.
// Update CONTACT_EMAIL + LAST_UPDATED when the policy changes.

const LAST_UPDATED = '2026-05-20';
// TODO before public launch: replace with a monitored privacy/support email.
// The literal token is intentional — it must never look like a real address
// (e.g. don't put a domain we don't own). Leave the angle brackets in.
const CONTACT_EMAIL = '<YOUR_REAL_PRIVACY_EMAIL_BEFORE_LAUNCH>';

export function PrivacyPage() {
    const section: React.CSSProperties = {
        fontSize: '15px',
        fontWeight: 700,
        color: 'var(--color-text-strong)',
        margin: '20px 0 8px',
    };
    const p: React.CSSProperties = {
        margin: '0 0 10px',
        fontSize: '14px',
        lineHeight: 1.55,
        color: 'var(--color-text)',
    };
    const li: React.CSSProperties = {
        fontSize: '14px',
        lineHeight: 1.55,
        color: 'var(--color-text)',
        marginBottom: '4px',
    };

    return (
        <div
            data-testid="privacy-page"
            style={{
                maxWidth: '720px',
                margin: '24px auto',
                padding: 'clamp(14px, 4vw, 24px)',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: '8px',
                color: 'var(--color-text)',
            }}
        >
            <h1 style={{ margin: '0 0 4px', fontSize: '22px', color: 'var(--color-text-strong)' }}>
                Privacy Policy
            </h1>
            <p style={{ ...p, color: 'var(--color-text-muted)', fontSize: '12px' }}>
                Last updated: {LAST_UPDATED}
            </p>

            <h2 style={section}>What we store</h2>
            <ul>
                <li style={li}>
                    <strong>Account</strong>: email address (used to sign in) and a hashed password.
                    We never store passwords in plain text.
                </li>
                <li style={li}>
                    <strong>Learning data</strong>: which words / phrases / grammar rules
                    you've encountered, your per-item status (unknown / learning / known),
                    spaced-repetition card schedules, and per-event usage history
                    (transcript clicks, SRS reviews, chat turns).
                </li>
                <li style={li}>
                    <strong>Uploaded PDFs and reading selections</strong>: book files you
                    upload, the OCR/text extraction we run on them, and the
                    multi-token selections you save while reading.
                </li>
                <li style={li}>
                    <strong>Chat sessions</strong>: free and guided chat transcripts,
                    including LLM evaluations of your messages.
                </li>
                <li style={li}>
                    <strong>Preferences</strong>: theme choice, followed channels and
                    genres, SRS thresholds, reminder + auto-mark toggles.
                </li>
                <li style={li}>
                    <strong>Operational logs</strong>: client-side crash reports
                    (message, stack trace, page URL, user-agent) so we can fix
                    rendering bugs. Reports submitted while signed in are linked
                    to your account; if you delete your account, those links are
                    cleared and the report stays in anonymised form.
                </li>
            </ul>

            <h2 style={section}>How we use third-party services</h2>
            <p style={p}>
                Translations, evaluation of your chat messages, and a few other
                language tasks call Anthropic's Claude API. The text we send
                includes the words or sentences you are working with and, for
                chat, the messages of the current session. We do not share
                analytics or marketing data with third parties.
            </p>

            <h2 style={section}>YouTube content</h2>
            <p style={p}>
                Subtitles and metadata for educational videos are sourced from
                YouTube. The original videos are embedded via YouTube's player;
                YouTube's own privacy policy applies to that embed.
            </p>

            <h2 style={section}>Account deletion</h2>
            <p style={p}>
                You can permanently delete your account at any time from{' '}
                <strong>Settings → Account → Delete account</strong>. Deletion
                immediately removes your learning history, SRS cards, uploaded
                books, reading selections, chat sessions, notifications, and
                preferences. Shared catalog data (the word and phrase tables,
                public channel and video metadata) is not user-specific and is
                not deleted. Crash reports and content-add requests you
                submitted are kept in anonymised form (user link cleared) so
                operational signal isn't lost.
            </p>

            <h2 style={section}>Browser storage</h2>
            <p style={p}>
                On the web app, we keep two values in your browser's
                localStorage so you don't have to sign in on every page load:
            </p>
            <ul>
                <li style={li}>
                    <strong><code>auth_token</code></strong> — keeps you signed in.
                </li>
                <li style={li}>
                    <strong><code>auth_email</code></strong> — used to display the email of the signed-in account.
                </li>
            </ul>
            <p style={p}>
                Both are cleared when you sign out, delete your account, or
                your session expires. We don't use cookies for authentication,
                and the contents of your localStorage are <em>not</em> included
                in client error reports.
            </p>

            <h2 style={section}>Data retention</h2>
            <p style={p}>
                Account data lives until you delete your account. Backups may
                briefly retain copies (typically up to 30 days) before they roll
                off.
            </p>

            <h2 style={section}>Contact</h2>
            <p style={p}>
                Questions or requests about your data:{' '}
                {CONTACT_EMAIL.startsWith('<') ? (
                    <code style={{ background: 'var(--color-surface-muted)', padding: '1px 6px', borderRadius: '3px' }}>
                        {CONTACT_EMAIL}
                    </code>
                ) : (
                    <a href={`mailto:${CONTACT_EMAIL}`} style={{ color: 'var(--color-primary)' }}>{CONTACT_EMAIL}</a>
                )}
            </p>
        </div>
    );
}
