import { useEffect, useRef } from 'react';
import { highlightText } from '../utils/sentenceUtils';

interface Props {
    text: string;
    highlightTerms: string[];
}

export function SubtitleDisplay({ text, highlightTerms }: Props) {
    const wrapperRef = useRef<HTMLDivElement>(null);
    const textRef = useRef<HTMLParagraphElement>(null);

    useEffect(() => {
        const wrapper = wrapperRef.current;
        const p = textRef.current;

        console.log('--- SUBTITLE DISPLAY DEBUG ---');
        console.log('text:', text);
        console.log('wrapper', wrapper && {
            clientWidth: wrapper.clientWidth,
            scrollWidth: wrapper.scrollWidth,
            offsetWidth: wrapper.offsetWidth,
        });
        console.log('p', p && {
            clientWidth: p.clientWidth,
            scrollWidth: p.scrollWidth,
            offsetWidth: p.offsetWidth,
        });
    }, [text]);

    return (
        <div
            ref={wrapperRef}
            data-debug="subtitle-wrapper"
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
                outline: '2px solid red',
            }}
        >
            <p
                ref={textRef}
                data-debug="subtitle-text"
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
                    outline: '2px solid blue',
                }}
            >
                {highlightText(text, highlightTerms)}
            </p>
        </div>
    );
}