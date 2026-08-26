import { useState } from 'react';

import { ApiError } from '@/api/client';
import { accounts, classes, type AccountInput } from '@/api/resources';
import type { Account, Role } from '@/api/types';
import { Badge, DataTable } from '@/components/DataTable';
import { ConfirmDialog, Dialog } from '@/components/Dialog';
import { Alert, Button, Card, Field } from '@/components/ui';

interface FormState {
  first_name: string;
  last_name: string;
  email: string;
  school_id: string;
  password: string;
  class_group_id: number | null;
  is_active: boolean;
}

const BLANK: FormState = {
  first_name: '',
  last_name: '',
  email: '',
  school_id: '',
  password: '',
  class_group_id: null,
  is_active: true,
};

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

/**
 * Serves /admin/faculty, /admin/students and /admin/users.
 *
 * The legacy app had new_faculty.php, new_student.php and new_user.php over
 * three near-identical tables, each with its own save_* endpoint. There is one
 * account resource now, so there is one screen.
 */
export function AccountsPage({ role, title }: { role: Role; title: string }) {
  const list = accounts.useList({ role });
  const create = accounts.useCreate();
  const update = accounts.useUpdate();
  const remove = accounts.useRemove();
  const classList = classes.useList(undefined, { enabled: role === 'student' });

  const [form, setForm] = useState<FormState | null>(null);
  const [editing, setEditing] = useState<Account | null>(null);
  const [deleting, setDeleting] = useState<Account | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, next: FormState[K]) {
    setForm((current) => (current === null ? current : { ...current, [key]: next }));
  }

  function openCreate() {
    setEditing(null);
    setForm(BLANK);
    setFormError(null);
  }

  function openEdit(row: Account) {
    setEditing(row);
    setForm({
      first_name: row.first_name,
      last_name: row.last_name,
      email: row.email,
      school_id: row.school_id ?? '',
      // Never populated from the server — the API does not return a hash and
      // an empty field here means "leave the password alone".
      password: '',
      class_group_id: row.class_group_id,
      is_active: true,
    });
    setFormError(null);
  }

  function close() {
    setForm(null);
    setEditing(null);
    setFormError(null);
  }

  async function submit() {
    if (form === null) return;
    setFormError(null);

    const shared = {
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email,
      school_id: form.school_id === '' ? null : form.school_id,
      class_group_id: role === 'student' ? form.class_group_id : null,
    };

    try {
      if (editing === null) {
        await create.mutateAsync({ role, password: form.password, ...shared } as AccountInput);
      } else {
        await update.mutateAsync({
          id: editing.id,
          // Omitting password entirely leaves the existing one untouched;
          // sending an empty string would fail the 12-character minimum.
          body: form.password === '' ? shared : { ...shared, password: form.password },
        });
      }
      close();
    } catch (error) {
      setFormError(messageFrom(error, 'Could not save this account.'));
    }
  }

  async function confirmDelete() {
    if (deleting === null) return;
    setListError(null);
    try {
      await remove.mutateAsync(deleting.id);
      setDeleting(null);
    } catch (error) {
      // The API refuses to delete an account referenced by assignments or
      // evaluations, and says to deactivate instead.
      setListError(messageFrom(error, 'Could not delete this account.'));
      setDeleting(null);
    }
  }

  const saving = create.isPending || update.isPending;
  const noun = role === 'faculty' ? 'faculty member' : role === 'student' ? 'student' : 'administrator';

  return (
    <div className="flex flex-col gap-4">
      {listError ? <Alert>{listError}</Alert> : null}

      <Card title={title} actions={<Button onClick={openCreate}>Add {noun}</Button>}>
        <DataTable
          rows={list.data}
          columns={[
            { header: 'Name', cell: (row) => row.full_name },
            { header: 'Email', cell: (row) => row.email },
            {
              header: role === 'student' ? 'Roll number' : 'Staff id',
              cell: (row) => row.school_id ?? '—',
            },
            ...(role === 'student'
              ? [
                  {
                    header: 'Class',
                    cell: (row: Account) =>
                      classList.data?.find((c) => c.id === row.class_group_id)?.label ??
                      '—',
                  },
                ]
              : []),
          ]}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.error}
          empty={`No ${noun}s yet.`}
          actions={(row) => (
            <div className="flex items-center justify-end gap-1">
              <Button variant="ghost" onClick={() => openEdit(row)}>
                Edit
              </Button>
              <Button
                variant="ghost"
                className="text-bad"
                onClick={() => setDeleting(row)}
              >
                Delete
              </Button>
            </div>
          )}
        />
      </Card>

      <Dialog
        open={form !== null}
        title={editing === null ? `Add ${noun}` : `Edit ${noun}`}
        onClose={close}
        footer={
          <>
            <Button variant="secondary" onClick={close} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={submit} loading={saving}>
              Save
            </Button>
          </>
        }
      >
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {formError ? <Alert>{formError}</Alert> : null}
          {form !== null ? (
            <>
              <Field
                label="First name"
                value={form.first_name}
                onChange={(event) => set('first_name', event.target.value)}
                required
              />
              <Field
                label="Last name"
                value={form.last_name}
                onChange={(event) => set('last_name', event.target.value)}
                required
              />
              <Field
                label="Email"
                type="email"
                autoComplete="off"
                value={form.email}
                onChange={(event) => set('email', event.target.value)}
                required
              />
              <Field
                label={role === 'student' ? 'Roll number' : 'Staff id'}
                value={form.school_id}
                onChange={(event) => set('school_id', event.target.value)}
              />

              {role === 'student' ? (
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="class-select" className="text-sm font-medium text-body">
                    Class
                  </label>
                  <select
                    id="class-select"
                    required
                    value={form.class_group_id ?? ''}
                    onChange={(event) =>
                      set(
                        'class_group_id',
                        event.target.value === '' ? null : Number(event.target.value),
                      )
                    }
                    className="rounded-md bg-surface px-3 py-2 text-sm text-heading ring-1 ring-line-strong"
                  >
                    <option value="">Select a class</option>
                    {classList.data?.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.label}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}

              <Field
                label={editing === null ? 'Password' : 'New password'}
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={(event) => set('password', event.target.value)}
                required={editing === null}
                hint={
                  editing === null
                    ? 'At least 12 characters.'
                    : 'Leave blank to keep the current password.'
                }
              />
            </>
          ) : null}
          <button type="submit" className="hidden" aria-hidden="true" tabIndex={-1} />
        </form>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title={`Delete ${noun}`}
        busy={remove.isPending}
        message={
          deleting === null ? null : (
            <>
              Delete <strong>{deleting.full_name}</strong>? Accounts with evaluation
              history cannot be deleted — deactivate them instead.
            </>
          )
        }
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}

export const FacultyPage = () => <AccountsPage role="faculty" title="Faculty" />;
export const StudentsPage = () => <AccountsPage role="student" title="Students" />;
export const AdminUsersPage = () => (
  <AccountsPage role="admin" title="Administrators" />
);

export { Badge };
