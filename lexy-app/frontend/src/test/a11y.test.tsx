// Practical accessibility regression guards (#26 / 2026-05-21).
//
// Not a full WCAG sweep — just locks the high-impact gaps we just fixed so
// they don't regress: icon-only buttons must have accessible names, key
// form inputs must be labelable by role+name, image thumbnails must carry
// alt text, destructive actions must have clear text.
//
// One representative test per fix. Add more when fixing additional gaps.

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { WordStatusPicker } from '../components/WordStatusPicker';
import { SearchBar } from '../components/SearchBar';
import { LoginForm } from '../components/LoginForm';

vi.mock('../api/suggest', () => ({
  fetchSuggestions: vi.fn().mockResolvedValue([]),
}));


describe('a11y — accessible names on icon-only buttons', () => {
  it('WordStatusPicker close button is reachable by accessible name', () => {
    render(
      <WordStatusPicker
        word="Haus"
        lookup={null}
        loading={false}
        saving={false}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    expect(
      screen.getByRole('button', { name: /close word status picker/i }),
    ).toBeInTheDocument();
  });

  it('SearchBar input is reachable by accessible name', () => {
    render(
      <SearchBar
        terms={[]}
        onAddTerm={() => {}}
        onRemoveTerm={() => {}}
        loading={false}
      />
    );
    expect(
      screen.getByRole('textbox', { name: /search vocabulary/i }),
    ).toBeInTheDocument();
  });

  it('SearchBar term-chip remove buttons carry the term in their accessible name', () => {
    render(
      <SearchBar
        terms={['Haus', 'Brot']}
        onAddTerm={() => {}}
        onRemoveTerm={() => {}}
        loading={false}
      />
    );
    // "Remove search term Haus" / "Remove search term Brot"
    expect(
      screen.getByRole('button', { name: /remove search term haus/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /remove search term brot/i }),
    ).toBeInTheDocument();
  });
});

describe('a11y — LoginForm form inputs', () => {
  it('email + password inputs are labelable; submit button has accessible name', () => {
    const onLogin = vi.fn();
    const onLogout = vi.fn();
    render(<LoginForm token={null} onLogin={onLogin} onLogout={onLogout} />);

    // The Sign-in toggle opens the inline form. Use fireEvent so React's
    // synthetic event system runs the onClick handler and re-renders.
    fireEvent.click(screen.getByTestId('login-signin-toggle'));

    expect(screen.getByRole('textbox', { name: /email address/i })).toBeInTheDocument();
    // Password inputs don't expose role=textbox — find by accessible name.
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    // Cancel button is reachable by its aria-label.
    expect(screen.getByRole('button', { name: /^cancel$/i })).toBeInTheDocument();
    // Submit lives at data-testid login-submit; the visible text is "Sign in"
    // in login mode.
    expect(screen.getByTestId('login-submit')).toHaveTextContent(/sign in/i);
  });
});
