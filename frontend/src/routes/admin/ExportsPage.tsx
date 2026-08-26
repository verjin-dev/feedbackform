import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '@/api/client';
import { terms } from '@/api/resources';
import type { AssignmentReport } from '@/api/types';
import { Mean, Rate } from '@/components/ReportView';
import { Alert, Button, Card } from '@/components/ui';
import { TermPicker, useSelectedTerm } from '@/routes/admin/TermPicker';

interface Summary {
  institution: string;
  term: { id: number; year: string; semester: number; label: string; status: string };
  curriculum: string | null;
  generated_at: string;
  criteria: number;
  questions: number;
  assignments: number;
  faculty: number;
  classes: number;
  students_eligible: number;
  responses: number;
  response_rate: number | null;
  assignments_with_published_means: number;
  assignments_below_threshold: number;
  minimum_responses_for_mean: number;
  assignment_reports: (AssignmentReport & { faculty_name: string; curriculum: string })[];
}

function query(termId: number | null, curriculum: string | null): string {
  const parts: string[] = [];
  if (termId !== null) parts.push(`term_id=${termId}`);
  if (curriculum) parts.push(`curriculum=${encodeURIComponent(curriculum)}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

/**
 * The accreditation return.
 *
 * Three CSVs for an assessor who wants to check the arithmetic, and a printable
 * cover page for the file itself. The PDF comes from the browser's own print
 * dialogue rather than a server-side renderer — it keeps one stylesheet as the
 * source of truth for how this looks, and avoids a rendering dependency that
 * would have to be kept alive for a document produced twice a year.
 */
export function ExportsPage() {
  const termList = terms.useList();
  const { termId } = useSelectedTerm(termList.data);
  const [curriculum, setCurriculum] = useState<string>('');

  const curricula = useQuery({
    queryKey: ['exports', 'curricula'],
    queryFn: () => api.get<string[]>('/exports/curricula'),
  });

  const summary = useQuery({
    queryKey: ['exports', 'summary', termId, curriculum],
    queryFn: () =>
      api.get<Summary>('/exports/summary', {
        term_id: termId ?? undefined,
        curriculum: curriculum || undefined,
      }),
    enabled: termId !== null,
  });

  const suffix = query(termId, curriculum || null);
  const files = [
    {
      href: `/api/exports/questionnaire.csv${query(termId, null)}`,
      label: 'Questionnaire',
      note: 'The questions actually asked, in order. What the results were collected against.',
    },
    {
      href: `/api/exports/participation.csv${suffix}`,
      label: 'Participation',
      note: 'Responses against class size, per subject. The denominator an assessor asks for.',
    },
    {
      href: `/api/exports/results.csv${suffix}`,
      label: 'Results',
      note: 'One row per question with the raw counts, so any average can be recomputed.',
    },
  ];

  const data = summary.data;

  return (
    <div className="flex flex-col gap-4">
      {/* Screen only — the printed page is the report, not the controls. */}
      <div className="print:hidden">
        <Card
          title="Accreditation export"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <TermPicker
                terms={termList.data}
                value={termId}
                onChange={() => undefined}
              />
              <label className="flex items-center gap-2 text-sm text-ink-600">
                <span>Curriculum</span>
                <select
                  value={curriculum}
                  onChange={(event) => setCurriculum(event.target.value)}
                  className="rounded-md bg-white px-2 py-1.5 text-sm text-ink-800 ring-1 ring-ink-200"
                >
                  <option value="">All</option>
                  {curricula.data?.map((entry) => (
                    <option key={entry} value={entry}>
                      {entry}
                    </option>
                  ))}
                </select>
              </label>
              <Button onClick={() => window.print()} disabled={!data}>
                Print the cover page
              </Button>
            </div>
          }
        >
          <p className="mb-4 max-w-prose text-sm text-ink-500">
            Files for an NBA or NAAC return. The CSVs carry the raw counts, so an
            assessor can recompute any figure rather than taking it on trust. The
            cover page prints from your browser.
          </p>

          <div className="grid gap-3 md:grid-cols-3">
            {files.map((file) => (
              <a
                key={file.label}
                href={file.href}
                className="flex flex-col gap-1 rounded-lg border border-ink-200 p-4 transition-colors hover:border-accent-500 hover:bg-accent-50"
              >
                <span className="text-sm font-medium text-ink-800">
                  {file.label} <span className="text-ink-400">.csv</span>
                </span>
                <span className="text-xs text-ink-500">{file.note}</span>
              </a>
            ))}
          </div>

          {/* The number an assessor should be told rather than left to infer
              from blank cells. */}
          {data && data.assignments_below_threshold > 0 ? (
            <div className="mt-4">
              <Alert tone="caution">
                {data.assignments_below_threshold} of {data.assignments} subject
                {data.assignments === 1 ? '' : 's'} had fewer than{' '}
                {data.minimum_responses_for_mean} responses, so no average is
                published for them. The counts are still exported, and the reason
                is stated on every affected row.
              </Alert>
            </div>
          ) : null}
        </Card>
      </div>

      {data ? (
        <article className="rounded-lg bg-white p-8 ring-1 ring-ink-200 print:p-0 print:ring-0">
          <header className="border-b-2 border-ink-800 pb-3">
            <h1 className="text-2xl font-semibold text-ink-900">{data.institution}</h1>
            <p className="mt-1 text-ink-600">
              Student feedback on teaching — {data.term.label}
              {data.curriculum ? ` · ${data.curriculum}` : ''}
            </p>
            <p className="mt-1 text-xs text-ink-500">
              Generated {new Date(data.generated_at).toLocaleString()}
            </p>
          </header>

          <section className="mt-5">
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-ink-800 uppercase">
              Coverage
            </h2>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm md:grid-cols-4">
              <Figure label="Faculty" value={data.faculty} />
              <Figure label="Subjects reviewed" value={data.assignments} />
              <Figure label="Classes" value={data.classes} />
              <Figure label="Questions asked" value={data.questions} />
              <Figure label="Students eligible" value={data.students_eligible} />
              <Figure label="Responses" value={data.responses} />
              <div>
                <dt className="text-xs uppercase text-ink-500">Response rate</dt>
                <dd className="mt-0.5">
                  <Rate value={data.response_rate} />
                </dd>
              </div>
            </dl>
          </section>

          <section className="mt-6">
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-ink-800 uppercase">
              Results by subject
            </h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-300 text-left text-xs uppercase text-ink-500">
                  <th className="py-1 font-medium">Faculty</th>
                  <th className="py-1 font-medium">Subject</th>
                  <th className="py-1 font-medium">Class</th>
                  <th className="py-1 text-right font-medium">Responses</th>
                  <th className="py-1 text-right font-medium">Rate</th>
                  <th className="py-1 text-right font-medium">Mean</th>
                </tr>
              </thead>
              <tbody>
                {data.assignment_reports.map((row) => (
                  <tr
                    key={row.assignment_id}
                    className="border-b border-ink-100 break-inside-avoid"
                  >
                    <td className="py-1.5">{row.faculty_name}</td>
                    <td className="py-1.5">{row.subject_code}</td>
                    <td className="py-1.5">{row.class_label}</td>
                    <td className="py-1.5 text-right tabular-nums">
                      {row.responses} / {row.eligible_students}
                    </td>
                    <td className="py-1.5 text-right">
                      <Rate value={row.response_rate} />
                    </td>
                    <td className="py-1.5 text-right">
                      <Mean value={row.mean} responses={row.responses} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="mt-6 text-xs text-ink-500">
            <h2 className="mb-1 text-sm font-semibold tracking-wide text-ink-800 uppercase">
              Method
            </h2>
            <p className="max-w-prose">
              Every student in a class is asked to rate each subject they are
              taught, on a five-point scale, against {data.criteria} criteri
              {data.criteria === 1 ? 'on' : 'a'} covering {data.questions} question
              {data.questions === 1 ? '' : 's'}. Responses are recorded without any
              link to the student who gave them, and instructors see only combined
              results for a whole class.
            </p>
            <p className="mt-2 max-w-prose">
              No average is published where fewer than{' '}
              {data.minimum_responses_for_mean} students responded, because a mean
              of that few opinions claims a precision it does not have. The counts
              for those subjects are still included in the accompanying files.
            </p>
          </section>
        </article>
      ) : null}
    </div>
  );
}

function Figure({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-xs uppercase text-ink-500">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-ink-900">{value}</dd>
    </div>
  );
}
