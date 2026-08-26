import { useEffect, useState } from 'react';

import type { AcademicTerm } from '@/api/types';

/**
 * Term selection, shared by the questionnaire, assignments and reports.
 *
 * Defaults to whichever term is current, and only once — reselecting it on
 * every render would fight the user's own choice.
 */
export function useSelectedTerm(termList: AcademicTerm[] | undefined) {
  const [termId, setTermId] = useState<number | null>(null);

  useEffect(() => {
    if (termId !== null || termList === undefined || termList.length === 0) return;
    const current = termList.find((term) => term.is_current) ?? termList[0];
    if (current !== undefined) setTermId(current.id);
  }, [termId, termList]);

  return {
    termId,
    setTermId,
    term: termList?.find((entry) => entry.id === termId) ?? null,
  };
}

export function TermPicker({
  terms,
  value,
  onChange,
}: {
  terms: AcademicTerm[] | undefined;
  value: number | null;
  onChange: (id: number) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      <span>Academic year</span>
      <select
        value={value ?? ''}
        onChange={(event) => onChange(Number(event.target.value))}
        className="rounded-md bg-surface px-2 py-1.5 text-sm text-heading ring-1 ring-line-strong"
      >
        {terms === undefined || terms.length === 0 ? (
          <option value="">No years yet</option>
        ) : null}
        {terms?.map((term) => (
          <option key={term.id} value={term.id}>
            {term.year} · semester {term.semester}
            {term.is_current ? ' (current)' : ''}
          </option>
        ))}
      </select>
    </label>
  );
}
