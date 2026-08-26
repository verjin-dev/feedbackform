import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { Alert, Card } from '@/components/ui';

export interface TrendPoint {
  term_id: number;
  label: string;
  mean: number | null;
  responses: number;
  eligible_students: number;
  response_rate: number | null;
  reliability: string;
}

export interface FacultyTrend {
  faculty_id: number;
  faculty_name: string;
  terms: { id: number; year: string; semester: number; label: string }[];
  overall: TrendPoint[];
  criteria: { criterion_id: number; name: string; points: TrendPoint[] }[];
  subjects: { subject_id: number; code: string; name: string; points: TrendPoint[] }[];
  minimum_responses_for_mean: number;
}

const WIDTH = 132;
const HEIGHT = 34;
const PAD = 4;
// Fixed to the rating scale, not to the data. Auto-scaling a 4.1-to-4.3 range
// to fill the box turns noise into a mountain, which is the single easiest way
// to mislead with a sparkline.
const MIN = 1;
const MAX = 5;

function x(index: number, count: number): number {
  if (count <= 1) return WIDTH / 2;
  return PAD + (index / (count - 1)) * (WIDTH - PAD * 2);
}

function y(value: number): number {
  const ratio = (value - MIN) / (MAX - MIN);
  return HEIGHT - PAD - ratio * (HEIGHT - PAD * 2);
}

/**
 * A sparkline over the rating scale.
 *
 * Terms with too few responses are gaps rather than points — a dot drawn from
 * three answers is read as a fact — so the line is broken into runs of
 * consecutive published values rather than drawn straight through.
 */
export function Sparkline({ points, label }: { points: TrendPoint[]; label: string }) {
  const published = points.filter((point) => point.mean !== null);

  if (published.length === 0) {
    return <span className="text-xs text-ink-400">Not enough data yet</span>;
  }

  const runs: { index: number; point: TrendPoint }[][] = [];
  let current: { index: number; point: TrendPoint }[] = [];
  points.forEach((point, index) => {
    if (point.mean === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push({ index, point });
    }
  });
  if (current.length) runs.push(current);

  const last = published[published.length - 1] as TrendPoint;
  const first = published[0] as TrendPoint;
  const direction = (last.mean as number) - (first.mean as number);

  const description = points
    .map((p) => `${p.label}: ${p.mean === null ? 'too few responses' : p.mean.toFixed(2)}`)
    .join(', ');

  return (
    <div className="flex items-center gap-2">
      <svg
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${label} over time. ${description}`}
        className="overflow-visible"
      >
        {/* The midpoint of the scale, so a line sitting near 3 is visibly
            mid-scale rather than just "somewhere in the box". */}
        <line
          x1={0}
          x2={WIDTH}
          y1={y(3)}
          y2={y(3)}
          className="stroke-ink-200"
          strokeWidth={1}
          strokeDasharray="2 3"
        />

        {runs.map((run, runIndex) => (
          <polyline
            key={runIndex}
            fill="none"
            className="stroke-accent-500"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
            points={run
              .map(({ index, point }) => `${x(index, points.length)},${y(point.mean as number)}`)
              .join(' ')}
          />
        ))}

        {points.map((point, index) =>
          point.mean === null ? (
            // A hollow marker on the axis: something happened that term, but
            // not enough of it to plot.
            <circle
              key={point.term_id}
              cx={x(index, points.length)}
              cy={y(3)}
              r={2}
              className="fill-transparent stroke-ink-300"
              strokeWidth={1}
            />
          ) : (
            <circle
              key={point.term_id}
              cx={x(index, points.length)}
              cy={y(point.mean)}
              r={index === points.length - 1 ? 3 : 2}
              className={index === points.length - 1 ? 'fill-accent-600' : 'fill-accent-300'}
            />
          ),
        )}
      </svg>

      <span className="text-xs tabular-nums text-ink-500">
        {(last.mean as number).toFixed(2)}
        {published.length > 1 ? (
          <span
            className={
              direction > 0.05
                ? 'ml-1 text-positive-600'
                : direction < -0.05
                  ? 'ml-1 text-critical-600'
                  : 'ml-1 text-ink-400'
            }
          >
            {direction > 0.05 ? '↑' : direction < -0.05 ? '↓' : '→'}
            {Math.abs(direction) >= 0.05 ? Math.abs(direction).toFixed(2) : ''}
          </span>
        ) : null}
      </span>
    </div>
  );
}

/** The trend section on a results page. */
export function TrendPanel({ facultyId }: { facultyId: number | 'me' }) {
  const path = facultyId === 'me' ? '/reports/me/trend' : `/reports/faculty/${facultyId}/trend`;

  const trend = useQuery({
    queryKey: ['trend', facultyId],
    queryFn: () => api.get<FacultyTrend>(path),
    retry: false,
  });

  if (trend.isLoading) {
    return (
      <Card title="Over time">
        <p className="py-4 text-center text-sm text-ink-400" role="status">
          Loading...
        </p>
      </Card>
    );
  }

  if (trend.error || !trend.data) return null;

  const data = trend.data;
  if (data.terms.length === 0) {
    return (
      <Card title="Over time">
        <p className="text-sm text-ink-400">
          Nothing to compare yet. A second term of feedback is what turns this
          from a verdict into a direction.
        </p>
      </Card>
    );
  }

  if (data.terms.length === 1) {
    return (
      <Card title="Over time">
        <p className="text-sm text-ink-500">
          This is the first term with feedback, so there is nothing to compare
          it against yet.
        </p>
      </Card>
    );
  }

  const anyGaps = data.overall.some((point) => point.mean === null);

  return (
    <Card title="Over time">
      <div className="flex flex-col gap-5">
        <div>
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink-800">Across everything</h3>
            <span className="text-xs text-ink-400">
              {data.terms[0]?.label} → {data.terms[data.terms.length - 1]?.label}
            </span>
          </div>
          <Sparkline points={data.overall} label="Overall rating" />
        </div>

        {data.criteria.length > 0 ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink-800">By criterion</h3>
            <ul className="flex flex-col gap-2">
              {data.criteria.map((series) => (
                <li
                  key={series.criterion_id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 pb-2 last:border-0"
                >
                  <span className="text-sm text-ink-700">{series.name}</span>
                  <Sparkline points={series.points} label={series.name} />
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {data.subjects.length > 1 ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink-800">By subject</h3>
            <ul className="flex flex-col gap-2">
              {data.subjects.map((series) => (
                <li
                  key={series.subject_id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 pb-2 last:border-0"
                >
                  <span className="text-sm text-ink-700">
                    {series.code} <span className="text-ink-400">{series.name}</span>
                  </span>
                  <Sparkline points={series.points} label={series.code} />
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {anyGaps ? (
          <Alert tone="caution">
            A gap in a line is a term where fewer than{' '}
            {data.minimum_responses_for_mean} students responded. Those terms are
            marked on the axis rather than plotted, because an average from that
            few would be read as a fact.
          </Alert>
        ) : null}

        <p className="text-xs text-ink-400">
          Lines are drawn against the full 1–5 scale, not zoomed to the range of
          the data, so a small change looks small.
        </p>
      </div>
    </Card>
  );
}
