import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';

import { ApiError, api } from '@/api/client';
import { landingFor } from '@/auth/landing';
import { useAuth } from '@/auth/useAuth';
import { FullPageSpinner } from '@/auth/RequireRole';
import { Alert, Button, Field } from '@/components/ui';
import { LanguagePicker } from '@/i18n/LanguagePicker';
import { useLanguage } from '@/i18n/useLanguage';

export function LoginPage() {
  const { account, isResolving, signIn } = useAuth();
  const { language, t } = useLanguage();
  const [params] = useSearchParams();

  // Sign-in over the college directory redirects back here, so failures from
  // that round trip arrive as a query parameter rather than as a response.
  const ssoError = params.get('sso_error');

  const sso = useQuery({
    queryKey: ['auth', 'sso', 'status'],
    queryFn: () => api.get<{ enabled: boolean; label: string }>('/auth/sso/status'),
    staleTime: Infinity,
    retry: false,
  });
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isResolving) return <FullPageSpinner label={t('auth.checkingSession')} />;

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
        // The API deliberately returns the same message for an unknown
        // address and a wrong password, and returns it in English. Showing it
        // verbatim keeps the two indistinguishable, which matters more than
        // showing it translated.
        cause instanceof ApiError ? cause.message : t('auth.failed'),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-5" lang={language}>
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-ink-900">{t('app.title')}</h1>
            <p className="mt-1 text-sm text-ink-500">
              Sign in with your college email address.
            </p>
          </div>
          {/* Offered before signing in, not after: a student who cannot read
              this page cannot reach a setting that lives behind it. */}
          <LanguagePicker />
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 rounded-lg bg-white p-6 ring-1 ring-ink-200"
          noValidate
        >
          {error ? <Alert>{error}</Alert> : null}
          {error === null && ssoError ? <Alert>{ssoError}</Alert> : null}

          <Field
            label={t('auth.email')}
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <Field
            label={t('auth.password')}
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button type="submit" loading={submitting}>
            {submitting ? t('auth.signingIn') : t('auth.signIn')}
          </Button>

          {sso.data?.enabled ? (
            <>
              {/* Below the password form, not above it. Students have no
                  college directory account and are most of the people signing
                  in; putting the button they cannot use first would make the
                  form they need look like the fallback. */}
              <div className="flex items-center gap-3 text-xs text-ink-400">
                <span className="h-px flex-1 bg-ink-200" />
                <span>or</span>
                <span className="h-px flex-1 bg-ink-200" />
              </div>
              <a
                href="/api/auth/sso/start"
                className="flex min-h-11 items-center justify-center rounded-md bg-white px-4 text-sm font-medium text-ink-800 ring-1 ring-ink-200 hover:bg-ink-50"
              >
                Sign in with {sso.data.label}
              </a>
              <p className="text-center text-xs text-ink-400">
                For staff. Students sign in above.
              </p>
            </>
          ) : null}

          <Link
            to="/forgot-password"
            className="text-center text-sm text-accent-600 hover:underline"
          >
            Forgotten your password?
          </Link>
        </form>

        {/* The legacy form asked people to pick "Student / Faculty /
            Hod-Principal" from a dropdown, which selected the database table to
            authenticate against. The role comes from the account now, so
            there is nothing here to choose. */}
      </div>
    </div>
  );
}
