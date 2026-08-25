import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '@/api/client';
import { accounts, terms } from '@/api/resources';
import type { AssignmentReport, FacultyReport, QuestionReport } from '@/api/types';
import { Badge } from '@/components/DataTable';
import { Alert, Card } from '@/components/ui';
import { TermPicker, useSelectedTerm } from '@/routes/admin/TermPicker';

const RATINGS = ['1', '2', '3', '4', '5'] as const;

/** null means nobody answered. Rendering it as 0.00 would read as a unanimous
 *  worst score, which is what the legacy report effectively did by omitting
 *  the question entirely. */
export function Mean({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-ink-400">No responses</span>;
  }
  return <span className="font-medium tabular-nums">{value.toFixed(2)}</span>;
}

function Rate({ value }: { value: number | null }) {
  if (value === null) return <span className="text-ink-400">—</span>;
  const percent = value * 100;
  const tone = percent >= 60 ? 'positive' : percent >= 30 ? 'caution' : 'critical';
  return <Badge tone={tone}>{percent.toFixed(0)}%</Badge>;
}

/** A compact distribution bar, so the shape of the answers is visible without
 *  reading five numbers. */
function Distribution({ question }: { question: QuestionReport }) {
  if (question.responses === 0) {
    return <span className="text-xs text-ink-400">No responses</span>;
  }

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex h-2 w-32 overflow-hidden rounded-full bg-ink-100"
        role="img"
        aria-label={RATINGS.map(
          (rating) => `${rating}: ${question.counts[rating] ?? 0}`,
        ).join(', ')}
      >
        {RATINGS.map((rating) => {
          const percent = question.percentages[rating] ?? 0;
          if (percent === 0) return null;
          const shades: Record<string, string> = {
            '1': 'bg-critical-600',
            '2': 'bg-caution-600',
            '3': 'bg-ink-300',
            '4': 'bg-accent-300',
            '5': 'bg-accent-500',
          };
          return (
            <span
              key={rating}
              className={shades[rating]}
              style={{ width: `${percent}%` }}
            />
          );
        })}
      </div>
      <span className="text-xs text-ink-400 tabular-nums">n={question.responses}</span>
    </div>
  );
}

function AssignmentSection({ report }: { report: AssignmentReport }) {
  return (
    <Card
      title={`${report.subject_code} — ${report.subject_name} · ${report.class_label}`}
    >
      <dl className="mb-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <dt className="text-xs text-ink-500 uppercase">Overall</dt>
          <dd>
            <Mean value={report.mean} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-500 uppercase">Responses</dt>
          <dd className="tabular-nums">
            {report.responses} of {report.eligible_students}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-500 uppercase">Response rate</dt>
          <dd>
            <Rate value={report.response_rate} />
          </dd>
        </div>
      </dl>

      <div className="flex flex-col gap-5">
        {report.criteria.map((criterion) => (
          <section key={criterion.criterion_id}>
            <header className="mb-2 flex items-baseline justify-between border-b border-ink-100 pb-1">
              <h3 className="text-sm font-semibold text-ink-800">{criterion.name}</h3>
              <Mean value={criterion.mean} />
            </header>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-500 uppercase">
                    <th scope="col" className="py-1 font-medium">
                      Question
                    </th>
                    <th scope="col" className="py-1 font-medium">
                      Distribution
                    </th>
                    <th scope="col" className="py-1 text-right font-medium">
                      Mean
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {criterion.questions.map((question) => (
                    <tr
                      key={question.question_id}
                      className="border-t border-ink-100 align-middle"
                    >
                      <td className="py-2 pr-4 text-ink-700">{question.text}</td>
                      <td className="py-2 pr-4">
                        <Distribution question={question} />
                      </td>
                      <td className="py-2 text-right">
                        <Mean value={question.mean} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </Card>
  );
}

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

      {report.data?.assignments.map((assignment) => (
        <AssignmentSection key={assignment.assignment_id} report={assignment} />
      ))}
    </div>
  );
}
