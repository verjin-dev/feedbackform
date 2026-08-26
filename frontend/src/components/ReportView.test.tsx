import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { AssignmentReport, QuestionReport } from '@/api/types';
import { AssignmentSection, Mean } from '@/components/ReportView';

function question(overrides: Partial<QuestionReport> = {}): QuestionReport {
  return {
    question_id: 1,
    text: 'Explains concepts clearly.',
    counts: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
    percentages: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
    responses: 0,
    mean: null,
    mean_range: null,
    reliability: 'insufficient',
    ...overrides,
  };
}

function assignment(overrides: Partial<AssignmentReport> = {}): AssignmentReport {
  return {
    assignment_id: 1,
    subject_id: 1,
    subject_code: 'CS3401',
    subject_name: 'Algorithms',
    class_group_id: 1,
    class_label: 'B.E. CSE III-A',
    eligible_students: 39,
    responses: 0,
    response_rate: 0,
    reliability: 'insufficient',
    mean: null,
    criteria: [{ criterion_id: 1, name: 'Subject knowledge', questions: [question()], mean: null }],
    cohort: null,
    comments: [],
    comment_state: 'released',
    comment_total: 0,
    ...overrides,
  };
}

describe('Mean', () => {
  it('distinguishes "nobody answered" from "too few answered"', () => {
    // Both arrive as mean === null. Rendering them the same way hides that
    // data exists in one case and not the other.
    const { rerender } = render(<Mean value={null} responses={0} />);
    expect(screen.getByText('No responses')).toBeInTheDocument();

    rerender(<Mean value={null} responses={3} />);
    expect(screen.getByText(/Too few to average/)).toBeInTheDocument();
    expect(screen.getByText('(3)')).toBeInTheDocument();
  });

  it('never renders a suppressed mean as zero', () => {
    render(<Mean value={null} responses={3} />);

    expect(screen.queryByText('0.00')).not.toBeInTheDocument();
  });

  it('shows the interval beside a published mean', () => {
    render(<Mean value={4.2} responses={12} range={[3.6, 4.8]} />);

    expect(screen.getByText('4.20')).toBeInTheDocument();
    expect(screen.getByText('(3.6–4.8)')).toBeInTheDocument();
  });

  it('omits a zero-width interval rather than printing 4.0-4.0', () => {
    render(<Mean value={4} responses={12} range={[4, 4]} />);

    expect(screen.queryByText(/4\.0–4\.0/)).not.toBeInTheDocument();
  });
});

describe('AssignmentSection', () => {
  it('says plainly when nobody has responded', () => {
    render(<AssignmentSection report={assignment()} />);

    expect(screen.getByText(/Nobody has responded yet/)).toBeInTheDocument();
  });

  it('explains why an average is withheld for a small sample', () => {
    render(
      <AssignmentSection
        report={assignment({ responses: 3, response_rate: 3 / 39 })}
      />,
    );

    expect(screen.getByText(/Only 3 people have responded/)).toBeInTheDocument();
    expect(screen.getByText(/too few to publish an average/)).toBeInTheDocument();
  });

  it('flags a real mean drawn from a minority of the class', () => {
    // The thesis case: 7 of 39 and 28 of 39 both average 4.2, and only one of
    // them is worth acting on.
    render(
      <AssignmentSection
        report={assignment({
          responses: 7,
          response_rate: 7 / 39,
          reliability: 'low',
          mean: 4.2,
        })}
      />,
    );

    expect(screen.getByText(/come from a minority of the class/)).toBeInTheDocument();
    expect(screen.getByText('4.20')).toBeInTheDocument();
  });

  it('adds no caveat when the sample is adequate', () => {
    render(
      <AssignmentSection
        report={assignment({
          responses: 28,
          response_rate: 28 / 39,
          reliability: 'adequate',
          mean: 4.2,
        })}
      />,
    );

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('4.20')).toBeInTheDocument();
  });
});

describe('cohort context', () => {
  const band = {
    size: 11,
    p25: 3.8,
    median: 4.1,
    p75: 4.5,
    basis: '11 other subjects in B.E. CSE, 2025-2026 semester 1',
  };

  it('shows nothing when there is no honest comparison', () => {
    render(<AssignmentSection report={assignment({ responses: 20, mean: 4.2 })} />);

    expect(screen.queryByText(/In context/i)).not.toBeInTheDocument();
  });

  it('describes the band as a range rather than a position', () => {
    render(
      <AssignmentSection
        report={assignment({ responses: 20, mean: 4.2, reliability: 'adequate', cohort: band })}
      />,
    );

    expect(screen.getByText(/middle half 3\.8–4\.5/)).toBeInTheDocument();
    expect(screen.getByText(band.basis)).toBeInTheDocument();
  });

  it('never renders a rank or a percentile', () => {
    const { container } = render(
      <AssignmentSection
        report={assignment({ responses: 20, mean: 4.2, reliability: 'adequate', cohort: band })}
      />,
    );

    const text = container.textContent?.toLowerCase() ?? '';
    expect(text).not.toContain('percentile');
    expect(text).not.toContain('rank');
    expect(text).not.toMatch(/\d+(st|nd|rd|th) of \d+/);
  });

  it('says where the score sits without ordering anyone', () => {
    render(
      <AssignmentSection
        report={assignment({ responses: 20, mean: 4.8, reliability: 'adequate', cohort: band })}
      />,
    );

    expect(screen.getByText(/above the middle half/)).toBeInTheDocument();
  });

  it('describes the whole comparison for a screen reader', () => {
    render(
      <AssignmentSection
        report={assignment({ responses: 20, mean: 3.2, reliability: 'adequate', cohort: band })}
      />,
    );

    const chart = screen.getAllByRole('img').at(-1) as HTMLElement;
    expect(chart).toHaveAccessibleName(/scored 3\.20/);
    expect(chart).toHaveAccessibleName(/below the middle half/);
  });

  it('is hidden when this subject has no publishable mean of its own', () => {
    // Comparing a withheld figure against a band would put it back on screen.
    render(<AssignmentSection report={assignment({ responses: 3, mean: null, cohort: band })} />);

    expect(screen.queryByText(/middle half/)).not.toBeInTheDocument();
  });
});
