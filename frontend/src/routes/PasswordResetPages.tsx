import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { ApiError, api } from '@/api/client';
import { Alert, Button, Card, Field } from '@/components/ui';

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-5">
      <div className="w-full max-w-sm">
        <h1 className="mb-1 text-xl font-semibold text-heading">{title}</h1>
        <div className="mt-5">{children}</div>
        <p className="mt-4 text-center text-sm">
          <Link to="/login" className="text-brand-text hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

/** Asks for an address and says the same thing whatever the answer. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post('/auth/password-reset/request', { email });
      setSent(true);
    } catch (cause) {
      setError(messageFrom(cause, 'Something went wrong. Please try again.'));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Shell title="Check your email">
        <Card>
          <p className="text-sm text-muted">
            If <strong>{email}</strong> has an account, a link to choose a new
            password is on its way. It works for one hour and can only be used
            once.
          </p>
          <p className="mt-3 text-sm text-muted">
            Nothing arrived? Check the spam folder, then ask your administrator
            to confirm which address your account uses.
          </p>
        </Card>
      </Shell>
    );
  }

  return (
    <Shell title="Forgotten password">
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 rounded-lg bg-surface p-6 ring-1 ring-line-strong"
        noValidate
      >
        {error ? <Alert>{error}</Alert> : null}
        <p className="text-sm text-muted">
          Enter your college email address and we will send you a link to choose
          a new password.
        </p>
        <Field
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Button type="submit" loading={busy} className="min-h-11">
          Send the link
        </Button>
      </form>
    </Shell>
  );
}

/**
 * Redeems a link. Serves both /reset-password and /set-password — the flows
 * differ only in wording and in the purpose the token was minted for.
 */
export function SetPasswordPage({ mode }: { mode: 'reset' | 'invite' }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') ?? '';
  const purpose = mode === 'invite' ? 'invitation' : 'password-reset';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Checked before the form is shown, so an expired link says so rather than
  // being discovered after someone has typed a password twice.
  const check = useQuery({
    queryKey: ['reset-check', token, purpose],
    queryFn: () =>
      api.get<{ valid: boolean; email: string | null; first_name: string | null }>(
        '/auth/password-reset/check',
        { token, purpose },
      ),
    enabled: token !== '',
    retry: false,
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }
    if (password.length < 12) {
      setError('Use at least 12 characters.');
      return;
    }

    setBusy(true);
    try {
      await api.post(
        `/auth/password-reset/confirm?purpose=${purpose}`,
        { token, new_password: password },
      );
      setDone(true);
    } catch (cause) {
      setError(messageFrom(cause, 'That did not work. Request a new link.'));
    } finally {
      setBusy(false);
    }
  }

  const title = mode === 'invite' ? 'Set your password' : 'Choose a new password';

  if (done) {
    return (
      <Shell title="Password set">
        <Card>
          <p className="text-sm text-muted">
            Your password has been {mode === 'invite' ? 'set' : 'changed'}. Sign
            in with it to continue.
          </p>
          <div className="mt-4">
            <Button onClick={() => navigate('/login')} className="min-h-11 w-full">
              Sign in
            </Button>
          </div>
        </Card>
      </Shell>
    );
  }

  if (token === '' || check.data?.valid === false || check.isError) {
    return (
      <Shell title="This link no longer works">
        <Card>
          <p className="text-sm text-muted">
            It may have expired, or it may already have been used — each link
            works once.
          </p>
          <div className="mt-4">
            <Button
              variant="secondary"
              onClick={() => navigate('/forgot-password')}
              className="min-h-11 w-full"
            >
              Request a new link
            </Button>
          </div>
        </Card>
      </Shell>
    );
  }

  if (check.isLoading) {
    return (
      <Shell title={title}>
        <p className="text-center text-sm text-faint" role="status">
          Checking your link...
        </p>
      </Shell>
    );
  }

  return (
    <Shell title={title}>
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 rounded-lg bg-surface p-6 ring-1 ring-line-strong"
        noValidate
      >
        {error ? <Alert>{error}</Alert> : null}
        {check.data?.first_name ? (
          <p className="text-sm text-muted">
            Hello {check.data.first_name} — this is for{' '}
            <strong>{check.data.email}</strong>.
          </p>
        ) : null}

        <Field
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="At least 12 characters."
        />
        <Field
          label="Repeat it"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
        <Button type="submit" loading={busy} className="min-h-11">
          Save password
        </Button>
      </form>
    </Shell>
  );
}
