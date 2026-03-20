import type React from 'react';

export interface WordColorScheme {
    known: React.CSSProperties;
    learning: React.CSSProperties;
    unknown: React.CSSProperties;
}

/**
 * Controls how words are styled in the subtitle based on the user's knowledge status.
 * Edit this file to change the color scheme — any valid React CSS properties work.
 */
export const WORD_COLORS: WordColorScheme = {
    known:    { color: '#388e3c' },  // green  — already know this word
    learning: { color: '#f57c00' },  // orange — still learning
    unknown:  { color: '#d32f2f' },  // red    — haven't seen this yet
};
