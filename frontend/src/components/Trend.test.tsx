import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Sparkline, type TrendPoint } from '@/components/Trend';

function point(label: string, mean: number | null, responses = 20): TrendPoint {
  return {
    term_id: label.length + (mean ?? 0) * 100,
    label,
    mean,
    responses,
    eligible_students: 30,
    response_rate: responses / 30,
    reliability: mean === null ? 'insufficient' : 'adequate',
  };
}

function polylines(container: HTMLElement): SVGPolylineElement[] {
  return Array.from(container.querySelectorAll('polyline'));
}

describe('Sparkline', () => {
  it('says so rather than drawing an empty box when there is nothing to plot', () => {
    render(<Sparkline points={[point('2024 S1', null), point('2025 S1', null)]} label="x" />);

    expect(screen.getByText('Not enough data yet')).toBeInTheDocument();
  });

  it('draws against the full 1-5 scale, not the range of the data', () => {
    // Auto-scaling 4.1-4.3 to fill the box turns noise into a mountain. Two
    // series a fifth of a point apart must sit close together, not identically.
    const flat = render(
      <Sparkline points={[point('a', 4.1), point('b', 4.3)]} label="flat" />,
    );
    const flatPoints = polylines(flat.container)[0]?.getAttribute('points') ?? '';
    const [, firstY, , secondY] = flatPoints.split(/[ ,]/).map(Number);

    // A 0.2 change on a 1-5 scale across a 34px box is a few pixels, not the
    // whole height.
    expect(Math.abs((firstY as number) - (secondY as number))).toBeLessThan(6);
  });

  it('breaks the line at a term with too few responses', () => {
    // Drawing straight through would imply a value that was never published.
    const { container } = render(
      <Sparkline
        points={[point('a', 4.0), point('b', null, 3), point('c', 4.5)]}
        label="broken"
      />,
    );

    expect(polylines(container)).toHaveLength(2);
  });

  it('keeps one line when there are no gaps', () => {
    const { container } = render(
      <Sparkline points={[point('a', 4.0), point('b', 4.2), point('c', 4.5)]} label="x" />,
    );

    expect(polylines(container)).toHaveLength(1);
  });

  it('marks a suppressed term rather than omitting it silently', () => {
    const { container } = render(
      <Sparkline points={[point('a', 4.0), point('b', null, 2)]} label="x" />,
    );

    // Three markers would mean it plotted the gap; one means it vanished.
    expect(container.querySelectorAll('circle')).toHaveLength(2);
  });

  it('describes the whole series for a screen reader, gaps included', () => {
    render(
      <Sparkline
        points={[point('2024 S1', 4.0), point('2025 S1', null, 3)]}
        label="Subject knowledge"
      />,
    );

    const chart = screen.getByRole('img');
    expect(chart).toHaveAccessibleName(/Subject knowledge over time/);
    expect(chart).toHaveAccessibleName(/2024 S1: 4\.00/);
    expect(chart).toHaveAccessibleName(/2025 S1: too few responses/);
  });

  it('reports the direction of travel, not just the latest figure', () => {
    render(<Sparkline points={[point('a', 3.5), point('b', 4.2)]} label="x" />);

    expect(screen.getByText('4.20')).toBeInTheDocument();
    expect(screen.getByText(/↑0\.70/)).toBeInTheDocument();
  });

  it('calls a change of half a tenth flat rather than a rise', () => {
    render(<Sparkline points={[point('a', 4.2), point('b', 4.22)]} label="x" />);

    expect(screen.getByText(/→/)).toBeInTheDocument();
  });

  it('shows no direction from a single published term', () => {
    render(<Sparkline points={[point('a', null, 1), point('b', 4.2)]} label="x" />);

    expect(screen.queryByText(/[↑↓→]/)).not.toBeInTheDocument();
  });
});
