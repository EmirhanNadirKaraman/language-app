import { useEffect, useState, useRef } from 'react';
import type { UserPreferences, UserPreferencesUpdate } from '../api/settings';

interface Props {
    prefs: UserPreferences;
    onSave: (update: UserPreferencesUpdate) => Promise<void>;
    onClose: () => void;
}

const PRESET_GENRES = [
    'News', 'Comedy', 'Sports', 'Music', 'Politics', 'Science',
    'Technology', 'Travel', 'Food', 'Education', 'Documentary',
    'Film', 'Gaming', 'History', 'Culture', 'Kids',
];

const POPULAR_CHANNELS = [
    'DW Nachrichten', 'Galileo', 'ZDF', 'ARD', 'BBC News',
    'TED', 'Kurzgesagt', 'Y-Kollektiv', 'Arte', 'MDR',
    'Spiegel TV', 'RTL', 'N-TV', 'Phoenix', 'WDR',
];

function parseList(s: string): string[] {
    return s.split(',').map(x => x.trim()).filter(Boolean);
}
function formatList(arr: string[]): string {
    return arr.join(', ');
}

function TagInput({
    value,
    onChange,
    placeholder,
    suggestions,
    presets,
    presetLabel,
}: {
    value: string;
    onChange: (v: string) => void;
    placeholder: string;
    suggestions: string[];
    presets: string[];
    presetLabel: string;
}) {
    const [inputText, setInputText] = useState('');
    const [showSuggestions, setShowSuggestions] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const current = parseList(value);

    function addTag(tag: string) {
        const trimmed = tag.trim();
        if (!trimmed || current.includes(trimmed)) return;
        onChange(formatList([...current, trimmed]));
        setInputText('');
        setShowSuggestions(false);
    }

    function removeTag(tag: string) {
        onChange(formatList(current.filter(t => t !== tag)));
    }

    function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
        if ((e.key === 'Enter' || e.key === ',') && inputText.trim()) {
            e.preventDefault();
            addTag(inputText);
        } else if (e.key === 'Backspace' && !inputText && current.length > 0) {
            removeTag(current[current.length - 1]);
        }
    }

    const filtered = suggestions.filter(s =>
        inputText && s.toLowerCase().includes(inputText.toLowerCase()) && !current.includes(s),
    );

    return (
        <div>
            {/* Preset chips */}
            <div style={{ marginBottom: '8px' }}>
                <span style={{ fontSize: '11px', color: '#999', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '5px' }}>
                    {presetLabel}
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                    {presets.map(p => {
                        const active = current.includes(p);
                        return (
                            <button
                                key={p}
                                type="button"
                                onClick={() => active ? removeTag(p) : addTag(p)}
                                style={{
                                    padding: '3px 10px', fontSize: '12px', borderRadius: '12px',
                                    border: '1px solid ' + (active ? '#1a237e' : '#ddd'),
                                    background: active ? '#e8eaf6' : '#fff',
                                    color: active ? '#1a237e' : '#666',
                                    cursor: 'pointer', fontWeight: active ? 600 : 400,
                                }}
                            >
                                {active ? '✓ ' : ''}{p}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Selected tags + input */}
            <div style={{ position: 'relative' }}>
                <div
                    onClick={() => inputRef.current?.focus()}
                    style={{
                        display: 'flex', flexWrap: 'wrap', gap: '5px', alignItems: 'center',
                        padding: '6px 8px', border: '1px solid #ccc', borderRadius: '6px',
                        minHeight: '38px', cursor: 'text', background: '#fff',
                    }}
                >
                    {current.map(tag => (
                        <span key={tag} style={{
                            display: 'inline-flex', alignItems: 'center', gap: '3px',
                            padding: '2px 8px', background: '#e8eaf6', borderRadius: '10px',
                            fontSize: '12px', color: '#1a237e',
                        }}>
                            {tag}
                            <button
                                type="button"
                                onClick={e => { e.stopPropagation(); removeTag(tag); }}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7986cb', fontSize: '13px', lineHeight: 1, padding: '0 1px' }}
                            >
                                ×
                            </button>
                        </span>
                    ))}
                    <input
                        ref={inputRef}
                        type="text"
                        value={inputText}
                        placeholder={current.length === 0 ? placeholder : ''}
                        onChange={e => { setInputText(e.target.value); setShowSuggestions(true); }}
                        onKeyDown={handleKeyDown}
                        onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                        onFocus={() => setShowSuggestions(true)}
                        style={{ border: 'none', outline: 'none', flex: 1, minWidth: '100px', fontSize: '13px', background: 'transparent' }}
                    />
                </div>

                {showSuggestions && filtered.length > 0 && (
                    <ul style={{
                        position: 'absolute', top: '100%', left: 0, right: 0,
                        background: '#fff', border: '1px solid #ccc', borderTop: 'none',
                        borderRadius: '0 0 5px 5px', margin: 0, padding: 0, listStyle: 'none',
                        zIndex: 300, maxHeight: '160px', overflowY: 'auto',
                        boxShadow: '0 4px 10px rgba(0,0,0,0.1)',
                    }}>
                        {filtered.map(s => (
                            <li key={s}
                                onMouseDown={() => addTag(s)}
                                style={{ padding: '8px 12px', cursor: 'pointer', fontSize: '13px' }}
                                onMouseEnter={e => (e.currentTarget.style.background = '#f0f4ff')}
                                onMouseLeave={e => (e.currentTarget.style.background = '#fff')}
                            >
                                {s}
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            <span style={{ fontSize: '11px', color: '#aaa', marginTop: '3px', display: 'block' }}>
                Click presets or type and press Enter
            </span>
        </div>
    );
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
    const [saved, setSaved]                       = useState(false);

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
            await onSave({
                liked_genres:           parseList(likedGenres),
                liked_channels:         parseList(likedChannels),
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

    // Build channel suggestions from all known channels in prefs
    const knownChannelNames = [
        ...POPULAR_CHANNELS,
        ...Object.values(prefs.channel_names ?? {}),
        ...(prefs.followed_channels ?? []).map(id => (prefs.channel_names ?? {})[id]).filter(Boolean),
    ];
    const uniqueChannels = [...new Set(knownChannelNames)];

    const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '16px' };
    const label: React.CSSProperties = { fontSize: '13px', fontWeight: 600, color: '#444' };
    const input: React.CSSProperties = { padding: '6px 10px', border: '1px solid #ccc', borderRadius: '5px', fontSize: '14px' };

    return (
        <div style={{ border: '1px solid #e8eaf6', borderRadius: '8px', padding: '20px 24px', background: '#fafafa', marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0, fontSize: '16px', color: '#1a237e' }}>Preferences</h2>
                <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#888' }} aria-label="Close settings">×</button>
            </div>

            {/* Recommendations */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 12px' }}>
                Recommendations
            </p>

            <div style={field}>
                <label style={label}>Liked genres</label>
                <TagInput
                    value={likedGenres}
                    onChange={setLikedGenres}
                    placeholder="e.g. News, Comedy…"
                    suggestions={PRESET_GENRES}
                    presets={PRESET_GENRES}
                    presetLabel="Quick picks"
                />
            </div>

            <div style={field}>
                <label style={label}>Liked channels</label>
                <TagInput
                    value={likedChannels}
                    onChange={setLikedChannels}
                    placeholder="e.g. DW Nachrichten…"
                    suggestions={uniqueChannels}
                    presets={POPULAR_CHANNELS.slice(0, 8)}
                    presetLabel="Popular channels"
                />
            </div>

            {/* SRS */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '18px 0 12px' }}>
                Spaced Repetition
            </p>

            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <div style={field}>
                    <label style={label}>Passive reps for "known"</label>
                    <input style={{ ...input, width: '80px' }} type="number" min={1} max={20}
                        value={passiveReps}
                        onChange={e => setPassiveReps(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))} />
                </div>
                <div style={field}>
                    <label style={label}>Active reps for "known"</label>
                    <input style={{ ...input, width: '80px' }} type="number" min={1} max={20}
                        value={activeReps}
                        onChange={e => setActiveReps(Math.max(1, Math.min(20, parseInt(e.target.value, 10) || 1)))} />
                </div>
            </div>

            {/* Word colors */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '18px 0 12px' }}>
                Word Colors
            </p>
            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '16px' }}>
                {[
                    { label: 'Known',    value: knownColor,    onChange: setKnownColor },
                    { label: 'Learning', value: learningColor, onChange: setLearningColor },
                    { label: 'Unknown',  value: unknownColor,  onChange: setUnknownColor },
                ].map(({ label: lbl, value, onChange }) => (
                    <div key={lbl} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                        <input type="color" value={value} onChange={e => onChange(e.target.value)}
                            style={{ width: '44px', height: '36px', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', padding: '2px' }} />
                        <span style={{ fontSize: '12px', color: '#555', fontWeight: 600 }}>{lbl}</span>
                        <span style={{ fontSize: '11px', color: value, fontWeight: 700 }}>Aa</span>
                    </div>
                ))}
            </div>

            {/* Reminders */}
            <p style={{ fontSize: '12px', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '18px 0 10px' }}>
                Reminders
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '18px' }}>
                <input id="reminders-toggle" type="checkbox" checked={remindersEnabled}
                    onChange={e => setRemindersEnabled(e.target.checked)}
                    style={{ width: '16px', height: '16px', cursor: 'pointer' }} />
                <label htmlFor="reminders-toggle" style={{ fontSize: '13px', color: '#444', cursor: 'pointer' }}>
                    Show banner when reviews are due
                </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <button onClick={handleSave} disabled={saving}
                    style={{ padding: '8px 22px', background: '#1a237e', color: '#fff', border: 'none', borderRadius: '6px', fontSize: '14px', fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1 }}>
                    {saving ? 'Saving…' : 'Save'}
                </button>
                {saved && <span style={{ fontSize: '13px', color: '#388e3c' }}>Saved</span>}
            </div>
        </div>
    );
}
