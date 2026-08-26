import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '@/api/client';
import { Alert, Button, Card, cx } from '@/components/ui';
import { useLanguage } from '@/i18n/useLanguage';

interface PendingPulse {
  round_id: number;
  subject_code: string;
  subject_name: string;
  faculty_name: string;
}

/** The wording is translated; the numbers are not. */
const PACE = [1, 2, 3, 4, 5] as const;

/**
 * The mid-term check, from the student's side.
 *
 * Three questions, and the copy leads with the reason to bother: unlike the
 * end-of-term evaluation, this one can change the subject they are still
 * sitting in. That is the only honest argument for filling it in, so it is the
 * one made.
 */
export function PulsePrompt() {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const [active, setActive] = useState<number | null>(null);
  const [pace, setPace] = useState<number | null>(null);
  const [clarity, setClarity] = useState<number | null>(null);
  const [suggestion, setSuggestion] = useState('');
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pending = useQuery({
    queryKey: ['pulse', 'pending'],
    queryFn: () => api.get<PendingPulse[]>('/pulse/pending'),
    retry: false,
  });

  const reply = useMutation({
    mutationFn: ({ roundId }: { roundId: number }) =>
      api.post(`/pulse/rounds/${roundId}/reply`, {
        pace,
        clarity,
        suggestion: suggestion.trim() || null,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['pulse'] }),
  });

  const rounds = pending.data ?? [];
  if (pending.isError || (rounds.length === 0 && done === null)) return null;

  const current = rounds.find((round) => round.round_id === active) ?? rounds[0] ?? null;

  async function send() {
    if (current === null || pace === null || clarity === null) return;
    setError(null);
    try {
      await reply.mutateAsync({ roundId: current.round_id });
      setDone(current.subject_code);
      setPace(null);
      setClarity(null);
      setSuggestion('');
      setActive(null);
    } catch (cause) {
      setError(
        cause instanceof ApiError || cause instanceof Error
          ? cause.message
          : t('pulse.sendFailed'),
      );
    }
  }

  if (current === null) {
    return done ? (
      <Alert tone="positive">
        Thanks — your answer went straight to the instructor for {done}.
      </Alert>
    ) : null;
  }

  const ready = pace !== null && clarity !== null;

  return (
    <Card
      title={`Quick check: ${current.subject_code}`}
      actions={
        rounds.length > 1 ? (
          <span className="text-xs text-ink-400">
            {rounds.length} waiting
          </span>
        ) : null
      }
    >
      {error ? (
        <div className="mb-3">
          <Alert>{error}</Alert>
        </div>
      ) : null}

      <p className="mb-4 max-w-prose text-sm text-ink-500">
        {current.faculty_name} is asking how {current.subject_name} is going
        while there is still time to change it. Three questions, about twenty
        seconds. Only they see the answers, without your name, and they are
        deleted at the end of term.
      </p>

      <div className="flex flex-col gap-4">
        <fieldset>
          <legend className="mb-2 text-sm text-ink-700">
            How is the pace?
          </legend>
          <div className="flex flex-wrap gap-2">
            {PACE.map((option) => (
              <label
                key={option}
                className={cx(
                  'cursor-pointer rounded-md border px-3 py-2 text-xs transition-colors',
                  pace === option
                    ? 'border-accent-500 bg-accent-50 text-accent-700'
                    : 'border-ink-200 hover:bg-ink-50',
                )}
              >
                <input
                  type="radio"
                  name="pace"
                  className="sr-only"
                  checked={pace === option}
                  onChange={() => setPace(option)}
                />
                {t(`pace.${option}` as const)}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-sm text-ink-700">
            I know what is expected of me
          </legend>
          <div className="grid max-w-xs grid-cols-5 gap-1">
            {[1, 2, 3, 4, 5].map((value) => (
              <label
                key={value}
                className={cx(
                  'cursor-pointer rounded-md border py-2 text-center text-sm transition-colors',
                  clarity === value
                    ? 'border-accent-500 bg-accent-50 text-accent-700'
                    : 'border-ink-200 hover:bg-ink-50',
                )}
              >
                <input
                  type="radio"
                  name="clarity"
                  className="sr-only"
                  checked={clarity === value}
                  onChange={() => setClarity(value)}
                />
                {value}
              </label>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-ink-400">
            1 = not at all, 5 = completely
          </p>
        </fieldset>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm text-ink-700">
            One thing that would help you right now
          </span>
          <textarea
            rows={2}
            maxLength={600}
            value={suggestion}
            onChange={(event) => setSuggestion(event.target.value)}
            placeholder={t('pulse.optional')}
            className="w-full rounded-md bg-white px-3 py-2 text-sm text-ink-800 ring-1 ring-ink-200 placeholder:text-ink-400"
          />
        </label>

        <div className="flex justify-end">
          <Button
            onClick={send}
            loading={reply.isPending}
            disabled={!ready}
            className="min-h-11 w-full sm:w-auto"
          >
            Send to {current.faculty_name.split(' ')[0]}
          </Button>
        </div>
      </div>
    </Card>
  );
}
