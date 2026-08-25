import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { accounts, classes, subjects, terms } from '@/api/resources';
import type { AcademicTerm } from '@/api/types';
import { Badge, DataTable } from '@/components/DataTable';
import { Alert, Card } from '@/components/ui';
// The dashboard is deliberately about the current term only; the other
// screens offer a picker because they are used for past years too.
import { useSelectedTerm } from '@/routes/admin/TermPicker';

interface ResponseRateRow {
  assignment_id: number;
  faculty_id: number;
  faculty_name: string;
  subject_code: string;
  class_label: string;
  eligible_students: number;
  responses: number;
  response_rate: number | null;
}

interface ResponseRateReport {
  term: Pick<AcademicTerm, 'id' | 'year' | 'semester' | 'status'>;
  rows: ResponseRateRow[];
  eligible_students: number;
  responses: number;
  response_rate: number | null;
}

const STATUS_TONE = {
  pending: 'caution',
  open: 'positive',
  closed: 'neutral',
} as const;

const STATUS_LABEL = {
  pending: 'Not started',
  open: 'Open',
  closed: 'Closed',
} as const;

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-white px-4 py-3 ring-1 ring-ink-200">
      <div className="text-xs tracking-wide text-ink-500 uppercase">{label}</div>
      <div className="mt-0.5 text-2xl font-semibold tabular-nums text-ink-900">
        {value}
      </div>
    </div>
  );
}

function rateOf(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(0)}%`;
}

/**
 * Replaces admin/home.php, which showed four SELECT * row counts.
 *
 * The number that actually matters during an evaluation window is the response
 * rate, and the legacy dashboard had no concept of a denominator at all, so
 * there was no way to tell a well-answered questionnaire from a barely
 * answered one.
 */
export function OverviewPage() {
  const termList = terms.useList();
  const { termId, term } = useSelectedTerm(termList.data);

  const facultyList = accounts.useList({ role: 'faculty' });
  const studentList = accounts.useList({ role: 'student' });
  const classList = classes.useList();
  const subjectList = subjects.useList();

  const rates = useQuery({
    queryKey: ['response-rates', termId],
    queryFn: () =>
      api.get<ResponseRateReport>('/reports/response-rates', {
        term_id: termId ?? undefined,
      }),
    enabled: termId !== null,
  });

  const lowest = [...(rates.data?.rows ?? [])]
    .filter((row) => row.response_rate !== null)
    .sort((a, b) => (a.response_rate ?? 0) - (b.response_rate ?? 0))
    .slice(0, 5);

  return (
    <div className="flex flex-col gap-4">
      {term === null && !termList.isLoading ? (
        <Alert tone="caution">
          No academic year has been set up yet. Create one and make it current
          before anything else will work.
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Faculty" value={facultyList.data?.length ?? '—'} />
        <Stat label="Students" value={studentList.data?.length ?? '—'} />
        <Stat label="Classes" value={classList.data?.length ?? '—'} />
        <Stat label="Subjects" value={subjectList.data?.length ?? '—'} />
      </div>

      <Card
        title="Participation this year"
        actions={
          term ? (
            <div className="flex items-center gap-3">
              <Badge tone={STATUS_TONE[term.status]}>{STATUS_LABEL[term.status]}</Badge>
              <span className="text-sm text-ink-500">
                {term.year} · semester {term.semester}
              </span>
            </div>
          ) : null
        }
      >
        {rates.error ? (
          <Alert>
            {rates.error instanceof Error
              ? rates.error.message
              : 'Could not load participation.'}
          </Alert>
        ) : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3">
              <Stat
                label="Responses"
                value={rates.data ? rates.data.responses : '—'}
              />
              <Stat
                label="Expected"
                value={rates.data ? rates.data.eligible_students : '—'}
              />
              <Stat
                label="Overall rate"
                value={rates.data ? rateOf(rates.data.response_rate) : '—'}
              />
            </div>

            {/* Surfacing the weakest first is the point: a mean across
                everything hides the classes nobody answered. */}
            <h3 className="mb-2 text-sm font-semibold text-ink-800">
              Lowest response rates
            </h3>
            <DataTable
              rows={lowest}
              columns={[
                { header: 'Faculty', cell: (row) => row.faculty_name },
                { header: 'Subject', cell: (row) => row.subject_code },
                { header: 'Class', cell: (row) => row.class_label },
                {
                  header: 'Responses',
                  cell: (row) => `${row.responses} / ${row.eligible_students}`,
                  numeric: true,
                },
                {
                  header: 'Rate',
                  cell: (row) => {
                    const percent = (row.response_rate ?? 0) * 100;
                    const tone =
                      percent >= 60 ? 'positive' : percent >= 30 ? 'caution' : 'critical';
                    return <Badge tone={tone}>{rateOf(row.response_rate)}</Badge>;
                  },
                  numeric: true,
                },
              ]}
              rowKey={(row) => row.assignment_id}
              isLoading={rates.isLoading}
              empty="No assignments with an expected roll yet."
            />
          </>
        )}
      </Card>
    </div>
  );
}
