import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { api } from '@/api/client';
import type { Account } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import {
  normaliseLanguage,
  translate,
  type Language,
  type StringKey,
} from '@/i18n/strings';

const GUEST_KEY = 'evaluation.language';

/**
 * Which language to render in, and how to change it.
 *
 * Signed in, the answer comes from the account, because students share lab
 * machines and a preference that follows the machine rather than the person is
 * a preference that keeps being wrong. Signed out there is no account to hang
 * it on, so the sign-in page alone falls back to this browser — enough to read
 * the form you are about to sign in with.
 */
export function useLanguage() {
  const { account } = useAuth();
  const queryClient = useQueryClient();

  const stored = readGuestLanguage();
  const language = account ? normaliseLanguage(account.language) : stored;

  const mutation = useMutation({
    mutationFn: (next: Language) =>
      api.post<Account>('/auth/me/language', { language: next }),
    onSuccess: (updated) => queryClient.setQueryData(['auth', 'me'], updated),
  });

  const setLanguage = useCallback(
    async (next: Language) => {
      writeGuestLanguage(next);
      // Signed out there is nothing to save it against, and the sign-in page
      // is the only screen that can be read in that state.
      if (account) await mutation.mutateAsync(next);
    },
    [account, mutation],
  );

  const t = useCallback(
    (key: StringKey, values?: Record<string, string | number>) =>
      translate(language, key, values),
    [language],
  );

  return { language, setLanguage, t, isSaving: mutation.isPending };
}

function readGuestLanguage(): Language {
  try {
    return normaliseLanguage(window.localStorage.getItem(GUEST_KEY));
  } catch {
    // Private windows and locked-down browsers throw on access rather than
    // returning null. English is a working default, not an error.
    return 'en';
  }
}

function writeGuestLanguage(language: Language): void {
  try {
    window.localStorage.setItem(GUEST_KEY, language);
  } catch {
    // Nothing to do: the preference is saved on the account a moment later,
    // and a guest who cannot store it simply chooses again.
  }
}
