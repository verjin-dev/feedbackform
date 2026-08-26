import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError, api } from '@/api/client';
import { accounts, classes, subjects, terms } from '@/api/resources';
import type { TeachingAssignment } from '@/api/types';
import { DataTable } from '@/components/DataTable';
import { Dialog } from '@/components/Dialog';
import { Alert, Button, Card } from '@/components/ui';
import { TermPicker, useSelectedTerm } from '@/routes/admin/TermPicker';

interface Row {
  faculty_id: number;
  class_group_id: number;
  subject_id: number;
}

const keyOf = (row: Row) => `${row.faculty_id}:${row.class_group_id}:${row.subject_id}`;

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

/**
 * Who teaches what, to which class, this term.
 *
 * The API replaces the whole set in one request, so this screen edits a local
 * draft and saves it deliberately rather than writing on every click. That
 * matches how the work is actually done — the matrix is reviewed as a whole at
 * the start of term — and it means a half-finished edit never reaches the
 * database.
 */
export function AssignmentsPage() {
  const queryClient = useQueryClient();
  const termList = terms.useList();
  const { termId, setTermId } = useSelectedTerm(termList.data);

  const facultyList = accounts.useList({ role: 'faculty' });
  const classList = classes.useList();
  const subjectList = subjects.useList();

  const existing = useQuery({
    queryKey: ['assignments', termId],
    queryFn: () =>
      api.get<TeachingAssignment[]>(`/academic-years/${termId}/assignments`),
    enabled: termId !== null,
  });

  const save = useMutation({
    mutationFn: (rows: Row[]) =>
      api.put<TeachingAssignment[]>(`/academic-years/${termId}/assignments`, {
        assignments: rows,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assignments'] }),
  });

  const [draft, setDraft] = useState<Row[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Reset the draft whenever the server's version changes, including after a
  // successful save and when the selected term changes.
  useEffect(() => {
    if (existing.data === undefined) return;
    setDraft(
      existing.data.map((row) => ({
        faculty_id: row.faculty_id,
        class_group_id: row.class_group_id,
        subject_id: row.subject_id,
      })),
    );
    setError(null);
  }, [existing.data]);

  const serverKeys = useMemo(
    () => new Set((existing.data ?? []).map((row) => keyOf(row))),
    [existing.data],
  );
  const draftKeys = useMemo(() => new Set((draft ?? []).map(keyOf)), [draft]);

  const removedCount = [...serverKeys].filter((key) => !draftKeys.has(key)).length;
  const addedCount = [...draftKeys].filter((key) => !serverKeys.has(key)).length;
  const dirty = removedCount > 0 || addedCount > 0;

  const nameOf = {
    faculty: (id: number) =>
      facultyList.data?.find((entry) => entry.id === id)?.full_name ?? `#${id}`,
    class: (id: number) =>
      classList.data?.find((entry) => entry.id === id)?.label ?? `#${id}`,
    subject: (id: number) => {
      const subject = subjectList.data?.find((entry) => entry.id === id);
      return subject ? `${subject.code} — ${subject.name}` : `#${id}`;
    },
  };

  function discard() {
    setDraft(
      (existing.data ?? []).map((row) => ({
        faculty_id: row.faculty_id,
        class_group_id: row.class_group_id,
        subject_id: row.subject_id,
      })),
    );
    setError(null);
    setSaved(false);
  }

  async function commit() {
    if (draft === null) return;
    setError(null);
    setSaved(false);
    try {
      await save.mutateAsync(draft);
      setSaved(true);
    } catch (cause) {
      // The API refuses to remove an assignment that already has submitted
      // evaluations and names which ones. That message is the whole value of
      // the 409, so it is shown verbatim and the draft is left intact for the
      // administrator to correct.
      setError(messageFrom(cause, 'Could not save these assignments.'));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}
      {saved && !dirty ? <Alert tone="positive">Assignments saved.</Alert> : null}

      <Card
        title="Teaching assignments"
        actions={
          <div className="flex items-center gap-2">
            <TermPicker terms={termList.data} value={termId} onChange={setTermId} />
            <Button variant="secondary" onClick={() => setAdding(true)} disabled={termId === null}>
              Add
            </Button>
            {/* Without this, a refused save leaves the draft showing rows as
                removed that the server still holds — an empty table next to a
                message saying they cannot be removed. */}
            <Button variant="ghost" onClick={discard} disabled={!dirty || save.isPending}>
              Discard changes
            </Button>
            <Button onClick={commit} loading={save.isPending} disabled={!dirty}>
              Save changes
            </Button>
          </div>
        }
      >
        {dirty ? (
          <p className="mb-3 text-sm text-warn">
            Unsaved changes: {addedCount} to add, {removedCount} to remove.
          </p>
        ) : null}

        <DataTable
          rows={draft ?? undefined}
          columns={[
            { header: 'Faculty', cell: (row) => nameOf.faculty(row.faculty_id) },
            { header: 'Class', cell: (row) => nameOf.class(row.class_group_id) },
            { header: 'Subject', cell: (row) => nameOf.subject(row.subject_id) },
            {
              header: '',
              cell: (row) =>
                serverKeys.has(keyOf(row)) ? null : (
                  <span className="text-xs text-good">new</span>
                ),
            },
          ]}
          rowKey={keyOf}
          isLoading={existing.isLoading}
          error={existing.error}
          empty="No assignments for this year yet."
          actions={(row) => (
            <Button
              variant="ghost"
              className="text-bad"
              onClick={() =>
                setDraft((current) =>
                  (current ?? []).filter((entry) => keyOf(entry) !== keyOf(row)),
                )
              }
            >
              Remove
            </Button>
          )}
        />
      </Card>

      <AddAssignmentDialog
        open={adding}
        onClose={() => setAdding(false)}
        faculty={facultyList.data ?? []}
        classGroups={classList.data ?? []}
        subjectList={subjectList.data ?? []}
        existingKeys={draftKeys}
        onAdd={(row) => {
          setDraft((current) => [...(current ?? []), row]);
          setAdding(false);
        }}
      />
    </div>
  );
}

function AddAssignmentDialog({
  open,
  onClose,
  faculty,
  classGroups,
  subjectList,
  existingKeys,
  onAdd,
}: {
  open: boolean;
  onClose: () => void;
  faculty: { id: number; full_name: string }[];
  classGroups: { id: number; label: string }[];
  subjectList: { id: number; code: string; name: string }[];
  existingKeys: Set<string>;
  onAdd: (row: Row) => void;
}) {
  const [facultyId, setFacultyId] = useState<number | null>(null);
  const [classId, setClassId] = useState<number | null>(null);
  const [subjectId, setSubjectId] = useState<number | null>(null);

  const complete = facultyId !== null && classId !== null && subjectId !== null;
  const duplicate =
    complete &&
    existingKeys.has(
      keyOf({ faculty_id: facultyId, class_group_id: classId, subject_id: subjectId }),
    );

  return (
    <Dialog
      open={open}
      title="Add assignment"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!complete || duplicate}
            onClick={() => {
              if (!complete) return;
              onAdd({
                faculty_id: facultyId,
                class_group_id: classId,
                subject_id: subjectId,
              });
              setFacultyId(null);
              setClassId(null);
              setSubjectId(null);
            }}
          >
            Add
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {/* Caught here rather than at save time, because the API rejects the
            whole batch for one duplicate. */}
        {duplicate ? <Alert tone="caution">That assignment is already listed.</Alert> : null}

        <Select
          label="Faculty"
          value={facultyId}
          onChange={setFacultyId}
          options={faculty.map((entry) => ({ value: entry.id, label: entry.full_name }))}
        />
        <Select
          label="Class"
          value={classId}
          onChange={setClassId}
          options={classGroups.map((entry) => ({ value: entry.id, label: entry.label }))}
        />
        <Select
          label="Subject"
          value={subjectId}
          onChange={setSubjectId}
          options={subjectList.map((entry) => ({
            value: entry.id,
            label: `${entry.code} — ${entry.name}`,
          }))}
        />
      </div>
    </Dialog>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
  options: { value: number; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-body">{label}</span>
      <select
        value={value ?? ''}
        onChange={(event) => onChange(Number(event.target.value))}
        className="rounded-md bg-surface px-3 py-2 text-sm text-heading ring-1 ring-line-strong"
      >
        <option value="">Select {label.toLowerCase()}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
