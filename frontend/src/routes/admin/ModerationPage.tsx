import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '@/api/client';
import { Badge } from '@/components/DataTable';
import { Dialog } from '@/components/Dialog';
import { Alert, Button, Card, Field, cx } from '@/components/ui';

interface ModerationRow {
  id: number;
  prompt: string;
  text: string;
  withheld: boolean;
  withheld_reason: string | null;
  subject_code: string;
  class_label: string;
  faculty_name: string;
}

const PROMPT_LABEL: Record<string, string> = {
  helped: 'What helped',
  change: 'What to change',
};

/**
 * The moderation queue.
 *
 * A comment about somebody's appearance, accent, gender or caste is not
 * feedback about teaching, and someone has to be able to take it down before
 * the person it targets reads it. This is also real access to student writing,
 * which is why withholding requires a reason and is recorded against whoever
 * did it — and why it is reversible.
 */
export function ModerationPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<'all' | 'withheld'>('all');
  const [target, setTarget] = useState<ModerationRow | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const comments = useQuery({
    queryKey: ['moderation', filter],
    queryFn: () =>
      api.get<ModerationRow[]>(
        '/comments',
        filter === 'withheld' ? { withheld: true } : undefined,
      ),
  });

  const act = useMutation({
    mutationFn: ({ id, action, why }: { id: number; action: 'withhold' | 'restore'; why?: string }) =>
      api.post(`/comments/${id}/${action}`, action === 'withhold' ? { reason: why } : undefined),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['moderation'] });
      void queryClient.invalidateQueries({ queryKey: ['report'] });
    },
  });

  async function confirmWithhold() {
    if (target === null) return;
    setError(null);
    try {
      await act.mutateAsync({ id: target.id, action: 'withhold', why: reason });
      setTarget(null);
      setReason('');
    } catch (cause) {
      setError(
        cause instanceof ApiError || cause instanceof Error
          ? cause.message
          : 'Could not withhold that comment.',
      );
    }
  }

  const rows = comments.data ?? [];
  const withheldCount = rows.filter((row) => row.withheld).length;

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <Card
        title="Written feedback"
        actions={
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-ink-600">
              <span>Show</span>
              <select
                value={filter}
                onChange={(event) => setFilter(event.target.value as 'all' | 'withheld')}
                className="rounded-md bg-white px-2 py-1.5 text-sm text-ink-800 ring-1 ring-ink-200"
              >
                <option value="all">Everything</option>
                <option value="withheld">Withheld only</option>
              </select>
            </label>
          </div>
        }
      >
        <p className="mb-4 max-w-prose text-sm text-ink-500">
          Everything students wrote this year. You can read these before the
          instructor can, so that anything abusive can be taken down first.
          Withholding needs a reason, is recorded against your account, and can
          be undone.
        </p>

        {rows.length > 0 ? (
          <p className="mb-3 text-sm text-ink-500">
            {rows.length} comment{rows.length === 1 ? '' : 's'}
            {withheldCount > 0 ? ` · ${withheldCount} withheld` : ''}
          </p>
        ) : null}

        {comments.isLoading ? (
          <p className="py-6 text-center text-sm text-ink-400" role="status">
            Loading...
          </p>
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-400">
            {filter === 'withheld'
              ? 'Nothing has been withheld.'
              : 'No written feedback yet.'}
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {rows.map((row) => (
              <li
                key={row.id}
                className={cx(
                  'rounded-lg border p-4',
                  row.withheld
                    ? 'border-critical-600 bg-critical-100/30'
                    : 'border-ink-200',
                )}
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
                    <Badge>{PROMPT_LABEL[row.prompt] ?? row.prompt}</Badge>
                    <span>{row.subject_code}</span>
                    <span>·</span>
                    <span>{row.class_label}</span>
                    <span>·</span>
                    <span>{row.faculty_name}</span>
                  </div>

                  {row.withheld ? (
                    <Button
                      variant="ghost"
                      loading={act.isPending}
                      onClick={() =>
                        void act.mutateAsync({ id: row.id, action: 'restore' })
                      }
                    >
                      Restore
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      className="text-critical-600"
                      onClick={() => {
                        setTarget(row);
                        setReason('');
                        setError(null);
                      }}
                    >
                      Withhold
                    </Button>
                  )}
                </div>

                <p className="text-sm text-ink-700">{row.text}</p>

                {row.withheld && row.withheld_reason ? (
                  <p className="mt-2 text-xs text-critical-600">
                    Withheld — {row.withheld_reason}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Dialog
        open={target !== null}
        title="Withhold this comment"
        onClose={() => setTarget(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={confirmWithhold}
              loading={act.isPending}
              disabled={reason.trim().length < 3}
            >
              Withhold
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {target ? (
            <blockquote className="rounded-md bg-ink-50 p-3 text-sm text-ink-700">
              {target.text}
            </blockquote>
          ) : null}
          <Field
            label="Why"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Personal remark, not about teaching"
            hint="Recorded against your account. Moderation without a stated reason is indistinguishable from removing criticism someone found inconvenient."
            required
          />
        </div>
      </Dialog>
    </div>
  );
}
