import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { landingFor } from '@/auth/landing';
import { useAuth } from '@/auth/useAuth';
import { FullPageSpinner } from '@/auth/RequireRole';
import { Alert, Button, Field } from '@/components/ui';

export function LoginPage() {
  const { account, isResolving, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isResolving) return <FullPageSpinner label="Checking your session" />;

  // Already signed in — no reason to show the form again.
  if (account !== null) return <Navigate to={landingFor(account.role)} replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const signedIn = await signIn(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? landingFor(signedIn.role), { replace: true });
    } catch (cause) {
      // The API deliberately returns the same message for an unknown address
      // and a wrong password. Showing it verbatim keeps it that way.
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'Something went wrong. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-5">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-ink-900">Faculty Evaluation</h1>
          <p className="mt-1 text-sm text-ink-500">
            Sign in with your college email address.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 rounded-lg bg-white p-6 ring-1 ring-ink-200"
          noValidate
        >
          {error ? <Alert>{error}</Alert> : null}

          <Field
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <Field
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button type="submit" loading={submitting}>
            {submitting ? 'Signing in' : 'Sign in'}
          </Button>
        </form>

        {/* The legacy form asked people to pick "Student / Faculty /
            Hod-Principal" from a dropdown, which selected the database table to
            authenticate against. The role comes from the account now, so
            there is nothing here to choose. */}
      </div>
    </div>
  );
}
