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
import { Icons } from '@/components/icons';
import { Alert, Button, Field } from '@/components/ui';
import { ThemeToggle } from '@/theme/ThemeToggle';
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
    <div className="relative flex min-h-screen flex-col p-5" lang={language}>
      {/* A single soft wash behind the card. Enough to stop the page reading
          as a blank sheet, not so much that it competes with the one form on
          it. Pointer-events off so it can never eat a click on the field
          underneath. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div className="absolute -top-40 left-1/2 size-[36rem] -translate-x-1/2 rounded-full bg-brand/8 blur-3xl" />
      </div>

      <div className="relative ml-auto flex items-center gap-2">
        {/* Both offered before signing in, not after: somebody who cannot
            read this page cannot reach a setting that lives behind it. */}
        <LanguagePicker />
        <ThemeToggle />
      </div>

      <div className="relative m-auto w-full max-w-sm py-8">
        <div className="animate-rise mb-7 flex flex-col items-center text-center">
          <span
            aria-hidden="true"
            className="mb-4 grid size-12 place-items-center rounded-2xl bg-brand text-lg font-bold text-on-brand shadow-e2"
          >
            F
          </span>
          <h1 className="text-2xl font-semibold text-heading">{t('app.title')}</h1>
          <p className="mt-1.5 text-sm text-muted">
            Sign in with your college email address.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="animate-rise flex flex-col gap-4 rounded-2xl bg-raised p-6 shadow-e2 ring-1 ring-line"
          noValidate
        >
          {error ? <Alert>{error}</Alert> : null}
          {error === null && ssoError ? <Alert>{ssoError}</Alert> : null}

          <Field
            label={t('auth.email')}
            type="email"
            name="email"
            autoComplete="username"
            inputMode="email"
            autoCapitalize="none"
            spellCheck={false}
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

          <Button type="submit" size="lg" loading={submitting} className="mt-1 w-full">
            {submitting ? t('auth.signingIn') : t('auth.signIn')}
          </Button>

          {sso.data?.enabled ? (
            <>
              {/* Below the password form, not above it. Students have no
                  college directory account and are most of the people signing
                  in; putting the button they cannot use first would make the
                  form they need look like the fallback. */}
              <div className="flex items-center gap-3 text-xs text-faint">
                <span className="h-px flex-1 bg-line-strong" />
                <span>or</span>
                <span className="h-px flex-1 bg-line-strong" />
              </div>
              <a
                href="/api/auth/sso/start"
                className="flex min-h-11 items-center justify-center gap-2 rounded-md bg-surface px-4 text-sm font-medium text-body shadow-e1 ring-1 ring-line-strong transition-colors hover:bg-sunken"
              >
                <Icons.key className="size-4 text-muted" />
                Sign in with {sso.data.label}
              </a>
              <p className="text-center text-xs text-faint">
                For staff. Students sign in above.
              </p>
            </>
          ) : null}

          <Link
            to="/forgot-password"
            className="text-center text-sm text-brand-text hover:underline"
          >
            Forgotten your password?
          </Link>
        </form>

        {/* The legacy form asked people to pick "Student / Faculty /
            Hod-Principal" from a dropdown, which selected the database table
            to authenticate against. The role comes from the account now, so
            there is nothing here to choose. */}
      </div>
    </div>
  );
}
