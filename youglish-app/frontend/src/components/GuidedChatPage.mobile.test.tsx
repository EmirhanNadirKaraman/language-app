/**
 * #27e — GuidedChatPage / MessageInput mobile guards.
 *
 * The most important check is the chat textarea's fontSize >= 16px (iOS zoom
 * blocker). We test MessageInput in isolation; GuidedChatPage's wiring is
 * verified by the existing chat flow tests.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MessageInput } from './MessageInput';

describe('MessageInput mobile (#27e)', () => {
    it('chat textarea has fontSize: 16px (iOS focus-zoom guard)', () => {
        render(<MessageInput onSend={() => {}} disabled={false} />);
        const input = screen.getByTestId('chat-input') as HTMLTextAreaElement;
        expect(input.style.fontSize).toBe('16px');
    });

    it('send button has 44px minHeight', () => {
        render(<MessageInput onSend={() => {}} disabled={false} />);
        const send = screen.getByTestId('chat-send') as HTMLElement;
        expect(send.style.minHeight).toBe('44px');
    });

    it('send button has minWidth >= 64px so it stays tappable even with 1-char label', () => {
        render(<MessageInput onSend={() => {}} disabled={false} />);
        const send = screen.getByTestId('chat-send') as HTMLElement;
        expect(send.style.minWidth).toBe('64px');
    });
});
