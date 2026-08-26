import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';

import { api } from '@/api/client';
import type {
  AcademicTerm,
  Account,
  ClassGroup,
  Criterion,
  Question,
  Role,
  Subject,
} from '@/api/types';

type Query = Record<string, string | number | boolean | undefined>;

/**
 * One set of hooks per resource.
 *
 * Every mutation invalidates the resource's own list. Anything that also
 * affects a *different* resource declares that explicitly at the call site —
 * silent cross-invalidation is how a screen ends up showing stale data that
 * nobody can reproduce.
 */
function resource<T, TCreate, TUpdate>(path: string) {
  const listKey = (query?: Query) => [path, query ?? null] as const;

  return {
    listKey,

    useList(query?: Query, options?: Partial<UseQueryOptions<T[]>>) {
      return useQuery({
        queryKey: listKey(query),
        queryFn: () => api.get<T[]>(path, query),
        ...options,
      });
    },

    useCreate() {
      const client = useQueryClient();
      return useMutation({
        mutationFn: (body: TCreate) => api.post<T>(path, body),
        onSuccess: () => client.invalidateQueries({ queryKey: [path] }),
      });
    },

    useUpdate() {
      const client = useQueryClient();
      return useMutation({
        mutationFn: ({ id, body }: { id: number; body: TUpdate }) =>
          api.patch<T>(`${path}/${id}`, body),
        onSuccess: () => client.invalidateQueries({ queryKey: [path] }),
      });
    },

    useRemove() {
      const client = useQueryClient();
      return useMutation({
        mutationFn: (id: number) => api.delete<void>(`${path}/${id}`),
        onSuccess: () => client.invalidateQueries({ queryKey: [path] }),
      });
    },
  };
}

// --- Payload shapes, mirroring the backend request schemas ----------------

export interface TermInput {
  year: string;
  semester: number;
}
export interface ClassInput {
  curriculum: string;
  level: string;
  section: string;
}
export interface SubjectInput {
  code: string;
  name: string;
  description?: string | null;
}
export interface CriterionInput {
  name: string;
}
export interface QuestionInput {
  term_id: number;
  criterion_id: number;
  text: string;

  // Sent explicitly as null to move a department question back into the core;
  // omitted on a patch, the scope is left alone.
  curriculum?: string | null;
}
export interface AccountInput {
  role: Role;
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  school_id?: string | null;
  class_group_id?: number | null;
}
export interface AccountPatch {
  first_name?: string;
  last_name?: string;
  email?: string;
  password?: string;
  school_id?: string | null;
  class_group_id?: number | null;
  is_active?: boolean;
}

export const terms = resource<AcademicTerm, TermInput, Partial<TermInput>>(
  '/academic-years',
);
export const classes = resource<ClassGroup, ClassInput, Partial<ClassInput>>('/classes');
export const subjects = resource<Subject, SubjectInput, Partial<SubjectInput>>(
  '/subjects',
);
export const criteria = resource<Criterion, CriterionInput, Partial<CriterionInput>>(
  '/criteria',
);
export const questions = resource<Question, QuestionInput, Partial<QuestionInput>>(
  '/questions',
);
export const accounts = resource<Account, AccountInput, AccountPatch>('/accounts');

/** The departments a question can be scoped to, taken from the class groups so
 *  the two spellings cannot drift apart. */
export function useDepartments() {
  return useQuery({
    queryKey: ['questions', 'departments'],
    queryFn: () => api.get<string[]>('/questions/departments'),
  });
}

/** Carry a term's questionnaire forward rather than retyping it. Refused if the
 *  target already has questions, so it cannot silently duplicate or discard. */
export function useCopyQuestionnaire() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { source_term_id: number; target_term_id: number }) =>
      api.post<Question[]>('/questions/copy', body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['questions'] }),
  });
}

// --- Operations that are not plain CRUD -----------------------------------

export function useActivateTerm() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<AcademicTerm>(`/academic-years/${id}/activate`),
    // Activation changes which term everything else is read against, so the
    // whole cache is stale, not just the term list.
    onSuccess: () => client.invalidateQueries(),
  });
}

export function useReorder(path: '/criteria' | '/questions', query?: Query) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) =>
      api.put<void>(
        `${path}/order${query ? `?${new URLSearchParams(
          Object.entries(query)
            .filter((entry): entry is [string, string | number | boolean] =>
              entry[1] !== undefined,
            )
            .map(([key, value]) => [key, String(value)]),
        )}` : ''}`,
        { ids },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: [path] }),
  });
}
