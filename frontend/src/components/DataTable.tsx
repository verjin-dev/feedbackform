import type { ReactNode } from 'react';

import { Alert, EmptyState, SkeletonRows, cx } from '@/components/ui';

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  /** Right-aligns and applies tabular figures, so digits line up in columns. */
  numeric?: boolean;
  width?: string;
  /** Dropped below `md`. For columns that are context rather than content. */
  secondary?: boolean;
}

interface DataTableProps<T> {
  rows: T[] | undefined;
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  isLoading?: boolean;
  error?: unknown;
  empty?: ReactNode;
  actions?: (row: T) => ReactNode;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  isLoading = false,
  error,
  empty = 'Nothing here yet.',
  actions,
}: DataTableProps<T>) {
  if (error) {
    return (
      <Alert>
        {error instanceof Error ? error.message : 'Could not load this list.'}
      </Alert>
    );
  }

  if (isLoading) {
    return (
      <div className="p-5">
        <SkeletonRows rows={5} />
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return <EmptyState title={typeof empty === 'string' ? empty : 'Nothing here yet.'} />;
  }

  return (
    // Wide tables scroll inside their own container so the page body never
    // scrolls sideways.
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          {/* Sticky, because these lists run to hundreds of rows and a column
              of dates with the heading scrolled away is a column of numbers. */}
          <tr className="sticky top-0 z-10 bg-raised text-left shadow-[0_1px_0_var(--line-strong)]">
            {columns.map((column) => (
              <th
                key={column.header}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={cx(
                  'px-4 py-2.5 text-[11px] font-semibold tracking-wider text-muted uppercase',
                  column.numeric && 'text-right',
                  column.secondary && 'hidden md:table-cell',
                )}
              >
                {column.header}
              </th>
            ))}
            {actions ? (
              <th scope="col" className="px-4 py-2.5">
                <span className="sr-only">Actions</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className="border-t border-line transition-colors hover:bg-sunken/70"
            >
              {columns.map((column) => (
                <td
                  key={column.header}
                  className={cx(
                    'px-4 py-3 text-body',
                    column.numeric && 'text-right tabular-nums',
                    column.secondary && 'hidden md:table-cell',
                  )}
                >
                  {column.cell(row)}
                </td>
              ))}
              {actions ? (
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {actions(row)}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Badge ----------------------------------------------------------------

const BADGE_TONES = {
  neutral: 'bg-sunken text-muted ring-line-strong',
  positive: 'bg-good-soft text-good ring-good/25',
  caution: 'bg-warn-soft text-warn ring-warn/25',
  critical: 'bg-bad-soft text-bad ring-bad/25',
  brand: 'bg-brand-soft text-brand-text ring-brand/20',
} as const;

export function Badge({
  tone = 'neutral',
  dot = false,
  children,
}: {
  tone?: keyof typeof BADGE_TONES;
  /** A coloured dot as a second, non-colour cue for status. */
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5',
        'text-xs font-medium whitespace-nowrap ring-1 ring-inset',
        BADGE_TONES[tone],
      )}
    >
      {dot ? (
        <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
      ) : null}
      {children}
    </span>
  );
}
