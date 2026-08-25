import { useMemo, useState } from 'react';

import { ApiError } from '@/api/client';
import { criteria, questions, terms, useReorder } from '@/api/resources';
import type { Criterion, Question } from '@/api/types';
import { ConfirmDialog, Dialog } from '@/components/Dialog';
import { Alert, Button, Card, Field } from '@/components/ui';
import { TermPicker, useSelectedTerm } from '@/routes/admin/TermPicker';

interface Group {
  criterion: Criterion;
  items: Question[];
}

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

/** Moves one item within an array, returning a new array. */
function moved<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  if (item === undefined) return items;
  next.splice(to, 0, item);
  return next;
}

export function QuestionnairePage() {
  const termList = terms.useList();
  const { termId, setTermId, term } = useSelectedTerm(termList.data);

  const criterionList = criteria.useList();
  const questionList = questions.useList(termId === null ? undefined : { term_id: termId });

  const createQuestion = questions.useCreate();
  const updateQuestion = questions.useUpdate();
  const removeQuestion = questions.useRemove();
  const reorderCriteria = useReorder('/criteria');
  const reorderQuestions = useReorder(
    '/questions',
    termId === null ? undefined : { term_id: termId },
  );

  const [editing, setEditing] = useState<Question | null>(null);
  const [draft, setDraft] = useState<{ text: string; criterion_id: number } | null>(null);
  const [deleting, setDeleting] = useState<Question | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  /** Only criteria that have questions in this term appear, in criterion order —
   *  matching how the student sees the form. */
  const groups = useMemo<Group[]>(() => {
    const byCriterion = new Map<number, Question[]>();
    for (const question of questionList.data ?? []) {
      const bucket = byCriterion.get(question.criterion_id) ?? [];
      bucket.push(question);
      byCriterion.set(question.criterion_id, bucket);
    }
    return (criterionList.data ?? [])
      .filter((criterion) => byCriterion.has(criterion.id))
      .map((criterion) => ({
        criterion,
        items: (byCriterion.get(criterion.id) ?? []).sort(
          (a, b) => a.position - b.position || a.id - b.id,
        ),
      }));
  }, [criterionList.data, questionList.data]);

  /** The API replaces the whole term's ordering at once, so a move inside one
   *  criterion still submits every question in the term. */
  async function moveQuestion(groupIndex: number, from: number, direction: -1 | 1) {
    const group = groups[groupIndex];
    if (group === undefined) return;

    const reordered = moved(group.items, from, from + direction);
    if (reordered === group.items) return;

    const flattened = groups.flatMap((entry, index) =>
      index === groupIndex ? reordered : entry.items,
    );

    setError(null);
    try {
      await reorderQuestions.mutateAsync(flattened.map((question) => question.id));
    } catch (cause) {
      setError(messageFrom(cause, 'Could not save the new order.'));
    }
  }

  async function moveCriterion(index: number, direction: -1 | 1) {
    const all = criterionList.data ?? [];
    const reordered = moved(all, index, index + direction);
    if (reordered === all) return;

    setError(null);
    try {
      await reorderCriteria.mutateAsync(reordered.map((criterion) => criterion.id));
    } catch (cause) {
      setError(messageFrom(cause, 'Could not save the new order.'));
    }
  }

  async function submitDraft() {
    if (draft === null || termId === null) return;
    setFormError(null);
    try {
      if (editing === null) {
        await createQuestion.mutateAsync({
          term_id: termId,
          criterion_id: draft.criterion_id,
          text: draft.text,
        });
      } else {
        await updateQuestion.mutateAsync({ id: editing.id, body: draft });
      }
      setDraft(null);
      setEditing(null);
    } catch (cause) {
      setFormError(messageFrom(cause, 'Could not save this question.'));
    }
  }

  async function confirmDelete() {
    if (deleting === null) return;
    setError(null);
    try {
      await removeQuestion.mutateAsync(deleting.id);
      setDeleting(null);
    } catch (cause) {
      // Refused once ratings exist against it — removing it would change what
      // past reports mean.
      setError(messageFrom(cause, 'Could not delete this question.'));
      setDeleting(null);
    }
  }

  const firstCriterionId = criterionList.data?.[0]?.id ?? null;
  const busy = reorderQuestions.isPending || reorderCriteria.isPending;

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <Card
        title="Questionnaire"
        actions={
          <div className="flex items-center gap-2">
            <TermPicker terms={termList.data} value={termId} onChange={setTermId} />
            <Button
              onClick={() => {
                if (firstCriterionId === null) return;
                setEditing(null);
                setDraft({ text: '', criterion_id: firstCriterionId });
                setFormError(null);
              }}
              disabled={firstCriterionId === null || termId === null}
              title={
                firstCriterionId === null
                  ? 'Add a criterion before adding questions.'
                  : undefined
              }
            >
              Add question
            </Button>
          </div>
        }
      >
        {criterionList.data?.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-400">
            Add criteria first — questions are grouped under them.
          </p>
        ) : groups.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-400">
            No questions for {term?.year ?? 'this year'} yet.
          </p>
        ) : (
          <div className="flex flex-col gap-6">
            {groups.map((group, groupIndex) => (
              <section key={group.criterion.id}>
                <header className="mb-2 flex items-center justify-between gap-2 border-b border-ink-100 pb-1">
                  <h3 className="text-sm font-semibold text-ink-800">
                    {group.criterion.name}
                  </h3>
                  <div className="flex gap-1">
                    <MoveButton
                      label={`Move ${group.criterion.name} up`}
                      disabled={busy || groupIndex === 0}
                      onClick={() => void moveCriterion(groupIndex, -1)}
                      direction="up"
                    />
                    <MoveButton
                      label={`Move ${group.criterion.name} down`}
                      disabled={busy || groupIndex === groups.length - 1}
                      onClick={() => void moveCriterion(groupIndex, 1)}
                      direction="down"
                    />
                  </div>
                </header>

                <ol className="flex flex-col">
                  {group.items.map((question, index) => (
                    <li
                      key={question.id}
                      className="flex items-center gap-2 border-b border-ink-100 py-2 last:border-0"
                    >
                      <span className="w-6 text-xs text-ink-400 tabular-nums">
                        {index + 1}.
                      </span>
                      <span className="flex-1 text-sm text-ink-700">{question.text}</span>

                      <MoveButton
                        label={`Move question ${index + 1} up`}
                        disabled={busy || index === 0}
                        onClick={() => void moveQuestion(groupIndex, index, -1)}
                        direction="up"
                      />
                      <MoveButton
                        label={`Move question ${index + 1} down`}
                        disabled={busy || index === group.items.length - 1}
                        onClick={() => void moveQuestion(groupIndex, index, 1)}
                        direction="down"
                      />
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setEditing(question);
                          setDraft({
                            text: question.text,
                            criterion_id: question.criterion_id,
                          });
                          setFormError(null);
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        className="text-critical-600"
                        onClick={() => setDeleting(question)}
                      >
                        Delete
                      </Button>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}
      </Card>

      <Dialog
        open={draft !== null}
        title={editing === null ? 'Add question' : 'Edit question'}
        onClose={() => {
          setDraft(null);
          setEditing(null);
        }}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setDraft(null);
                setEditing(null);
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={submitDraft}
              loading={createQuestion.isPending || updateQuestion.isPending}
            >
              Save
            </Button>
          </>
        }
      >
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submitDraft();
          }}
        >
          {formError ? <Alert>{formError}</Alert> : null}
          {draft !== null ? (
            <>
              <Field
                label="Question"
                value={draft.text}
                placeholder="Explains concepts clearly."
                onChange={(event) =>
                  setDraft({ ...draft, text: event.target.value })
                }
                required
              />
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="criterion-select"
                  className="text-sm font-medium text-ink-700"
                >
                  Criterion
                </label>
                <select
                  id="criterion-select"
                  value={draft.criterion_id}
                  onChange={(event) =>
                    setDraft({ ...draft, criterion_id: Number(event.target.value) })
                  }
                  className="rounded-md bg-white px-3 py-2 text-sm text-ink-800 ring-1 ring-ink-200"
                >
                  {criterionList.data?.map((criterion) => (
                    <option key={criterion.id} value={criterion.id}>
                      {criterion.name}
                    </option>
                  ))}
                </select>
              </div>
            </>
          ) : null}
          <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
        </form>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete question"
        busy={removeQuestion.isPending}
        message={
          deleting === null ? null : (
            <>
              Delete <strong>{deleting.text}</strong>? Questions that already have
              ratings against them cannot be removed.
            </>
          )
        }
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}

/**
 * Reordering is buttons rather than drag-and-drop, deliberately. Drag needs a
 * keyboard and touch fallback to be usable at all, and this list is short;
 * buttons are operable by every input method without one.
 */
function MoveButton({
  label,
  disabled,
  onClick,
  direction,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  direction: 'up' | 'down';
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded px-2 py-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-30"
    >
      <span aria-hidden="true">{direction === 'up' ? '↑' : '↓'}</span>
    </button>
  );
}
