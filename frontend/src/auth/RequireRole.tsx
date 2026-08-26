import { Navigate, Outlet, useLocation } from 'react-router-dom';

import type { Role } from '@/api/types';
import { landingFor } from '@/auth/landing';
import { Spinner } from '@/components/ui';
import { useAuth } from '@/auth/useAuth';

/**
 * Route guard.
 *
 * This is a usability control, not a security one — the API enforces access on
 * every request regardless of what the browser believes. Hiding a route here
 * without the matching dependency on the server would be exactly the mistake
 * the legacy app made, where authorization existed only in the UI.
 */
export function RequireRole({ allow }: { allow: readonly Role[] }) {
  const { account, isResolving } = useAuth();
  const location = useLocation();

  // Redirecting before /auth/me settles would bounce a signed-in user to the
  // login page on every reload.
  if (isResolving) {
    return <FullPageSpinner label="Checking your session" />;
  }

  if (account === null) {
    // Remember where they were headed so sign-in can return them there.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (!allow.includes(account.role)) {
    // Send them to their own area rather than showing a dead end.
    return <Navigate to={landingFor(account.role)} replace />;
  }

  return <Outlet />;
}

export function FullPageSpinner({ label }: { label: string }) {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center gap-3"
      role="status"
      aria-live="polite"
    >
      <Spinner className="size-5 text-brand" />
      <span className="text-sm text-muted">{label}...</span>
    </div>
  );
}
