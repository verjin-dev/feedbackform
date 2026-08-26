import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { ApiError, api } from '@/api/client';
import type { CommentPrompt, PendingAssignment, Questionnaire } from '@/api/types';
import { Alert, Button, Card, cx } from '@/components/ui';

const SCALE = [
  { value: 1, label: 'Poor' },
  { value: 2, label: 'Satisfactory' },
  { value: 3, label: 'Good' },
  { value: 4, label: 'Very good' },
  { value: 5, label: 'Excellent' },
] as const;

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

export function EvaluatePage() {
  const queryClient = useQueryClient();

  const pending = useQuery({
    queryKey: ['pending-assignments'],
    queryFn: () => api.get<PendingAssignment[]>('/me/assignments/pending'),
    retry: false,
  });

  const questionnaire = useQuery({
    queryKey: ['questionnaire'],
    queryFn: () => api.get<Questionnaire>('/me/questionnaire'),
    retry: false,
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [justSubmitted, setJustSubmitted] = useState<string | null>(null);
  const [showMissing, setShowMissing] = useState(false);

  const assignments = pending.data ?? [];
  const selected =
    assignments.find((entry) => entry.assignment_id === selectedId) ?? assignments[0] ?? null;

  // Follow the list when the current selection is submitted and disappears.
  useEffect(() => {
    if (selected && selected.assignment_id !== selectedId) {
      setSelectedId(selected.assignment_id);
    }
  }, [selected, selectedId]);

  const submit = useMutation({
    mutationFn: (body: {
      assignment_id: number;
      ratings: { question_id: number; rating: number }[];
      comments: { prompt: CommentPrompt; text: string }[];
    }) =>
      api.post<{ assignment_id: number; answers_recorded: number }>('/evaluations', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pending-assignments'] });
    },
  });

  const allQuestions = useMemo(
    () => (questionnaire.data?.criteria ?? []).flatMap((block) => block.questions),
    [questionnaire.data],
  );
  const answeredCount = allQuestions.filter((q) => answers[q.id] !== undefined).length;
  const complete = allQuestions.length > 0 && answeredCount === allQuestions.length;

  // --- Window and completion states ---------------------------------------

  const status = questionnaire.data?.term.status;

  if (questionnaire.isLoading || pending.isLoading) {
    return (
      <p className="py-10 text-center text-sm text-ink-400" role="status">
        Loading...
      </p>
    );
  }

  const loadError = questionnaire.error ?? pending.error;
  if (loadError instanceof ApiError && loadError.isConflict) {
    // No current term configured at all.
    return (
      <Notice title="Not available yet">
        Feedback has not been set up for this year. Please check back later.
      </Notice>
    );
  }

  if (status === 'pending') {
    return (
      <Notice title="Not started yet">
        The feedback period for {questionnaire.data?.term.year} has not opened. You
        will be able to give feedback once your college opens it.
      </Notice>
    );
  }

  if (status === 'closed') {
    return (
      <Notice title="Feedback is closed">
        The feedback period for {questionnaire.data?.term.year} has ended. Thank you
        to everyone who took part.
      </Notice>
    );
  }

  if (assignments.length === 0) {
    return (
      <Notice title="All done" tone="positive">
        You have given feedback for every subject this year. Thank you — there is
        nothing left to do.
      </Notice>
    );
  }

  // --- The form -----------------------------------------------------------

  async function handleSubmit() {
    if (selected === null) return;
    setError(null);

    if (!complete) {
      setShowMissing(true);
      return;
    }

    try {
      await submit.mutateAsync({
        assignment_id: selected.assignment_id,
        ratings: allQuestions.map((question) => ({
          question_id: question.id,
          rating: answers[question.id] as number,
        })),
        comments: Object.entries(comments)
          .filter(([, text]) => text.trim() !== '')
          .map(([prompt, text]) => ({ prompt: prompt as CommentPrompt, text })),
      });
      setJustSubmitted(`${selected.subject_code} — ${selected.faculty_name}`);
      setAnswers({});
      setComments({});
      setShowMissing(false);
      setSelectedId(null);
    } catch (cause) {
      setError(messageFrom(cause, 'Your feedback could not be saved. Please try again.'));
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      {justSubmitted ? (
        <Alert tone="positive">
          Feedback submitted for {justSubmitted}. Thank you.
        </Alert>
      ) : null}
      {error ? <Alert>{error}</Alert> : null}

      <Card title="Subjects to review">
        <p className="mb-3 text-sm text-ink-500">
          {assignments.length} left. Your answers are recorded without your name,
          and your instructor sees only combined results for the whole class.
        </p>

        {/* A horizontal scroller on phones, a wrapped list on wider screens.
            The legacy sidebar was a fixed 3-column grid that pushed the form
            off-screen below 768px. */}
        <ul className="flex gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible">
          {assignments.map((entry) => {
            const active = selected?.assignment_id === entry.assignment_id;
            return (
              <li key={entry.assignment_id}>
                <button
                  type="button"
                  aria-current={active ? 'true' : undefined}
                  onClick={() => {
                    setSelectedId(entry.assignment_id);
                    setAnswers({});
                    setComments({});
                    setShowMissing(false);
                    setError(null);
                  }}
                  className={cx(
                    'rounded-md border px-3 py-2 text-left text-sm whitespace-nowrap transition-colors',
                    active
                      ? 'border-accent-500 bg-accent-50 text-accent-700'
                      : 'border-ink-200 bg-white text-ink-600 hover:bg-ink-50',
                  )}
                >
                  <span className="block font-medium">{entry.subject_code}</span>
                  <span className="block text-xs text-ink-500">{entry.faculty_name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </Card>

      {selected ? (
        <Card
          title={`${selected.subject_name} · ${selected.faculty_name}`}
          actions={
            <span className="text-sm tabular-nums text-ink-500">
              {answeredCount} of {allQuestions.length} answered
            </span>
          }
        >
          {showMissing && !complete ? (
            <div className="mb-4">
              <Alert tone="caution">
                Please answer every question before submitting. Unanswered ones are
                marked below.
              </Alert>
            </div>
          ) : null}

          <form
            onSubmit={(event) => {
              event.preventDefault();
              void handleSubmit();
            }}
            className="flex flex-col gap-6"
          >
            {questionnaire.data?.criteria.map((block) => (
              <section key={block.criterion_id}>
                <h3 className="mb-2 border-b border-ink-100 pb-1 text-sm font-semibold text-ink-800">
                  {block.name}
                </h3>

                <div className="flex flex-col gap-4">
                  {block.questions.map((question) => {
                    const value = answers[question.id];
                    const missing = showMissing && value === undefined;

                    return (
                      <fieldset
                        key={question.id}
                        className={cx(
                          'rounded-md border p-3',
                          missing ? 'border-critical-600 bg-critical-100/40' : 'border-ink-100',
                        )}
                      >
                        <legend className="px-1 text-sm text-ink-700">
                          {question.text}
                          {missing ? (
                            <span className="ml-2 text-xs text-critical-600">
                              Not answered
                            </span>
                          ) : null}
                        </legend>

                        {/* Each option carries its own word. The legacy form
                            showed bare 1-5 columns under a legend printed once
                            at the top of the page, so on a phone the numbers
                            were unlabelled by the time you scrolled to them. */}
                        <div className="mt-2 grid grid-cols-5 gap-1">
                          {SCALE.map((option) => (
                            <label
                              key={option.value}
                              className={cx(
                                'flex cursor-pointer flex-col items-center gap-1 rounded-md border px-1 py-2 text-center transition-colors',
                                value === option.value
                                  ? 'border-accent-500 bg-accent-50'
                                  : 'border-ink-200 hover:bg-ink-50',
                              )}
                            >
                              <input
                                type="radio"
                                name={`question-${question.id}`}
                                value={option.value}
                                // Never defaulted. The legacy form pre-checked
                                // 5 for every question, so a student could
                                // submit a full set of top marks without
                                // reading one of them.
                                checked={value === option.value}
                                onChange={() => {
                                  setAnswers((current) => ({
                                    ...current,
                                    [question.id]: option.value,
                                  }));
                                }}
                                className="sr-only"
                              />
                              {/* Not aria-hidden: the accessible name should
                                  be "5 Excellent", matching what is on screen,
                                  rather than the word alone. */}
                              <span
                                className={cx(
                                  'text-sm font-semibold tabular-nums',
                                  value === option.value ? 'text-accent-700' : 'text-ink-500',
                                )}
                              >
                                {option.value}
                              </span>
                              <span className="text-[11px] leading-tight text-ink-500">
                                {option.label}
                              </span>
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    );
                  })}
                </div>
              </section>
            ))}

            {/* Written feedback. Optional, and last: it is the most useful
                thing a student can give and the most effort to give, so it
                comes after the part that is quick. */}
            {questionnaire.data?.comment_prompts?.length ? (
              <section className="rounded-md border border-ink-100 p-4">
                <h3 className="text-sm font-semibold text-ink-800">
                  Anything you want to say in your own words?
                </h3>

                {/* The fourth safeguard, and the only one that is not code:
                    the rules are stated before anyone types, not after. */}
                <p className="mt-1 mb-3 text-xs leading-relaxed text-ink-500">
                  Optional. Your instructor sees these only after the feedback
                  period closes and marks are in, and only if enough of your
                  class responded. They are shown without your name — but
                  describing a specific moment can still identify you to someone
                  who was in the room, so keep it about the teaching.
                </p>

                <div className="flex flex-col gap-3">
                  {questionnaire.data.comment_prompts?.map((entry) => {
                    const value = comments[entry.prompt] ?? '';
                    return (
                      <label key={entry.prompt} className="flex flex-col gap-1.5">
                        <span className="text-sm text-ink-700">{entry.text}</span>
                        <textarea
                          rows={3}
                          maxLength={1500}
                          value={value}
                          onChange={(event) =>
                            setComments((current) => ({
                              ...current,
                              [entry.prompt]: event.target.value,
                            }))
                          }
                          className="w-full rounded-md bg-white px-3 py-2 text-sm text-ink-800 ring-1 ring-ink-200 placeholder:text-ink-400"
                          placeholder="Leave blank if you would rather not."
                        />
                        {value.length > 1200 ? (
                          <span className="text-xs text-ink-400 tabular-nums">
                            {1500 - value.length} characters left
                          </span>
                        ) : null}
                      </label>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {/* Full width and a comfortable target on phones, which is how
                most students will do this. */}
            <div className="flex flex-col gap-3 border-t border-ink-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-sm text-ink-500">
                {complete ? 'Ready to submit.' : `${allQuestions.length - answeredCount} left.`}
              </span>
              <Button
                type="submit"
                loading={submit.isPending}
                className="min-h-11 w-full sm:w-auto"
              >
                Submit feedback
              </Button>
            </div>
          </form>
        </Card>
      ) : null}
    </div>
  );
}

function Notice({
  title,
  children,
  tone = 'neutral',
}: {
  title: string;
  children: React.ReactNode;
  tone?: 'neutral' | 'positive';
}) {
  return (
    <div className="mx-auto w-full max-w-lg">
      <Card>
        <div className="py-6 text-center">
          <h2
            className={cx(
              'text-base font-semibold',
              tone === 'positive' ? 'text-positive-600' : 'text-ink-800',
            )}
          >
            {title}
          </h2>
          <p className="mt-2 text-sm text-ink-500">{children}</p>
        </div>
      </Card>
    </div>
  );
}
