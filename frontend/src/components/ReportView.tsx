import type { AssignmentReport, FacultyReport, QuestionReport } from '@/api/types';
import { Badge } from '@/components/DataTable';
import { Card } from '@/components/ui';

const RATINGS = ['1', '2', '3', '4', '5'] as const;

const SHADES: Record<string, string> = {
  '1': 'bg-critical-600',
  '2': 'bg-caution-600',
  '3': 'bg-ink-300',
  '4': 'bg-accent-300',
  '5': 'bg-accent-500',
};

/**
 * null means nobody answered.
 *
 * Rendering it as 0.00 would read as a unanimous worst score. The legacy
 * report avoided the problem by omitting unanswered questions entirely, which
 * made a barely answered questionnaire look complete.
 */
export function Mean({ value }: { value: number | null }) {
  if (value === null) return <span className="text-ink-400">No responses</span>;
  return <span className="font-medium tabular-nums">{value.toFixed(2)}</span>;
}

export function Rate({ value }: { value: number | null }) {
  if (value === null) return <span className="text-ink-400">&mdash;</span>;
  const percent = value * 100;
  const tone = percent >= 60 ? 'positive' : percent >= 30 ? 'caution' : 'critical';
  return <Badge tone={tone}>{percent.toFixed(0)}%</Badge>;
}

/** The shape of the answers, without making anyone read five numbers. */
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
          (rating) => `${rating} star: ${question.counts[rating] ?? 0}`,
        ).join(', ')}
      >
        {RATINGS.map((rating) => {
          const percent = question.percentages[rating] ?? 0;
          if (percent === 0) return null;
          return (
            <span key={rating} className={SHADES[rating]} style={{ width: `${percent}%` }} />
          );
        })}
      </div>
      <span className="text-xs tabular-nums text-ink-400">n={question.responses}</span>
    </div>
  );
}

export function AssignmentSection({ report }: { report: AssignmentReport }) {
  return (
    <Card title={`${report.subject_code} — ${report.subject_name} · ${report.class_label}`}>
      <dl className="mb-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <dt className="text-xs uppercase text-ink-500">Overall</dt>
          <dd>
            <Mean value={report.mean} />
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-ink-500">Responses</dt>
          <dd className="tabular-nums">
            {report.responses} of {report.eligible_students}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-ink-500">Response rate</dt>
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
                  <tr className="text-left text-xs uppercase text-ink-500">
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
                    <tr key={question.question_id} className="border-t border-ink-100">
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

export function ReportBody({ report }: { report: FacultyReport }) {
  return (
    <>
      {report.assignments.map((assignment) => (
        <AssignmentSection key={assignment.assignment_id} report={assignment} />
      ))}
    </>
  );
}
