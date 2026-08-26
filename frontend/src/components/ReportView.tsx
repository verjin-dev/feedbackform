import type {
  AssignmentReport,
  CohortBand,
  CommentState,
  FacultyReport,
  QuestionReport,
  Reliability,
} from '@/api/types';
import { Badge } from '@/components/DataTable';
import { Alert, Card } from '@/components/ui';

const RATINGS = ['1', '2', '3', '4', '5'] as const;

// Mid-tones throughout. These are data rather than chrome, so they have to
// stay separable from one another and stay ordered as a ramp on both a light
// and a dark ground -- which the very light and very dark steps do not.
const SHADES: Record<string, string> = {
  '1': 'bg-critical-500',
  '2': 'bg-caution-500',
  '3': 'bg-ink-400',
  '4': 'bg-accent-400',
  '5': 'bg-brand',
};

/**
 * A mean, or an explanation of why there isn't one.
 *
 * `mean` is null in two different situations and they must not look alike:
 * nobody answered, or too few answered for a figure to be honest. Rendering
 * either as 0.00 would read as a unanimous worst score; rendering either as a
 * blank cell hides that data exists.
 */
export function Mean({
  value,
  responses,
  range,
}: {
  value: number | null;
  responses?: number;
  range?: [number, number] | null;
}) {
  if (value === null) {
    if (responses !== undefined && responses > 0) {
      return (
        <span className="text-faint">
          Too few to average
          <span className="ml-1 tabular-nums">({responses})</span>
        </span>
      );
    }
    return <span className="text-faint">No responses</span>;
  }

  return (
    <span className="whitespace-nowrap">
      <span className="font-medium tabular-nums">{value.toFixed(2)}</span>
      {range && range[1] - range[0] > 0.01 ? (
        <span className="ml-1 text-xs tabular-nums text-faint">
          ({range[0].toFixed(1)}–{range[1].toFixed(1)})
        </span>
      ) : null}
    </span>
  );
}

export function Rate({ value }: { value: number | null }) {
  if (value === null) return <span className="text-faint">&mdash;</span>;
  const percent = value * 100;
  const tone = percent >= 60 ? 'positive' : percent >= 30 ? 'caution' : 'critical';
  return <Badge tone={tone}>{percent.toFixed(0)}%</Badge>;
}

/** States plainly how much weight the numbers below can carry. */
export function ReliabilityNote({
  reliability,
  responses,
  eligible,
}: {
  reliability: Reliability;
  responses: number;
  eligible: number;
}) {
  if (reliability === 'adequate') return null;

  if (reliability === 'insufficient') {
    return (
      <Alert tone="caution">
        {responses === 0
          ? 'Nobody has responded yet, so there is nothing to average.'
          : `Only ${responses} ${responses === 1 ? 'person has' : 'people have'} responded. That is too few to publish an average — the distributions below show what was said, but one more answer would move any figure substantially.`}
      </Alert>
    );
  }

  return (
    <Alert tone="caution">
      {responses} of {eligible} students responded. The averages below are real,
      but they come from a minority of the class and may not represent it.
    </Alert>
  );
}

/** The shape of the answers, without making anyone read five numbers. */
function Distribution({ question }: { question: QuestionReport }) {
  if (question.responses === 0) {
    return <span className="text-xs text-faint">No responses</span>;
  }

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex h-2 w-32 overflow-hidden rounded-full bg-sunken"
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
      <span className="text-xs tabular-nums text-faint">n={question.responses}</span>
    </div>
  );
}

/**
 * A score against the middle half of what comparable subjects scored.
 *
 * A band, deliberately, and not a position. The question worth answering is
 * "is 4.2 good?"; the question this must never answer is "who is worst?".
 * Nobody else is named, and no percentile is shown — a percentile is a ranking
 * with one row visible.
 */
function CohortContext({
  band,
  mean,
}: {
  band: CohortBand | null;
  mean: number | null;
}) {
  if (band === null || mean === null) return null;

  // Fixed to the rating scale, like the sparklines, so a narrow band looks
  // narrow rather than being stretched to fill the bar.
  const MIN = 1;
  const MAX = 5;
  const place = (value: number) => ((value - MIN) / (MAX - MIN)) * 100;

  const left = place(band.p25);
  const width = Math.max(place(band.p75) - left, 0.6);
  const marker = place(mean);

  const where =
    mean > band.p75
      ? 'above the middle half'
      : mean < band.p25
        ? 'below the middle half'
        : 'within the middle half';

  return (
    <div className="mt-3">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs uppercase text-muted">In context</span>
        <span className="text-xs text-muted">{band.basis}</span>
      </div>

      <div
        className="relative h-6 w-full rounded-md bg-sunken"
        role="img"
        aria-label={`This subject scored ${mean.toFixed(2)}, ${where} of comparable subjects, which ran from ${band.p25.toFixed(2)} to ${band.p75.toFixed(2)} with a middle value of ${band.median.toFixed(2)}. Based on ${band.basis}.`}
      >
        {/* The middle half. */}
        <div
          className="absolute inset-y-1 rounded-sm bg-brand-soft"
          style={{ left: `${left}%`, width: `${width}%` }}
        />
        {/* The middle value of the cohort. */}
        <div
          className="absolute inset-y-1 w-px bg-accent-400"
          style={{ left: `${place(band.median)}%` }}
        />
        {/* This subject. */}
        <div
          className="absolute inset-y-0 w-0.5 rounded-full bg-brand-hover"
          style={{ left: `${marker}%` }}
        />
      </div>

      <div className="mt-1 flex justify-between text-[11px] tabular-nums text-faint">
        <span>1</span>
        <span>
          middle half {band.p25.toFixed(1)}–{band.p75.toFixed(1)}
        </span>
        <span>5</span>
      </div>

      <p className="mt-1.5 text-xs text-muted">
        This subject is {where} of comparable subjects. The band is there to
        answer whether a score is unusual, not to place anyone in an order.
      </p>
    </div>
  );
}

const PROMPT_HEADING: Record<string, string> = {
  helped: 'What helped',
  change: 'What to change',
};

/**
 * Written feedback, or why there is none to show.
 *
 * An empty list has three different meanings — nobody wrote anything, the
 * window is still open, or too few people responded — and a blank space says
 * none of them.
 */
function Comments({
  comments,
  state,
}: {
  comments: AssignmentReport['comments'];
  state: CommentState;
}) {
  if (state === 'window_open') {
    return (
      <p className="text-sm text-muted">
        Written feedback appears here once the feedback period closes. It is held
        back until then so that nobody is reading criticism while marks are still
        being decided.
      </p>
    );
  }

  if (state === 'too_few_responses') {
    return (
      <p className="text-sm text-muted">
        Too few students responded for written feedback to be shown. With only a
        handful of replies, who wrote what is often guessable, so none of it is
        released.
      </p>
    );
  }

  if (comments.length === 0) {
    return <p className="text-sm text-faint">Nobody wrote anything this time.</p>;
  }

  const grouped = comments.reduce<Record<string, typeof comments>>((acc, comment) => {
    (acc[comment.prompt] ??= []).push(comment);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-4">
      {Object.entries(grouped).map(([prompt, entries]) => (
        <div key={prompt}>
          <h4 className="mb-1.5 text-xs uppercase tracking-wide text-muted">
            {PROMPT_HEADING[prompt] ?? prompt}
          </h4>
          <ul className="flex flex-col gap-2">
            {entries.map((comment) => (
              <li
                key={comment.id}
                className={
                  comment.withheld
                    ? 'rounded-md border border-bad bg-bad-soft/40 p-3 text-sm text-body'
                    : 'rounded-md bg-sunken p-3 text-sm text-body'
                }
              >
                {comment.withheld ? (
                  <span className="mb-1 block text-xs font-medium text-bad">
                    Withheld from the instructor
                    {comment.withheld_reason ? ` — ${comment.withheld_reason}` : ''}
                  </span>
                ) : null}
                {comment.text}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function AssignmentSection({ report }: { report: AssignmentReport }) {
  return (
    <Card title={`${report.subject_code} — ${report.subject_name} · ${report.class_label}`}>
      <div className="mb-4 flex flex-col gap-3">
        <ReliabilityNote
          reliability={report.reliability}
          responses={report.responses}
          eligible={report.eligible_students}
        />

        <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <div>
            <dt className="text-xs uppercase text-muted">Overall</dt>
            <dd>
              <Mean value={report.mean} responses={report.responses} />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-muted">Responses</dt>
            <dd className="tabular-nums">
              {report.responses} of {report.eligible_students}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-muted">Response rate</dt>
            <dd>
              <Rate value={report.response_rate} />
            </dd>
          </div>
        </dl>

        <CohortContext band={report.cohort} mean={report.mean} />
      </div>

      <div className="flex flex-col gap-5">
        {report.criteria.map((criterion) => (
          <section key={criterion.criterion_id}>
            <header className="mb-2 flex items-baseline justify-between border-b border-line pb-1">
              <h3 className="text-sm font-semibold text-heading">{criterion.name}</h3>
              <Mean value={criterion.mean} responses={report.responses} />
            </header>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase text-muted">
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
                    <tr key={question.question_id} className="border-t border-line">
                      <td className="py-2 pr-4 text-body">
                        {question.text}
                        {question.curriculum ? (
                          <span className="ml-2 whitespace-nowrap text-xs text-faint">
                            asked only in {question.curriculum}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-4">
                        <Distribution question={question} />
                      </td>
                      <td className="py-2 text-right">
                        <Mean
                          value={question.mean}
                          responses={question.responses}
                          range={question.mean_range}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>

      <section className="mt-6 border-t border-line pt-4">
        <h3 className="mb-2 text-sm font-semibold text-heading">
          In students' own words
        </h3>
        <Comments comments={report.comments} state={report.comment_state} />
      </section>
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
