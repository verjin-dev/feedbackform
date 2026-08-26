import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '@/api/client';
import type { FacultyReport } from '@/api/types';
import { Badge } from '@/components/DataTable';
import { ConfirmDialog } from '@/components/Dialog';
import { Alert, Button, Card } from '@/components/ui';

interface PulseRound {
  round_id: number;
  assignment_id: number;
  subject_code: string;
  subject_name: string;
  class_label: string;
  is_open: boolean;
  opened_at: string;
  closed_at: string | null;
  eligible: number;
  replies: number;
  released: boolean;
  pace_counts: Record<string, number>;
  clarity_mean: number | null;
  suggestions: string[];
}

const PACE_LABELS: Record<string, string> = {
  '1': 'Much too slow',
  '2': 'A little slow',
  '3': 'About right',
  '4': 'A little fast',
  '5': 'Much too fast',
};

/** Pace is a spread, not a score — there is no good end of this scale. */
function PaceBars({ counts, total }: { counts: Record<string, number>; total: number }) {
  if (total === 0) return null;

  return (
    <ul className="flex flex-col gap-1">
      {(['1', '2', '3', '4', '5'] as const).map((key) => {
        const value = counts[key] ?? 0;
        const share = (value / total) * 100;
        return (
          <li key={key} className="flex items-center gap-2 text-xs">
            <span className="w-24 shrink-0 text-muted">{PACE_LABELS[key]}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-sunken">
              <span
                className={key === '3' ? 'block h-full bg-brand' : 'block h-full bg-accent-400'}
                style={{ width: `${share}%` }}
              />
            </span>
            <span className="w-6 text-right tabular-nums text-faint">{value}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The mid-term check.
 *
 * The instructor's own tool. Nobody else can read it and it does not survive
 * the term — both stated on the page, because an instructor who is not sure of
 * that will ask a safe question instead of a useful one.
 */
export function PulsePage() {
  const queryClient = useQueryClient();
  const [discarding, setDiscarding] = useState<PulseRound | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rounds = useQuery({
    queryKey: ['pulse', 'mine'],
    queryFn: () => api.get<PulseRound[]>('/pulse/mine'),
    retry: false,
  });

  // The subjects this person teaches, so a check can be started from here
  // rather than sending them somewhere else to do it.
  const mine = useQuery({
    queryKey: ['my-report'],
    queryFn: () => api.get<FacultyReport>('/reports/me'),
    retry: false,
  });

  const start = useMutation({
    mutationFn: (assignmentId: number) =>
      api.post<PulseRound>('/pulse/rounds', { assignment_id: assignmentId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['pulse'] }),
  });

  const act = useMutation({
    mutationFn: async ({
      action,
      id,
    }: {
      action: 'close' | 'discard';
      id: number;
    }) =>
      action === 'close'
        ? api.post(`/pulse/rounds/${id}/close`)
        : api.delete(`/pulse/rounds/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['pulse'] }),
  });

  async function run(action: 'close' | 'discard', id: number) {
    setError(null);
    try {
      await act.mutateAsync({ action, id });
      setDiscarding(null);
    } catch (cause) {
      setError(
        cause instanceof ApiError || cause instanceof Error
          ? cause.message
          : 'That did not work.',
      );
    }
  }

  const data = rounds.data ?? [];
  const withOpenRound = new Set(
    data.filter((round) => round.is_open).map((round) => round.assignment_id),
  );
  const startable = (mine.data?.assignments ?? []).filter(
    (assignment) => !withOpenRound.has(assignment.assignment_id),
  );

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <Card title="Mid-term check">
        <p className="max-w-prose text-sm text-muted">
          A three-question check you can run partway through a subject. Unlike
          the end-of-term evaluation, this one can still change the experience of
          the students who answered it.
        </p>
        <ul className="mt-3 flex list-disc flex-col gap-1 pl-5 text-sm text-muted">
          <li>Only you can see the replies. Not your head of department, not an
            administrator.</li>
          <li>It never appears in your results, an accreditation export, or any
            comparison.</li>
          <li>It is deleted when the term closes, and you can throw it away
            sooner.</li>
        </ul>
      </Card>

      {rounds.isLoading ? (
        <p className="py-6 text-center text-sm text-faint" role="status">
          Loading...
        </p>
      ) : data.length === 0 ? (
        <Card>
          <p className="py-4 text-center text-sm text-faint">
            You have not run one yet. Start a check from any subject on your
            results page.
          </p>
        </Card>
      ) : (
        data.map((round) => (
          <Card
            key={round.round_id}
            title={`${round.subject_code} — ${round.subject_name} · ${round.class_label}`}
            actions={
              <div className="flex items-center gap-2">
                <Badge tone={round.is_open ? 'positive' : 'neutral'}>
                  {round.is_open ? 'Open' : 'Closed'}
                </Badge>
                {round.is_open ? (
                  <Button
                    variant="secondary"
                    onClick={() => void run('close', round.round_id)}
                    loading={act.isPending}
                  >
                    Close it
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  className="text-bad"
                  onClick={() => setDiscarding(round)}
                >
                  Discard
                </Button>
              </div>
            }
          >
            <p className="mb-3 text-sm text-muted">
              {round.replies} of {round.eligible} replied
              {round.is_open ? ' so far' : ''}.
            </p>

            {!round.released ? (
              <Alert tone="caution">
                Replies appear once at least three students have answered. With
                fewer, who said what is too easy to work out.
              </Alert>
            ) : (
              <div className="flex flex-col gap-4">
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-heading">Pace</h3>
                  <PaceBars counts={round.pace_counts} total={round.replies} />
                </div>

                <div>
                  <h3 className="mb-1 text-sm font-semibold text-heading">
                    &ldquo;I know what is expected of me&rdquo;
                  </h3>
                  <p className="text-sm tabular-nums text-body">
                    {round.clarity_mean?.toFixed(2) ?? '—'}{' '}
                    <span className="text-xs text-faint">out of 5</span>
                  </p>
                </div>

                {round.suggestions.length > 0 ? (
                  <div>
                    <h3 className="mb-2 text-sm font-semibold text-heading">
                      One thing that would help right now
                    </h3>
                    <ul className="flex flex-col gap-2">
                      {round.suggestions.map((suggestion, index) => (
                        <li
                          key={index}
                          className="rounded-md bg-sunken p-3 text-sm text-body"
                        >
                          {suggestion}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}
          </Card>
        ))
      )}

      {startable.length > 0 ? (
        <Card title="Start a check">
          <ul className="flex flex-col gap-2">
            {startable.map((assignment) => (
              <li
                key={assignment.assignment_id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-2 last:border-0"
              >
                <span className="text-sm text-body">
                  {assignment.subject_code}{' '}
                  <span className="text-faint">{assignment.class_label}</span>
                </span>
                <Button
                  variant="secondary"
                  loading={start.isPending}
                  onClick={() => void start.mutateAsync(assignment.assignment_id)}
                >
                  Ask my class
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <ConfirmDialog
        open={discarding !== null}
        title="Discard this check"
        confirmLabel="Discard"
        busy={act.isPending}
        message={
          discarding === null ? null : (
            <>
              Delete the {discarding.replies} repl
              {discarding.replies === 1 ? 'y' : 'ies'} to{' '}
              <strong>{discarding.subject_code}</strong>? This cannot be undone —
              which is the point: it is yours to throw away.
            </>
          )
        }
        onConfirm={() => discarding && void run('discard', discarding.round_id)}
        onClose={() => setDiscarding(null)}
      />

    </div>
  );
}
