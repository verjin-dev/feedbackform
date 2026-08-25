import type { ReactNode } from 'react';

import { Alert } from '@/components/ui';

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  /** Right-aligns and applies tabular figures, so digits line up in columns. */
  numeric?: boolean;
  width?: string;
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
      <p className="py-6 text-center text-sm text-ink-400" role="status">
        Loading...
      </p>
    );
  }

  if (!rows || rows.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-400">{empty}</p>;
  }

  return (
    // Wide tables scroll inside their own container so the page body never
    // scrolls sideways.
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink-200 text-left">
            {columns.map((column) => (
              <th
                key={column.header}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={`px-3 py-2 text-xs font-medium tracking-wide text-ink-500 uppercase ${
                  column.numeric ? 'text-right' : ''
                }`}
              >
                {column.header}
              </th>
            ))}
            {actions ? (
              <th scope="col" className="px-3 py-2">
                <span className="sr-only">Actions</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-ink-100 last:border-0">
              {columns.map((column) => (
                <td
                  key={column.header}
                  className={`px-3 py-2 text-ink-700 ${
                    column.numeric ? 'text-right tabular-nums' : ''
                  }`}
                >
                  {column.cell(row)}
                </td>
              ))}
              {actions ? (
                <td className="px-3 py-2 text-right whitespace-nowrap">{actions(row)}</td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'positive' | 'caution' | 'critical';
  children: ReactNode;
}) {
  const tones = {
    neutral: 'bg-ink-100 text-ink-600',
    positive: 'bg-positive-100 text-positive-600',
    caution: 'bg-caution-100 text-caution-600',
    critical: 'bg-critical-100 text-critical-600',
  } as const;

  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
