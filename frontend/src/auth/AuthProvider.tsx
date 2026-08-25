import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useMemo, type ReactNode } from 'react';

import { ApiError, api } from '@/api/client';
import type { Account } from '@/api/types';

export interface AuthState {
  account: Account | null;
  /** True only until the first /auth/me settles. Guards must not redirect
   *  while this is true, or a reload bounces a signed-in user to /login. */
  isResolving: boolean;
  signIn: (email: string, password: string) => Promise<Account>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

const ME_KEY = ['auth', 'me'] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const { data, isPending } = useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api.get<Account>('/auth/me');
      } catch (error) {
        // Signed out is the expected answer here, not a failure worth
        // retrying or surfacing.
        if (error instanceof ApiError && error.isUnauthenticated) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const signInMutation = useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      api.post<Account>('/auth/login', credentials),
    onSuccess: (account) => queryClient.setQueryData(ME_KEY, account),
  });

  const signOutMutation = useMutation({
    mutationFn: () => api.post<void>('/auth/logout'),
    onSettled: () => {
      // Clear everything, not just the session: cached admin lists and reports
      // must not survive into the next account signed in on this machine.
      queryClient.clear();
      queryClient.setQueryData(ME_KEY, null);
    },
  });

  const value = useMemo<AuthState>(
    () => ({
      account: data ?? null,
      isResolving: isPending,
      signIn: (email, password) => signInMutation.mutateAsync({ email, password }),
      signOut: async () => {
        await signOutMutation.mutateAsync();
      },
    }),
    [data, isPending, signInMutation, signOutMutation],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
