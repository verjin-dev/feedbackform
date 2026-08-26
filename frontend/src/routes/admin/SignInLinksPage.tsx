import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '@/api/client';
import { Badge } from '@/components/DataTable';
import { ConfirmDialog } from '@/components/Dialog';
import { Alert, Button, Card } from '@/components/ui';

interface SignInLink {
  id: number;
  account_id: number;
  account_name: string;
  account_email: string;
  email_at_link: string;
  provider: string;
  linked_at: string | null;
  last_used_at: string | null;
  stale: boolean;
}

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

function when(value: string | null): string {
  return value === null ? 'never' : new Date(value).toLocaleDateString();
}

/**
 * Which college directory accounts can sign in as whom.
 *
 * The change log says what changed; this says what is true now, which is the
 * question actually asked when somebody leaves. It is also the screen the
 * sign-in flow sends people to: a member of staff given a departed colleague's
 * address is refused there and told an administrator has to unlink it first.
 */
export function SignInLinksPage() {
  const queryClient = useQueryClient();
  const [removing, setRemoving] = useState<SignInLink | null>(null);
  const [error, setError] = useState<string | null>(null);

  const links = useQuery({
    queryKey: ['sso', 'links'],
    queryFn: () => api.get<SignInLink[]>('/auth/sso/links'),
  });

  const unlink = useMutation({
    mutationFn: (id: number) => api.delete<void>(`/auth/sso/links/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sso', 'links'] }),
  });

  async function confirmUnlink() {
    if (removing === null) return;
    setError(null);
    try {
      await unlink.mutateAsync(removing.id);
      setRemoving(null);
    } catch (cause) {
      setError(messageFrom(cause, 'Could not remove that link.'));
      setRemoving(null);
    }
  }

  const rows = links.data ?? [];
  const stale = rows.filter((row) => row.stale);

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <Card title="College sign-in">
        <p className="mb-4 max-w-prose text-sm text-ink-500">
          Staff who can sign in with their college account instead of a
          password. Removing a link never touches the account or its history —
          the person keeps their password, their assignments and everything
          past reports were built from.
        </p>

        {stale.length > 0 ? (
          <Alert tone="caution">
            {stale.length === 1 ? 'One link is' : `${stale.length} links are`} held
            against an address that is no longer the account&apos;s. That is what a
            reassigned address looks like. Remove the link, and the person now
            using that address can sign in and link it themselves.
          </Alert>
        ) : null}

        <div className="mt-4 overflow-x-auto">
          {links.isLoading ? (
            <p className="py-6 text-center text-sm text-ink-400" role="status">
              Loading...
            </p>
          ) : rows.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-400">
              Nobody has signed in with a college account yet.
            </p>
          ) : (
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="text-xs text-ink-400">
                <tr>
                  <th scope="col" className="py-1 pr-4 font-medium">
                    Account
                  </th>
                  <th scope="col" className="py-1 pr-4 font-medium">
                    Linked with
                  </th>
                  <th scope="col" className="py-1 pr-4 font-medium">
                    Linked
                  </th>
                  <th scope="col" className="py-1 pr-4 font-medium">
                    Last used
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-t border-ink-100">
                    <td className="py-2 pr-4">
                      <div className="text-ink-800">{row.account_name}</div>
                      <div className="text-xs text-ink-400">{row.account_email}</div>
                    </td>
                    <td className="py-2 pr-4">
                      <span className="text-ink-700">{row.email_at_link}</span>
                      {row.stale ? (
                        <span className="ml-2">
                          <Badge tone="caution">no longer matches</Badge>
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2 pr-4 text-ink-500 tabular-nums">
                      {when(row.linked_at)}
                    </td>
                    <td className="py-2 pr-4 text-ink-500 tabular-nums">
                      {when(row.last_used_at)}
                    </td>
                    <td className="py-2 text-right">
                      <Button
                        variant="ghost"
                        className="text-critical-600"
                        onClick={() => setRemoving(row)}
                      >
                        Unlink
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      <ConfirmDialog
        open={removing !== null}
        title="Remove college sign-in link"
        busy={unlink.isPending}
        message={
          removing === null ? null : (
            <>
              <strong>{removing.account_name}</strong> will no longer be able to
              sign in with <strong>{removing.email_at_link}</strong>. Their
              account, their password and their history are untouched, and they
              can link a college account again by signing in with one.
            </>
          )
        }
        onConfirm={confirmUnlink}
        onClose={() => setRemoving(null)}
      />
    </div>
  );
}
