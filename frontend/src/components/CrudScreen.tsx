import { useState, type ReactNode } from 'react';

import { ApiError } from '@/api/client';
import { ConfirmDialog, Dialog } from '@/components/Dialog';
import { DataTable, type Column } from '@/components/DataTable';
import { Alert, Button, Card } from '@/components/ui';

/** The subset of a resource module this screen needs. */
interface ResourceHooks<T, TForm> {
  useList: (query?: undefined) => {
    data: T[] | undefined;
    isLoading: boolean;
    error: unknown;
  };
  useCreate: () => {
    mutateAsync: (body: TForm) => Promise<T>;
    isPending: boolean;
  };
  useUpdate: () => {
    mutateAsync: (args: { id: number; body: Partial<TForm> }) => Promise<T>;
    isPending: boolean;
  };
  useRemove: () => {
    mutateAsync: (id: number) => Promise<void>;
    isPending: boolean;
  };
}

interface CrudScreenProps<T extends { id: number }, TForm> {
  title: string;
  /** Singular, lowercase — used in button labels and confirmations. */
  noun: string;
  resource: ResourceHooks<T, TForm>;
  columns: Column<T>[];
  blankForm: TForm;
  toForm: (row: T) => TForm;
  renderForm: (value: TForm, set: <K extends keyof TForm>(key: K, next: TForm[K]) => void) => ReactNode;
  describe: (row: T) => string;
  /** Rows that must not be edited or deleted, with the reason shown. */
  locked?: (row: T) => string | null;
  extraActions?: (row: T) => ReactNode;
  empty?: string;
}

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

export function CrudScreen<T extends { id: number }, TForm>({
  title,
  noun,
  resource,
  columns,
  blankForm,
  toForm,
  renderForm,
  describe,
  locked,
  extraActions,
  empty,
}: CrudScreenProps<T, TForm>) {
  const list = resource.useList(undefined);
  const create = resource.useCreate();
  const update = resource.useUpdate();
  const remove = resource.useRemove();

  const [editing, setEditing] = useState<T | null>(null);
  const [form, setForm] = useState<TForm | null>(null);
  const [deleting, setDeleting] = useState<T | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  function set<K extends keyof TForm>(key: K, next: TForm[K]) {
    setForm((current) => (current === null ? current : { ...current, [key]: next }));
  }

  function openCreate() {
    setEditing(null);
    setForm(blankForm);
    setFormError(null);
  }

  function openEdit(row: T) {
    setEditing(row);
    setForm(toForm(row));
    setFormError(null);
  }

  function closeForm() {
    setForm(null);
    setEditing(null);
    setFormError(null);
  }

  async function submit() {
    if (form === null) return;
    setFormError(null);
    try {
      if (editing === null) {
        await create.mutateAsync(form);
      } else {
        await update.mutateAsync({ id: editing.id, body: form });
      }
      closeForm();
    } catch (error) {
      // 409 and 422 messages are written for people to read — the API says
      // "That subject code is already in use", not "constraint violation".
      setFormError(messageFrom(error, `Could not save this ${noun}.`));
    }
  }

  async function confirmDelete() {
    if (deleting === null) return;
    setListError(null);
    try {
      await remove.mutateAsync(deleting.id);
      setDeleting(null);
    } catch (error) {
      // The API refuses to delete rows other records depend on and explains
      // which. Surfacing that verbatim is the whole point of the 409.
      setListError(messageFrom(error, `Could not delete this ${noun}.`));
      setDeleting(null);
    }
  }

  const saving = create.isPending || update.isPending;

  return (
    <div className="flex flex-col gap-4">
      {listError ? <Alert>{listError}</Alert> : null}

      <Card
        title={title}
        actions={<Button onClick={openCreate}>Add {noun}</Button>}
      >
        <DataTable
          rows={list.data}
          columns={columns}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.error}
          empty={empty ?? `No ${noun}s yet.`}
          actions={(row) => {
            const lockReason = locked?.(row) ?? null;
            return (
              <div className="flex items-center justify-end gap-1">
                {extraActions?.(row)}
                <Button variant="ghost" onClick={() => openEdit(row)}>
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setDeleting(row)}
                  disabled={lockReason !== null}
                  title={lockReason ?? undefined}
                  className="text-critical-600"
                >
                  Delete
                </Button>
              </div>
            );
          }}
        />
      </Card>

      <Dialog
        open={form !== null}
        title={editing === null ? `Add ${noun}` : `Edit ${noun}`}
        onClose={closeForm}
        footer={
          <>
            <Button variant="secondary" onClick={closeForm} disabled={saving}>
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
          {form !== null ? renderForm(form, set) : null}
          {/* Lets Enter submit the form without a visible duplicate button. */}
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
              Delete <strong>{describe(deleting)}</strong>? This cannot be undone.
            </>
          )
        }
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
