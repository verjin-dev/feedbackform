import { useEffect, useRef, type ReactNode } from 'react';

import { Button } from '@/components/ui';

/**
 * Modal built on the native <dialog> element.
 *
 * showModal() gives focus trapping, Escape-to-close, inert background and the
 * top layer for free — all of which AdminLTE's Bootstrap modals reimplemented
 * in JavaScript, and several of which the legacy app got wrong (its modals
 * were reachable by keyboard while nominally hidden).
 */
export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (element === null) return;

    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  if (!open) return null;

  return (
    <dialog
      ref={ref}
      // Fires for Escape and for the close() call alike, so the parent's state
      // cannot drift out of sync with what is on screen.
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      // Clicking the backdrop hits the dialog element itself rather than any
      // child, which is what distinguishes it from a click inside.
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      aria-labelledby="dialog-title"
      className="w-full max-w-md rounded-xl bg-raised p-0 text-body shadow-e3 ring-1 ring-line backdrop:bg-overlay backdrop:backdrop-blur-sm open:flex open:flex-col"
    >
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <h2 id="dialog-title" className="text-sm font-semibold text-heading">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded px-2 text-faint hover:text-body"
        >
          &times;
        </button>
      </header>

      <div className="px-5 py-4">{children}</div>

      {footer ? (
        <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">
          {footer}
        </footer>
      ) : null}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Delete',
  destructive = true,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={busy}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm text-muted">{message}</div>
    </Dialog>
  );
}
