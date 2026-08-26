import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '@/api/client';
import type { AcademicTerm, FacultyReport } from '@/api/types';
import { Mean, ReportBody } from '@/components/ReportView';
import { TrendPanel } from '@/components/Trend';
import { Alert, Card } from '@/components/ui';

/**
 * What a faculty member sees about their own teaching.
 *
 * Reads /reports/me, which resolves the account from the session. The legacy
 * equivalent posted faculty_id from the page to an unguarded endpoint, so any
 * logged-in session could read any instructor's results by changing a number.
 */
export function ResultsPage() {
  const [termId, setTermId] = useState<number | null>(null);

  const terms = useQuery({
    queryKey: ['my-terms'],
    queryFn: () => api.get<AcademicTerm[]>('/academic-years'),
    // Faculty cannot list academic years — that endpoint is admin-only — so a
    // 403 here is expected and simply means no year picker.
    retry: false,
  });

  const report = useQuery({
    queryKey: ['my-report', termId],
    queryFn: () =>
      api.get<FacultyReport>('/reports/me', termId === null ? undefined : { term_id: termId }),
    retry: false,
  });

  const pickableTerms = terms.error ? [] : (terms.data ?? []);

  if (report.isLoading) {
    return (
      <p className="py-10 text-center text-sm text-faint" role="status">
        Loading...
      </p>
    );
  }

  if (report.error) {
    const conflict = report.error instanceof ApiError && report.error.isConflict;
    return (
      <div className="mx-auto w-full max-w-lg">
        <Card>
          <div className="py-6 text-center">
            <h2 className="text-base font-semibold text-heading">
              {conflict ? 'Not available yet' : 'Could not load your results'}
            </h2>
            <p className="mt-2 text-sm text-muted">
              {conflict
                ? 'No academic year is currently active.'
                : report.error instanceof Error
                  ? report.error.message
                  : 'Please try again.'}
            </p>
          </div>
        </Card>
      </div>
    );
  }

  const data = report.data;
  if (data === undefined) return null;

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <Card
        title="My results"
        actions={
          pickableTerms.length > 1 ? (
            <label className="flex items-center gap-2 text-sm text-muted">
              <span>Academic year</span>
              <select
                value={termId ?? data.term.id}
                onChange={(event) => setTermId(Number(event.target.value))}
                className="rounded-md bg-surface px-2 py-1.5 text-sm text-heading ring-1 ring-line-strong"
              >
                {pickableTerms.map((term) => (
                  <option key={term.id} value={term.id}>
                    {term.year} · semester {term.semester}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="text-sm text-muted">
              {data.term.year} · semester {data.term.semester}
            </span>
          )
        }
      >
        {data.assignments.length === 0 ? (
          <p className="py-6 text-center text-sm text-faint">
            You have no subjects assigned for this year.
          </p>
        ) : (
          <>
            <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <div>
                <dt className="text-xs uppercase text-muted">Across all subjects</dt>
                <dd>
                  <Mean value={data.mean} />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-muted">Subjects</dt>
                <dd className="tabular-nums">{data.assignments.length}</dd>
              </div>
            </dl>

            {data.mean === null ? (
              <div className="mt-4">
                <Alert tone="caution">
                  No feedback has been submitted yet. Results appear here as students
                  respond.
                </Alert>
              </div>
            ) : null}
          </>
        )}
      </Card>

      {/* Placed above the detail: an instructor asking "am I getting
          better?" should not have to scroll past fifteen rows to find out. */}
      <TrendPanel facultyId="me" />

      <ReportBody report={data} />
    </div>
  );
}
