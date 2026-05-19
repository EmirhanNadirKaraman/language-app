/**
 * #27g — LoginForm mobile regression guards.
 *
 * Header form appears on every page when signed out — iOS-zoom guard on the
 * email/password inputs is the most critical fix in this audit.
 *
 * Load-bearing invariants:
 *   - Email + password inputs have fontSize: 16px (iOS focus-zoom guard).
 *   - Inputs have minHeight: 44px.
 *   - Primary "Sign in" submit has minHeight: 44px.
 *   - Cancel ✕ button is 44×44.
 *   - Sign-in toggle opens the inline form (behaviour preserved).
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { LoginForm } from './LoginForm';

describe('LoginForm mobile (#27g)', () => {
    it('signed-out toggle opens the inline form', () => {
        render(<LoginForm token={null} onLogin={() => {}} onLogout={() => {}} />);
        const toggle = screen.getByTestId('login-signin-toggle') as HTMLElement;
        fireEvent.click(toggle);
        expect(screen.getByTestId('login-email')).toBeTruthy();
        expect(screen.getByTestId('login-password')).toBeTruthy();
    });

    it('email + password inputs use fontSize: 16px and minHeight: 44px', () => {
        render(<LoginForm token={null} onLogin={() => {}} onLogout={() => {}} />);
        fireEvent.click(screen.getByTestId('login-signin-toggle'));
        const email = screen.getByTestId('login-email') as HTMLInputElement;
        const password = screen.getByTestId('login-password') as HTMLInputElement;
        for (const input of [email, password]) {
            expect(input.style.fontSize).toBe('16px');
            expect(input.style.minHeight).toBe('44px');
        }
    });

    it('Sign in submit button has minHeight: 44px', () => {
        render(<LoginForm token={null} onLogin={() => {}} onLogout={() => {}} />);
        fireEvent.click(screen.getByTestId('login-signin-toggle'));
        const submit = screen.getByTestId('login-submit') as HTMLElement;
        expect(submit.style.minHeight).toBe('44px');
    });

    it('cancel button is 44×44', () => {
        render(<LoginForm token={null} onLogin={() => {}} onLogout={() => {}} />);
        fireEvent.click(screen.getByTestId('login-signin-toggle'));
        const cancel = screen.getByTestId('login-cancel') as HTMLElement;
        expect(cancel.style.minWidth).toBe('44px');
        expect(cancel.style.minHeight).toBe('44px');
    });

    it('outline outline button responds to click (smoke test)', () => {
        const onLogin = vi.fn();
        render(<LoginForm token={null} onLogin={onLogin} onLogout={() => {}} />);
        // Open + close keeps the form-toggle path exercised even without a live API.
        fireEvent.click(screen.getByTestId('login-signin-toggle'));
        fireEvent.click(screen.getByTestId('login-cancel'));
        // Form collapsed back — toggle button returns.
        expect(screen.getByTestId('login-signin-toggle')).toBeTruthy();
    });
});
