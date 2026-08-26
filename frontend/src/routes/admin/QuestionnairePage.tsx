import { useMemo, useState } from 'react';

import { ApiError } from '@/api/client';
import {
  criteria,
  questions,
  terms,
  useCopyQuestionnaire,
  useDepartments,
  useReorder,
} from '@/api/resources';
import type { Criterion, Question } from '@/api/types';
import { ConfirmDialog, Dialog } from '@/components/Dialog';
import { Alert, Button, Card, Field } from '@/components/ui';
import { Badge } from '@/components/DataTable';
import { TermPicker, useSelectedTerm } from '@/routes/admin/TermPicker';

interface Group {
  criterion: Criterion;
  items: Question[];
}

interface QuestionDraft {
  text: string;
  // Empty string in the form, sent as null: an empty translation and no
  // translation mean the same thing and must not be stored differently.
  text_ta: string;
  criterion_id: number;
  curriculum: string | null;
}

/** Everyone's questions first, then each department's block, so the list on
 *  screen reads in the order a student meets it. */
function byScope(a: Question, b: Question): number {
  const scopeA = a.curriculum ?? '';
  const scopeB = b.curriculum ?? '';
  if (scopeA !== scopeB) return scopeA.localeCompare(scopeB);
  return a.position - b.position || a.id - b.id;
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
  const [draft, setDraft] = useState<QuestionDraft | null>(null);
  const [deleting, setDeleting] = useState<Question | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [copySource, setCopySource] = useState<number | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  const departments = useDepartments();
  const copyQuestionnaire = useCopyQuestionnaire();

  async function copyForward() {
    if (copySource === null || termId === null) return;
    setCopyError(null);
    try {
      await copyQuestionnaire.mutateAsync({
        source_term_id: copySource,
        target_term_id: termId,
      });
      setCopySource(null);
    } catch (cause) {
      setCopyError(messageFrom(cause, 'Could not copy that questionnaire.'));
    }
  }

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
        items: (byCriterion.get(criterion.id) ?? []).sort(byScope),
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
          text_ta: draft.text_ta.trim() || null,
          curriculum: draft.curriculum,
        });
      } else {
        await updateQuestion.mutateAsync({
          id: editing.id,
          body: { ...draft, text_ta: draft.text_ta.trim() || null },
        });
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
                setDraft({
                  text: '',
                  text_ta: '',
                  criterion_id: firstCriterionId,
                  curriculum: null,
                });
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
          <p className="py-6 text-center text-sm text-faint">
            Add criteria first — questions are grouped under them.
          </p>
        ) : groups.length === 0 ? (
          <p className="py-6 text-center text-sm text-faint">
            No questions for {term?.year ?? 'this year'} yet.
          </p>
        ) : (
          <div className="flex flex-col gap-6">
            {groups.map((group, groupIndex) => (
              <section key={group.criterion.id}>
                <header className="mb-2 flex items-center justify-between gap-2 border-b border-line pb-1">
                  <h3 className="text-sm font-semibold text-heading">
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
                      className="flex items-center gap-2 border-b border-line py-2 last:border-0"
                    >
                      <span className="w-6 text-xs text-faint tabular-nums">
                        {index + 1}.
                      </span>
                      <span className="flex-1 text-sm text-body">{question.text}</span>
                      {question.curriculum ? (
                        <Badge tone="caution">{question.curriculum} only</Badge>
                      ) : null}
                      {question.text_ta ? null : (
                        <Badge>No Tamil</Badge>
                      )}

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
                            text_ta: question.text_ta ?? '',
                            criterion_id: question.criterion_id,
                            curriculum: question.curriculum,
                          });
                          setFormError(null);
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        className="text-bad"
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

      {termId !== null && groups.length === 0 && (termList.data?.length ?? 0) > 1 ? (
        <Card title="Start from a previous term">
          <p className="mb-3 max-w-prose text-sm text-muted">
            Copies the questions and their departments across. Retyping them is
            how the wording drifted between terms, and wording that changes
            without anyone deciding to change it makes the term-on-term
            comparison a comparison of two different questions.
          </p>
          {copyError ? <Alert>{copyError}</Alert> : null}
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="copy-source" className="text-sm font-medium text-body">
                Copy from
              </label>
              <select
                id="copy-source"
                value={copySource ?? ''}
                onChange={(event) => setCopySource(Number(event.target.value) || null)}
                className="rounded-md bg-surface px-3 py-2 text-sm text-heading ring-1 ring-line-strong"
              >
                <option value="">Choose a term</option>
                {(termList.data ?? [])
                  .filter((candidate) => candidate.id !== termId)
                  .map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.year} semester {candidate.semester}
                    </option>
                  ))}
              </select>
            </div>
            <Button
              disabled={copySource === null}
              loading={copyQuestionnaire.isPending}
              onClick={() => void copyForward()}
            >
              Copy questionnaire
            </Button>
          </div>
        </Card>
      ) : null}

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
              <Field
                label="Question in Tamil (optional)"
                lang="ta"
                value={draft.text_ta}
                placeholder="கருத்துகளைத் தெளிவாக விளக்குகிறார்."
                onChange={(event) =>
                  setDraft({ ...draft, text_ta: event.target.value })
                }
              />
              <p className="-mt-1 text-xs text-faint">
                Left blank, Tamil readers see the English wording. The question
                is still asked — an untranslated question falls back rather
                than disappearing from their form.
              </p>
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="criterion-select"
                  className="text-sm font-medium text-body"
                >
                  Criterion
                </label>
                <select
                  id="criterion-select"
                  value={draft.criterion_id}
                  onChange={(event) =>
                    setDraft({ ...draft, criterion_id: Number(event.target.value) })
                  }
                  className="rounded-md bg-surface px-3 py-2 text-sm text-heading ring-1 ring-line-strong"
                >
                  {criterionList.data?.map((criterion) => (
                    <option key={criterion.id} value={criterion.id}>
                      {criterion.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="scope-select"
                  className="text-sm font-medium text-body"
                >
                  Who answers this
                </label>
                <select
                  id="scope-select"
                  value={draft.curriculum ?? ''}
                  onChange={(event) =>
                    setDraft({ ...draft, curriculum: event.target.value || null })
                  }
                  className="rounded-md bg-surface px-3 py-2 text-sm text-heading ring-1 ring-line-strong"
                >
                  <option value="">Every department</option>
                  {departments.data?.map((department) => (
                    <option key={department} value={department}>
                      {department} only
                    </option>
                  ))}
                </select>
                <p className="text-xs text-faint">
                  A question limited to one department is left out of every other
                  department&apos;s form and report, rather than showing there
                  with no answers.
                </p>
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
      className="rounded px-2 py-1 text-faint hover:bg-sunken hover:text-body disabled:cursor-not-allowed disabled:opacity-30"
    >
      <span aria-hidden="true">{direction === 'up' ? '↑' : '↓'}</span>
    </button>
  );
}
