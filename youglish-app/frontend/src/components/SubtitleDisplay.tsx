import { highlightText } from '../utils/sentenceUtils';

interface Props {
    text: string;
    highlightTerms: string[];
}

export function SubtitleDisplay({ text, highlightTerms }: Props) {
    return (
        <div
            style={{
                width: '100%',
                height: '200px',
                padding: '32px 28px',
                overflow: 'hidden',
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
                    fontSize: '38px',
                    fontWeight: 500,
                    lineHeight: 1.4,
                    textAlign: 'center',
                    color: '#1a3a6c',
                    whiteSpace: 'normal',
                    overflowWrap: 'anywhere',
                    wordBreak: 'break-word',
                }}
            >
                {highlightText(text, highlightTerms)}
            </p>
        </div>
    );
}
