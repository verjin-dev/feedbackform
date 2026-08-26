import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '@/api/client';
import { Badge, DataTable } from '@/components/DataTable';
import { Alert, Button, Card, cx } from '@/components/ui';

interface ClassProgress {
  class_group_id: number;
  label: string;
  students: number;
  assignments: number;
  completed: number;
  partial: number;
  not_started: number;
  completion: number | null;
}

interface OutstandingPerson {
  account_id: number;
  name: string;
  email: string;
  outstanding: number;
  subjects: string[];
  last_reminded: string | null;
}

interface ReminderResult {
  dry_run: boolean;
  recipients: number;
  outstanding_total: number;
  suppressed_by_cooldown: number;
  people: OutstandingPerson[];
}

function pct(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`;
}

function toneFor(value: number | null) {
  if (value === null) return 'neutral' as const;
  const percent = value * 100;
  return percent >= 60 ? 'positive' : percent >= 30 ? 'caution' : 'critical';
}

/** A completion bar that shows the split, not just the total. */
function ProgressBar({ row }: { row: ClassProgress }) {
  const total = Math.max(row.students, 1);
  const parts = [
    { key: 'done', width: (row.completed / total) * 100, className: 'bg-brand' },
    { key: 'part', width: (row.partial / total) * 100, className: 'bg-accent-400' },
  ];

  return (
    <div
      className="flex h-2.5 w-full min-w-32 overflow-hidden rounded-full bg-sunken"
      role="img"
      aria-label={`${row.completed} finished, ${row.partial} partway, ${row.not_started} not started, of ${row.students}`}
    >
      {parts.map((part) =>
        part.width > 0 ? (
          <span key={part.key} className={part.className} style={{ width: `${part.width}%` }} />
        ) : null,
      )}
    </div>
  );
}

export function ParticipationPage() {
  const queryClient = useQueryClient();
  const [classId, setClassId] = useState<number | null>(null);
  const [preview, setPreview] = useState<ReminderResult | null>(null);
  const [sent, setSent] = useState<ReminderResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showQr, setShowQr] = useState(false);

  const progress = useQuery({
    queryKey: ['participation', 'progress'],
    queryFn: () => api.get<ClassProgress[]>('/participation/progress'),
  });

  const reminders = useMutation({
    mutationFn: ({ dryRun, ignoreCooldown = false }: { dryRun: boolean; ignoreCooldown?: boolean }) =>
      api.post<ReminderResult>(
        `/participation/reminders?dry_run=${dryRun}&ignore_cooldown=${ignoreCooldown}` +
          (classId === null ? '' : `&class_group_id=${classId}`),
      ),
  });

  async function run(dryRun: boolean, ignoreCooldown = false) {
    setError(null);
    try {
      const result = await reminders.mutateAsync({ dryRun, ignoreCooldown });
      if (dryRun) {
        setPreview(result);
        setSent(null);
      } else {
        setSent(result);
        setPreview(null);
        void queryClient.invalidateQueries({ queryKey: ['participation'] });
      }
    } catch (cause) {
      setError(
        cause instanceof ApiError || cause instanceof Error
          ? cause.message
          : 'Could not work out who to remind.',
      );
    }
  }

  const report = sent ?? preview;
  const overall = progress.data?.reduce(
    (acc, row) => ({
      students: acc.students + row.students,
      completed: acc.completed + row.completed,
    }),
    { students: 0, completed: 0 },
  );

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <Card
        title="Participation"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={() => setShowQr((open) => !open)}>
              {showQr ? 'Hide code' : 'Show scannable code'}
            </Button>
            <Button onClick={() => void run(true)} loading={reminders.isPending}>
              Who needs reminding?
            </Button>
          </div>
        }
      >
        <p className="mb-4 max-w-prose text-sm text-muted">
          Response rate decides whether the results mean anything. A report built
          on a fifth of the class is a well-presented guess, so this is the
          number worth moving.
        </p>

        {overall && overall.students > 0 ? (
          <div className="mb-4 flex flex-wrap gap-x-8 gap-y-2">
            <div>
              <div className="text-xs uppercase text-muted">Finished everything</div>
              <div className="text-2xl font-semibold tabular-nums text-heading">
                {overall.completed}
                <span className="text-base font-normal text-faint">
                  {' '}
                  of {overall.students}
                </span>
              </div>
            </div>
            <div>
              <div className="text-xs uppercase text-muted">Overall</div>
              <div className="mt-1">
                <Badge tone={toneFor(overall.completed / overall.students)}>
                  {pct(overall.completed / overall.students)}
                </Badge>
              </div>
            </div>
          </div>
        ) : null}

        {showQr ? (
          <div className="mb-4 flex flex-col items-center gap-2 rounded-lg border border-line-strong p-5">
            {/* Put this on a slide. Scanning from a seat is a much lower bar
                than remembering a URL later, and that gap is most of the
                response rate. */}
            <img
              src="/api/participation/qr.svg?scale=8"
              alt="Scan to open the feedback form"
              className="h-48 w-48"
            />
            <p className="text-sm text-muted">Scan to open the feedback form</p>
            <Button variant="ghost" onClick={() => window.print()}>
              Print this
            </Button>
          </div>
        ) : null}

        <DataTable
          rows={progress.data}
          rowKey={(row) => row.class_group_id}
          isLoading={progress.isLoading}
          error={progress.error}
          empty="No classes have subjects assigned this year."
          columns={[
            { header: 'Class', cell: (row) => row.label },
            { header: 'Subjects each', cell: (row) => row.assignments, numeric: true },
            { header: 'Students', cell: (row) => row.students, numeric: true },
            { header: 'Progress', cell: (row) => <ProgressBar row={row} /> },
            {
              header: 'Finished',
              cell: (row) => (
                <span className="tabular-nums">
                  {row.completed} / {row.students}
                </span>
              ),
              numeric: true,
            },
            {
              header: 'Rate',
              cell: (row) => <Badge tone={toneFor(row.completion)}>{pct(row.completion)}</Badge>,
              numeric: true,
            },
          ]}
          actions={(row) => (
            <Button
              variant="ghost"
              onClick={() => {
                setClassId(row.class_group_id);
                void run(true);
              }}
              disabled={row.completed === row.students}
            >
              Remind
            </Button>
          )}
        />
      </Card>

      {report ? (
        <Card
          title={sent ? 'Reminders sent' : 'Who would be reminded'}
          actions={
            sent ? null : (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setPreview(null);
                    setClassId(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => void run(false)}
                  loading={reminders.isPending}
                  disabled={report.recipients === 0}
                >
                  Send {report.recipients} reminder{report.recipients === 1 ? '' : 's'}
                </Button>
              </div>
            )
          }
        >
          {report.recipients === 0 && report.suppressed_by_cooldown > 0 ? (
            <div className="mb-4">
              <Alert tone="caution">
                {report.outstanding_total} student
                {report.outstanding_total === 1 ? ' is' : 's are'} still outstanding,
                but all of them were reminded in the last few days. Reminding people
                daily trains them to ignore the message — wait, or override the
                pause if the window closes today.
              </Alert>
              <div className="mt-2">
                <Button variant="secondary" onClick={() => void run(true, true)}>
                  Show them anyway
                </Button>
              </div>
            </div>
          ) : null}

          {report.recipients === 0 && report.suppressed_by_cooldown === 0 ? (
            <Alert tone="positive">
              Nobody is outstanding — everyone in scope has finished.
            </Alert>
          ) : null}

          {report.recipients > 0 ? (
            <>
              <p className="mb-3 text-sm text-muted">
                {sent
                  ? `${report.recipients} email${report.recipients === 1 ? '' : 's'} sent, each listing only the subjects that person still owes.`
                  : `Each person is emailed once, listing only the subjects they still owe.`}
                {report.suppressed_by_cooldown > 0
                  ? ` ${report.suppressed_by_cooldown} more held back — reminded recently.`
                  : ''}
              </p>
              <DataTable
                rows={report.people}
                rowKey={(row) => row.account_id}
                columns={[
                  { header: 'Student', cell: (row) => row.name },
                  { header: 'Email', cell: (row) => row.email },
                  { header: 'Owed', cell: (row) => row.outstanding, numeric: true },
                  {
                    header: 'Subjects',
                    cell: (row) => (
                      <div className="flex flex-col gap-0.5">
                        {row.subjects.map((subject) => (
                          <span key={subject} className="text-xs text-muted">
                            {subject}
                          </span>
                        ))}
                      </div>
                    ),
                  },
                  {
                    header: 'Last reminded',
                    cell: (row) => (
                      <span className={cx('text-xs', row.last_reminded ? 'text-muted' : 'text-faint')}>
                        {row.last_reminded
                          ? new Date(row.last_reminded).toLocaleDateString()
                          : 'never'}
                      </span>
                    ),
                  },
                ]}
              />
            </>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}
