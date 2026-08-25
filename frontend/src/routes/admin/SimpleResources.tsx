import { useState } from 'react';

import type { AcademicTerm, ClassGroup, Criterion, Subject } from '@/api/types';
import {
  classes,
  criteria,
  subjects,
  terms,
  useActivateTerm,
  type ClassInput,
  type CriterionInput,
  type SubjectInput,
  type TermInput,
} from '@/api/resources';
import { Badge } from '@/components/DataTable';
import { CrudScreen } from '@/components/CrudScreen';
import { Alert, Button, Field } from '@/components/ui';

const STATUS_TONE = {
  pending: 'caution',
  open: 'positive',
  closed: 'neutral',
} as const;

const STATUS_LABEL = {
  pending: 'Not started',
  open: 'Open',
  closed: 'Closed',
} as const;

export function AcademicYearsPage() {
  const activate = useActivateTerm();
  const [error, setError] = useState<string | null>(null);

  async function makeCurrent(term: AcademicTerm) {
    setError(null);
    try {
      await activate.mutateAsync(term.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not activate that term.');
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <CrudScreen<AcademicTerm, TermInput>
        title="Academic years"
        noun="year"
        resource={terms}
        columns={[
          { header: 'Year', cell: (row) => row.year },
          { header: 'Semester', cell: (row) => row.semester, numeric: true },
          {
            header: 'Evaluation',
            cell: (row) => (
              <Badge tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Badge>
            ),
          },
          {
            header: 'Current',
            cell: (row) =>
              row.is_current ? <Badge tone="positive">Current</Badge> : null,
          },
        ]}
        blankForm={{ year: '', semester: 1 }}
        toForm={(row) => ({ year: row.year, semester: row.semester })}
        describe={(row) => `${row.year} semester ${row.semester}`}
        // The API refuses this too; disabling the control explains why up front
        // rather than after a failed attempt.
        locked={(row) =>
          row.is_current ? 'Make another year current before deleting this one.' : null
        }
        extraActions={(row) =>
          row.is_current ? null : (
            <Button
              variant="ghost"
              onClick={() => void makeCurrent(row)}
              loading={activate.isPending}
            >
              Make current
            </Button>
          )
        }
        renderForm={(value, set) => (
          <>
            <Field
              label="Year"
              value={value.year}
              placeholder="2025-2026"
              onChange={(event) => set('year', event.target.value)}
              required
            />
            <Field
              label="Semester"
              type="number"
              min={1}
              max={4}
              value={value.semester}
              onChange={(event) => set('semester', Number(event.target.value))}
              required
            />
          </>
        )}
      />
    </div>
  );
}

export function ClassesPage() {
  return (
    <CrudScreen<ClassGroup, ClassInput>
      title="Classes"
      noun="class"
      resource={classes}
      columns={[
        { header: 'Curriculum', cell: (row) => row.curriculum },
        { header: 'Level', cell: (row) => row.level },
        { header: 'Section', cell: (row) => row.section },
      ]}
      blankForm={{ curriculum: '', level: '', section: '' }}
      toForm={(row) => ({
        curriculum: row.curriculum,
        level: row.level,
        section: row.section,
      })}
      describe={(row) => row.label}
      empty="No classes yet."
      renderForm={(value, set) => (
        <>
          <Field
            label="Curriculum"
            value={value.curriculum}
            placeholder="B.E. Computer Science"
            onChange={(event) => set('curriculum', event.target.value)}
            required
          />
          <Field
            label="Level"
            value={value.level}
            placeholder="III"
            onChange={(event) => set('level', event.target.value)}
            required
          />
          <Field
            label="Section"
            value={value.section}
            placeholder="A"
            onChange={(event) => set('section', event.target.value)}
            required
          />
        </>
      )}
    />
  );
}

export function SubjectsPage() {
  return (
    <CrudScreen<Subject, SubjectInput>
      title="Subjects"
      noun="subject"
      resource={subjects}
      columns={[
        { header: 'Code', cell: (row) => row.code },
        { header: 'Name', cell: (row) => row.name },
        {
          header: 'Description',
          cell: (row) => (
            <span className="text-ink-500">{row.description ?? '—'}</span>
          ),
        },
      ]}
      blankForm={{ code: '', name: '', description: '' }}
      toForm={(row) => ({
        code: row.code,
        name: row.name,
        description: row.description ?? '',
      })}
      describe={(row) => `${row.code} ${row.name}`}
      renderForm={(value, set) => (
        <>
          <Field
            label="Code"
            value={value.code}
            placeholder="CS3401"
            onChange={(event) => set('code', event.target.value)}
            required
          />
          <Field
            label="Name"
            value={value.name}
            placeholder="Algorithms"
            onChange={(event) => set('name', event.target.value)}
            required
          />
          <Field
            label="Description"
            value={value.description ?? ''}
            onChange={(event) => set('description', event.target.value)}
          />
        </>
      )}
    />
  );
}

export function CriteriaPage() {
  return (
    <CrudScreen<Criterion, CriterionInput>
      title="Criteria"
      noun="criterion"
      resource={criteria}
      columns={[
        { header: 'Order', cell: (row) => row.position, numeric: true, width: '5rem' },
        { header: 'Criterion', cell: (row) => row.name },
      ]}
      blankForm={{ name: '' }}
      toForm={(row) => ({ name: row.name })}
      describe={(row) => row.name}
      empty="No criteria yet."
      renderForm={(value, set) => (
        <Field
          label="Criterion"
          value={value.name}
          placeholder="Subject knowledge"
          onChange={(event) => set('name', event.target.value)}
          required
        />
      )}
    />
  );
}
