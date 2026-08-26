import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { ApiError, api } from '@/api/client';
import type { CommentPrompt, PendingAssignment, Questionnaire } from '@/api/types';
import { Alert, Button, Card, cx } from '@/components/ui';
import { useLanguage } from '@/i18n/useLanguage';
import { PulsePrompt } from '@/routes/student/PulsePrompt';

/** The wording is translated; the numbers are not. A rating means the same
 *  thing in both languages and is stored as the number either way. */
const SCALE = [1, 2, 3, 4, 5] as const;

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

export function EvaluatePage() {
  const queryClient = useQueryClient();
  const { language, t } = useLanguage();

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
      <p className="py-10 text-center text-sm text-faint" role="status">
        Loading...
      </p>
    );
  }

  const loadError = questionnaire.error ?? pending.error;
  if (loadError instanceof ApiError && loadError.isConflict) {
    // No current term configured at all.
    return (
      <Notice title={t('evaluate.notAvailable')}>
        Feedback has not been set up for this year. Please check back later.
      </Notice>
    );
  }

  if (status === 'pending') {
    return (
      <Notice title={t('evaluate.notStarted')}>
        The feedback period for {questionnaire.data?.term.year} has not opened. You
        will be able to give feedback once your college opens it.
      </Notice>
    );
  }

  if (status === 'closed') {
    return (
      <Notice title={t('evaluate.closed')}>
        The feedback period for {questionnaire.data?.term.year} has ended. Thank you
        to everyone who took part.
      </Notice>
    );
  }

  if (assignments.length === 0) {
    return (
      <Notice title={t('evaluate.allDone')} tone="positive">
        You have given feedback for every subject this year. Thank you — there is
        nothing left to do.
      </Notice>
    );
  }

  // --- The form -----------------------------------------------------------

  const progressPercent = `${
    allQuestions.length === 0 ? 0 : (answeredCount / allQuestions.length) * 100
  }%`;

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
      setError(messageFrom(cause, t('evaluate.saveFailed')));
    }
  }

  return (
    // Declared on the form rather than on <html>: the question wording comes
    // back in the reader's language, and Tamil inside an element declared
    // English is read by a screen reader with English phonetics.
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4" lang={language}>
      {justSubmitted ? (
        <Alert tone="positive">
          Feedback submitted for {justSubmitted}. Thank you.
        </Alert>
      ) : null}
      {error ? <Alert>{error}</Alert> : null}

      <PulsePrompt />

      <Card title={t('evaluate.heading')}>
        <p className="mb-3 text-sm text-muted">
          {t('evaluate.remaining', { count: assignments.length })}{' '}
          {t('evaluate.anonymous')}
        </p>

        {/* A horizontal scroller on phones, a wrapped list on wider screens.
            The legacy sidebar was a fixed 3-column grid that pushed the form
            off-screen below 768px. */}
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
                    'flex h-full w-full flex-col gap-0.5 rounded-xl px-3.5 py-3 text-left',
                    'ring-1 transition-all duration-150',
                    active
                      ? 'bg-brand-soft text-brand-text shadow-e1 ring-brand/40'
                      : 'bg-surface text-body ring-line-strong hover:bg-sunken hover:ring-ink-300',
                  )}
                >
                  <span className="text-sm font-semibold">{entry.subject_code}</span>
                  <span className="truncate text-xs opacity-80">
                    {entry.subject_name}
                  </span>
                  <span className="mt-0.5 truncate text-xs text-muted">
                    {entry.faculty_name}
                  </span>
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
            <div className="flex items-center gap-2.5">
              {/* Redundant with the count beside it, deliberately: on a phone
                  this bar is the thing somebody actually reads to know how
                  much is left. */}
              <div
                aria-hidden="true"
                className="h-1.5 w-24 overflow-hidden rounded-full bg-sunken ring-1 ring-line"
              >
                <div
                  className={cx(
                    'h-full rounded-full transition-[width] duration-300',
                    complete ? 'bg-good' : 'bg-brand',
                  )}
                  style={{ width: progressPercent }}
                />
              </div>
              <span className="text-sm tabular-nums text-muted">
                {answeredCount} of {allQuestions.length} answered
              </span>
            </div>
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
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-heading">
                  {block.name}
                  <span aria-hidden="true" className="h-px flex-1 bg-line" />
                </h3>

                <div className="flex flex-col gap-4">
                  {block.questions.map((question) => {
                    const value = answers[question.id];
                    const missing = showMissing && value === undefined;

                    return (
                      <fieldset
                        key={question.id}
                        className={cx(
                          'rounded-xl bg-surface p-3.5 ring-1 transition-colors',
                          missing ? 'bg-bad-soft/40 ring-bad/40' : 'ring-line-strong',
                        )}
                      >
                        <legend className="flex flex-wrap items-center gap-2 px-1 text-sm text-body">
                          <span>{question.text}</span>
                          {missing ? (
                            <span className="rounded-full bg-bad-soft px-2 py-0.5 text-xs font-medium text-bad ring-1 ring-bad/25">
                              Not answered
                            </span>
                          ) : null}
                        </legend>

                        {/* Each option carries its own word. The legacy form
                            showed bare 1-5 columns under a legend printed once
                            at the top of the page, so on a phone the numbers
                            were unlabelled by the time you scrolled to them. */}
                        <div className="mt-3 grid grid-cols-5 gap-1.5">
                          {SCALE.map((option) => (
                            <label
                              key={option}
                              className={cx(
                                'flex min-h-16 cursor-pointer flex-col items-center justify-center gap-1',
                                'rounded-lg px-1 py-2 text-center ring-1',
                                'transition-all duration-150 active:scale-[0.97]',
                                // The ring thickens as well as changing
                                // colour, so the chosen option is never
                                // distinguished by hue alone.
                                value === option
                                  ? 'bg-brand-soft ring-2 ring-brand'
                                  : 'bg-surface ring-line-strong hover:bg-sunken hover:ring-ink-300',
                              )}
                            >
                              <input
                                type="radio"
                                name={`question-${question.id}`}
                                value={option}
                                // Never defaulted. The legacy form pre-checked
                                // 5 for every question, so a student could
                                // submit a full set of top marks without
                                // reading one of them.
                                checked={value === option}
                                onChange={() => {
                                  setAnswers((current) => ({
                                    ...current,
                                    [question.id]: option,
                                  }));
                                }}
                                className="sr-only"
                              />
                              {/* Not aria-hidden: the accessible name should
                                  be "5 Excellent", matching what is on screen,
                                  rather than the word alone. */}
                              <span
                                className={cx(
                                  'text-base leading-none font-semibold tabular-nums',
                                  value === option ? 'text-brand-text' : 'text-muted',
                                )}
                              >
                                {option}
                              </span>
                              <span
                                className={cx(
                                  'text-[11px] leading-tight',
                                  value === option ? 'text-brand-text' : 'text-muted',
                                )}
                              >
                                {t(`rating.${option}` as const)}
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
              <section className="rounded-md border border-line p-4">
                <h3 className="text-sm font-semibold text-heading">
                  Anything you want to say in your own words?
                </h3>

                {/* The fourth safeguard, and the only one that is not code:
                    the rules are stated before anyone types, not after. */}
                <p className="mt-1 mb-3 text-xs leading-relaxed text-muted">
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
                        <span className="text-sm text-body">{entry.text}</span>
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
                          className="w-full rounded-md bg-surface px-3 py-2 text-sm text-heading ring-1 ring-line-strong placeholder:text-faint"
                          placeholder={t('evaluate.optional')}
                        />
                        {value.length > 1200 ? (
                          <span className="text-xs text-faint tabular-nums">
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
            <div className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-sm text-muted">
                {complete
                  ? t('evaluate.ready')
                  : t('evaluate.remaining', {
                      count: allQuestions.length - answeredCount,
                    })}
              </span>
              <Button
                type="submit"
                loading={submit.isPending}
                className="min-h-11 w-full sm:w-auto"
              >
                {t('evaluate.submit')}
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
              tone === 'positive' ? 'text-good' : 'text-heading',
            )}
          >
            {title}
          </h2>
          <p className="mt-2 text-sm text-muted">{children}</p>
        </div>
      </Card>
    </div>
  );
}
