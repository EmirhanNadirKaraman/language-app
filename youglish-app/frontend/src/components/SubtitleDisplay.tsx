import { highlightText, renderClickableText } from '../utils/sentenceUtils';
import type { WordColorScheme } from '../config/wordColors';

interface Props {
    text: string;
    highlightTerms: string[];
    onWordClick?: (word: string) => void;
    onWordRightClick?: (word: string) => void;
    wordStatuses?: Record<string, string>;
    wordColors?: WordColorScheme;
}

export function SubtitleDisplay({ text, highlightTerms, onWordClick, onWordRightClick, wordStatuses = {}, wordColors }: Props) {
    const content = onWordClick
        ? renderClickableText(text, highlightTerms, onWordClick, wordStatuses, onWordRightClick, wordColors)
        : highlightText(text, highlightTerms);

    return (
        // Container changes for #27b:
        //   * fixed 200px height → 200px minHeight (lets long subtitles grow
        //     instead of clipping on mobile / large fonts)
        //   * tighter padding via clamp() instead of an isMobile branch (kept
        //     in CSS so we don't need useViewport for a purely-visual rule)
        <div
            style={{
                width: '100%',
                minHeight: '200px',
                padding: 'clamp(16px, 4vw, 32px) clamp(12px, 4vw, 28px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxSizing: 'border-box',
                minWidth: 0,
            }}
        >
            <p
                style={{
                    margin: 0,
                    width: '100%',
                    maxWidth: '100%',
                    minWidth: 0,
                    flex: '1 1 auto',
                    // Fluid font: 20px on a 320px phone, 38px on desktop. The
                    // 5vw middle term means it scales smoothly with viewport
                    // width without a useViewport branch.
                    fontSize: 'clamp(20px, 5vw, 38px)',
                    fontWeight: 500,
                    lineHeight: 1.4,
                    textAlign: 'center',
                    color: '#1a3a6c',
                    whiteSpace: 'normal',
                    overflowWrap: 'anywhere',
                    wordBreak: 'break-word',
                }}
            >
                {content}
            </p>
        </div>
    );
}
