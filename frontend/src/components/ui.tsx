import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';
import { forwardRef, useId } from 'react';

function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}

// --- Button ---------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent-500 text-white hover:bg-accent-600',
  secondary: 'bg-white text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50',
  danger: 'bg-critical-600 text-white hover:brightness-110',
  ghost: 'text-ink-600 hover:bg-ink-100',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', loading = false, disabled, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      // A button that is busy must also be unclickable; relying on the caller
      // to pass both flags is how double submissions happen.
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-md px-4 py-2',
        'text-sm font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-60',
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

// --- Field ----------------------------------------------------------------

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string | undefined;
  hint?: string | undefined;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, error, hint, id, className, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium text-ink-700">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        // Wires the message to the input so a screen reader announces it,
        // rather than leaving it as red text floating nearby.
        aria-describedby={cx(error && errorId, hint && hintId) || undefined}
        className={cx(
          'rounded-md bg-white px-3 py-2 text-sm text-ink-800',
          'ring-1 ring-ink-200 placeholder:text-ink-400',
          error && 'ring-critical-600',
          className,
        )}
        {...rest}
      />
      {hint ? (
        <p id={hintId} className="text-xs text-ink-500">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-xs text-critical-600">
          {error}
        </p>
      ) : null}
    </div>
  );
});

// --- Alert ----------------------------------------------------------------

export function Alert({
  tone = 'critical',
  children,
}: {
  tone?: 'critical' | 'caution' | 'positive';
  children: ReactNode;
}) {
  const tones = {
    critical: 'bg-critical-100 text-critical-600',
    caution: 'bg-caution-100 text-caution-600',
    positive: 'bg-positive-100 text-positive-600',
  } as const;

  return (
    <div
      role="alert"
      className={cx('rounded-md px-3 py-2 text-sm', tones[tone])}
    >
      {children}
    </div>
  );
}

// --- Card -----------------------------------------------------------------

export function Card({
  title,
  actions,
  children,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg bg-white ring-1 ring-ink-200">
      {title || actions ? (
        <header className="flex items-center justify-between gap-4 border-b border-ink-100 px-5 py-3">
          {title ? (
            <h2 className="text-sm font-semibold text-ink-800">{title}</h2>
          ) : (
            <span />
          )}
          {actions}
        </header>
      ) : null}
      <div className="p-5">{children}</div>
    </section>
  );
}

export { cx };
