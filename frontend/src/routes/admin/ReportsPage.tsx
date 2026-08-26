import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '@/api/client';
import { accounts, terms } from '@/api/resources';
import type { FacultyReport } from '@/api/types';
import { Mean, ReportBody } from '@/components/ReportView';
import { TrendPanel } from '@/components/Trend';
import { Alert, Card } from '@/components/ui';
import { TermPicker, useSelectedTerm } from '@/routes/admin/TermPicker';

export function ReportsPage() {
  const termList = terms.useList();
  const { termId, setTermId } = useSelectedTerm(termList.data);
  const facultyList = accounts.useList({ role: 'faculty' });
  const [facultyId, setFacultyId] = useState<number | null>(null);

  const report = useQuery({
    queryKey: ['report', 'faculty', facultyId, termId],
    queryFn: () =>
      api.get<FacultyReport>(`/reports/faculty/${facultyId}`, {
        term_id: termId ?? undefined,
      }),
    enabled: facultyId !== null && termId !== null,
  });

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Reports"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <TermPicker terms={termList.data} value={termId} onChange={setTermId} />
            <label className="flex items-center gap-2 text-sm text-ink-600">
              <span>Faculty</span>
              <select
                value={facultyId ?? ''}
                onChange={(event) =>
                  setFacultyId(event.target.value === '' ? null : Number(event.target.value))
                }
                className="rounded-md bg-white px-2 py-1.5 text-sm text-ink-800 ring-1 ring-ink-200"
              >
                <option value="">Select a faculty member</option>
                {facultyList.data?.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.full_name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        }
      >
        {facultyId === null ? (
          <p className="py-6 text-center text-sm text-ink-400">
            Select a faculty member to see their results.
          </p>
        ) : report.isLoading ? (
          <p className="py-6 text-center text-sm text-ink-400" role="status">
            Loading...
          </p>
        ) : report.error ? (
          <Alert>
            {report.error instanceof Error
              ? report.error.message
              : 'Could not load this report.'}
          </Alert>
        ) : report.data && report.data.assignments.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-400">
            {report.data.faculty_name} has no assignments this year.
          </p>
        ) : report.data ? (
          <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <div>
              <dt className="text-xs text-ink-500 uppercase">Faculty</dt>
              <dd className="font-medium">{report.data.faculty_name}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-500 uppercase">Overall across subjects</dt>
              <dd>
                <Mean value={report.data.mean} />
              </dd>
            </div>
          </dl>
        ) : null}
      </Card>

      {facultyId !== null ? <TrendPanel facultyId={facultyId} /> : null}

      {report.data ? <ReportBody report={report.data} /> : null}
    </div>
  );
}
