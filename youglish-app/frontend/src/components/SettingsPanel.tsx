import { useEffect, useState } from 'react';
import type { UserPreferences, UserPreferencesUpdate } from '../api/settings';

interface Props {
    prefs: UserPreferences;
    onSave: (update: UserPreferencesUpdate) => Promise<void>;
    onClose: () => void;
}

export function SettingsPanel({ prefs, onSave, onClose }: Props) {
    const [likedGenres, setLikedGenres]     = useState('');
    const [likedChannels, setLikedChannels] = useState('');
    const [passiveReps, setPassiveReps]     = useState(prefs.passive_reps_for_known);
    const [activeReps, setActiveReps]       = useState(prefs.active_reps_for_known);
    const [knownColor, setKnownColor]             = useState(prefs.known_word_color);
    const [learningColor, setLearningColor]       = useState(prefs.learning_word_color);
    const [unknownColor, setUnknownColor]         = useState(prefs.unknown_word_color);
    const [remindersEnabled, setRemindersEnabled] = useState(prefs.reminders_enabled);
    const [saving, setSaving]                     = useState(false);
    const [saved, setSaved]                 = useState(false);

    // Sync local state when prefs change (e.g. after initial fetch)
    useEffect(() => {
        setLikedGenres(prefs.liked_genres.join(', '));
        setLikedChannels(prefs.liked_channels.join(', '));
        setPassiveReps(prefs.passive_reps_for_known);
        setActiveReps(prefs.active_reps_for_known);
        setKnownColor(prefs.known_word_color);
        setLearningColor(prefs.learning_word_color);
        setUnknownColor(prefs.unknown_word_color);
        setRemindersEnabled(prefs.reminders_enabled);
    }, [prefs]);

    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        try {
            const splitTrim = (s: string) =>
                s.split(',').map(x => x.trim()).filter(Boolean);

            await onSave({
                liked_genres:           splitTrim(likedGenres),
                liked_channels:         splitTrim(likedChannels),
                passive_reps_for_known: passiveReps,
                active_reps_for_known:  activeReps,
                known_word_color:       knownColor,
                learning_word_color:    learningColor,
                unknown_word_color:     unknownColor,
                reminders_enabled:      remindersEnabled,
            });
            setSaved(true);
        } finally {
            setSaving(false);
        }
    };

    const field: React.CSSProperties = {
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        marginBottom: '14px',
    };
    const label: React.CSSProperties = {
        fontSize: '13px',
        fontWeight: 600,
        color: '#444',
    };
    const input: React.CSSProperties = {
        padding: '6px 10px',
        border: '1px solid #ccc',
        borderRadius: '5px',
        fontSize: '14px',
    };
    const hint: React.CSSProperties = {
        fontSize: '11px',
        color: '#999',
    };

    return (
        <div
            style={{
                border: '1px solid #e8eaf6',
                borderRadius: '8px',
                padding: '20px 24px',
                background: '#fafafa',
                marginBottom: '16px',
            }}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
                <h2 style={{ margin: 0, fontSize: '16px', color: '#1a237e' }}>Preferences</h2>
                <button
                    onClick={onClose}
                    style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#888' }}
                    aria-label="Close settings"
                >
                    ×
                </button>
            </div>

            {/* Recommendation */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 10px' }}>
                Recommendations
            </p>

            <div style={field}>
                <label style={label}>Liked genres</label>
                <input
                    style={input}
                    value={likedGenres}
                    onChange={e => setLikedGenres(e.target.value)}
                    placeholder="e.g. news, comedy, sports"
                />
                <span style={hint}>Comma-separated. Comma-separated. Use the Follow/Like/Dislike buttons on video cards to set preferences directly.</span>
            </div>

            <div style={field}>
                <label style={label}>Liked channels</label>
                <input
                    style={input}
                    value={likedChannels}
                    onChange={e => setLikedChannels(e.target.value)}
                    placeholder="e.g. DW Nachrichten, Galileo"
                />
                <span style={hint}>Comma-separated. Comma-separated. Use the Follow/Like/Dislike buttons on video cards to set preferences directly.</span>
            </div>

            {/* SRS */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '16px 0 10px' }}>
                Spaced Repetition
            </p>

            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <div style={field}>
                    <label style={label}>Passive reps for "known"</label>
                    <input
                        style={{ ...input, width: '80px' }}
                        type="number"
                        min={1}
                        max={20}
                        value={passiveReps}
                        onChange={e => setPassiveReps(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))}
                    />
                </div>
                <div style={field}>
                    <label style={label}>Active reps for "known"</label>
                    <input
                        style={{ ...input, width: '80px' }}
                        type="number"
                        min={1}
                        max={20}
                        value={activeReps}
                        onChange={e => setActiveReps(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))}
                    />
                </div>
            </div>

            {/* Display */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '16px 0 10px' }}>
                Word Colors
            </p>

            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '14px' }}>
                {[
                    { label: 'Known', value: knownColor, onChange: setKnownColor },
                    { label: 'Learning', value: learningColor, onChange: setLearningColor },
                    { label: 'Unknown', value: unknownColor, onChange: setUnknownColor },
                ].map(({ label: lbl, value, onChange }) => (
                    <div key={lbl} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                        <input
                            type="color"
                            value={value}
                            onChange={e => onChange(e.target.value)}
                            style={{ width: '44px', height: '36px', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', padding: '2px' }}
                        />
                        <span style={{ fontSize: '12px', color: '#555', fontWeight: 600 }}>{lbl}</span>
                        <span style={{ fontSize: '11px', color: value, fontWeight: 700 }}>Aa</span>
                    </div>
                ))}
            </div>

            {/* Reminders */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '16px 0 10px' }}>
                Reminders
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                <input
                    id="reminders-toggle"
                    type="checkbox"
                    checked={remindersEnabled}
                    onChange={e => setRemindersEnabled(e.target.checked)}
                    style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                />
                <label htmlFor="reminders-toggle" style={{ fontSize: '13px', color: '#444', cursor: 'pointer' }}>
                    Show banner when reviews are due
                </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
                <button
                    onClick={handleSave}
                    disabled={saving}
                    style={{
                        padding: '8px 22px',
                        background: '#1a237e',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '14px',
                        fontWeight: 600,
                        cursor: saving ? 'not-allowed' : 'pointer',
                        opacity: saving ? 0.7 : 1,
                    }}
                >
                    {saving ? 'Saving…' : 'Save'}
                </button>
                {saved && <span style={{ fontSize: '13px', color: '#388e3c' }}>Saved</span>}
            </div>
        </div>
    );
}
