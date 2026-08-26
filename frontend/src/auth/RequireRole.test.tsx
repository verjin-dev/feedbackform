import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { Account, Role } from '@/api/types';
import { AuthContext, type AuthState } from '@/auth/AuthProvider';
import { RequireRole } from '@/auth/RequireRole';

function account(role: Role): Account {
  return {
    id: 1,
    role,
    school_id: null,
    first_name: 'Test',
    last_name: 'Person',
    full_name: 'Test Person',
    email: 'test.person@example.edu',
    class_group_id: role === 'student' ? 1 : null,
    avatar: null,
    language: 'en',
  };
}

function renderGuarded(state: Partial<AuthState>, allow: readonly Role[]) {
  const value: AuthState = {
    account: null,
    isResolving: false,
    signIn: async () => account('admin'),
    signOut: async () => {},
    ...state,
  };

  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route element={<RequireRole allow={allow} />}>
            <Route path="/admin" element={<p>Admin content</p>} />
          </Route>
          <Route path="/login" element={<p>Login page</p>} />
          <Route path="/results" element={<p>Faculty results</p>} />
          <Route path="/evaluate" element={<p>Student evaluate</p>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('RequireRole', () => {
  it('waits instead of redirecting while the session is still resolving', () => {
    // Redirecting here would bounce a signed-in user to /login on every reload.
    renderGuarded({ isResolving: true }, ['admin']);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
  });

  it('sends an anonymous visitor to the login page', () => {
    renderGuarded({ account: null }, ['admin']);

    expect(screen.getByText('Login page')).toBeInTheDocument();
  });

  it('renders the route for a permitted role', () => {
    renderGuarded({ account: account('admin') }, ['admin']);

    expect(screen.getByText('Admin content')).toBeInTheDocument();
  });

  it('sends a signed-in user of the wrong role to their own area', () => {
    renderGuarded({ account: account('student') }, ['admin']);

    expect(screen.getByText('Student evaluate')).toBeInTheDocument();
    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
  });

  it('does not show a student the admin area even briefly', () => {
    renderGuarded({ account: account('faculty') }, ['admin']);

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
    expect(screen.getByText('Faculty results')).toBeInTheDocument();
  });

  it('allows a route shared by several roles', () => {
    renderGuarded({ account: account('faculty') }, ['admin', 'faculty']);

    expect(screen.getByText('Admin content')).toBeInTheDocument();
  });
});
