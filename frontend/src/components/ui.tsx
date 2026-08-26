import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { forwardRef, useId } from 'react';

function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}

/**
 * Every control here is at least 40px tall, and 44px at `lg`.
 *
 * Most of the people using this are students filling in the form on a phone
 * between classes. The legacy app used 28px rows built for a mouse.
 */
const CONTROL = 'min-h-10 rounded-md';

// --- Spinner --------------------------------------------------------------

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cx('animate-spin', className ?? 'size-4')}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        opacity="0.25"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

// --- Button ---------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle';
type ButtonSize = 'sm' | 'md' | 'lg';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-brand text-on-brand shadow-e1 hover:bg-brand-hover active:translate-y-px',
  secondary:
    'bg-raised text-body ring-1 ring-line-strong shadow-e1 hover:bg-sunken active:translate-y-px',
  danger: 'bg-bad text-on-brand shadow-e1 hover:brightness-110 active:translate-y-px',
  ghost: 'text-muted hover:bg-sunken hover:text-body',
  subtle: 'bg-brand-soft text-brand-text hover:brightness-95',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'min-h-8 px-2.5 text-xs gap-1.5',
  md: 'min-h-10 px-4 text-sm gap-2',
  lg: 'min-h-11 px-5 text-sm gap-2',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    disabled,
    className,
    children,
    ...rest
  },
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
        'inline-flex items-center justify-center rounded-md font-medium',
        'transition-[background-color,box-shadow,transform,filter] duration-150',
        'disabled:pointer-events-none disabled:opacity-55 disabled:shadow-none',
        BUTTON_SIZES[size],
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {/* Rendered beside the label rather than replacing it: swapping the text
          out changes the button's width mid-click and moves the thing under
          the pointer. */}
      {loading ? <Spinner className="size-4 shrink-0" /> : null}
      {children}
    </button>
  );
});

// --- Labelled control shell -----------------------------------------------

function useControlIds(id: string | undefined) {
  const generated = useId();
  const controlId = id ?? generated;
  return {
    controlId,
    errorId: `${controlId}-error`,
    hintId: `${controlId}-hint`,
  };
}

function ControlFrame({
  label,
  controlId,
  hint,
  hintId,
  error,
  errorId,
  children,
}: {
  label: string;
  controlId: string;
  hint?: string | undefined;
  hintId: string;
  error?: string | undefined;
  errorId: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={controlId} className="text-sm font-medium text-body">
        {label}
      </label>
      {children}
      {hint ? (
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="flex items-start gap-1 text-xs text-bad">
          <span aria-hidden="true">&#9888;</span>
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

/** The ring is the whole visual treatment: no border underneath it, so the
 *  control does not grow by a pixel when it gains focus or an error. */
const INPUT_BASE = cx(
  CONTROL,
  'w-full bg-surface px-3 py-2 text-sm text-body',
  'ring-1 ring-line-strong transition-[box-shadow,background-color] duration-150',
  'hover:ring-ink-300 focus:outline-none focus:ring-2 focus:ring-brand',
  'disabled:cursor-not-allowed disabled:bg-sunken disabled:text-faint',
);

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
  const { controlId, errorId, hintId } = useControlIds(id);

  return (
    <ControlFrame
      label={label}
      controlId={controlId}
      hint={hint}
      hintId={hintId}
      error={error}
      errorId={errorId}
    >
      <input
        ref={ref}
        id={controlId}
        aria-invalid={error ? true : undefined}
        // Wires the message to the input so a screen reader announces it,
        // rather than leaving it as red text floating nearby.
        aria-describedby={cx(error && errorId, hint && hintId) || undefined}
        className={cx(INPUT_BASE, error && 'ring-bad focus:ring-bad', className)}
        {...rest}
      />
    </ControlFrame>
  );
});

// --- Select ---------------------------------------------------------------

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string | undefined;
  hint?: string | undefined;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, error, hint, id, className, children, ...rest },
  ref,
) {
  const { controlId, errorId, hintId } = useControlIds(id);

  return (
    <ControlFrame
      label={label}
      controlId={controlId}
      hint={hint}
      hintId={hintId}
      error={error}
      errorId={errorId}
    >
      <select
        ref={ref}
        id={controlId}
        aria-invalid={error ? true : undefined}
        aria-describedby={cx(error && errorId, hint && hintId) || undefined}
        className={cx(INPUT_BASE, 'pr-8', error && 'ring-bad focus:ring-bad', className)}
        {...rest}
      >
        {children}
      </select>
    </ControlFrame>
  );
});

// --- Textarea -------------------------------------------------------------

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string | undefined;
  hint?: string | undefined;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ label, error, hint, id, className, ...rest }, ref) {
    const { controlId, errorId, hintId } = useControlIds(id);

    return (
      <ControlFrame
        label={label}
        controlId={controlId}
        hint={hint}
        hintId={hintId}
        error={error}
        errorId={errorId}
      >
        <textarea
          ref={ref}
          id={controlId}
          aria-invalid={error ? true : undefined}
          aria-describedby={cx(error && errorId, hint && hintId) || undefined}
          className={cx(
            INPUT_BASE,
            'min-h-20 resize-y leading-relaxed',
            error && 'ring-bad focus:ring-bad',
            className,
          )}
          {...rest}
        />
      </ControlFrame>
    );
  },
);

// --- Alert ----------------------------------------------------------------

type Tone = 'critical' | 'caution' | 'positive' | 'info';

const ALERT_TONES: Record<Tone, string> = {
  critical: 'bg-bad-soft text-bad ring-bad/25',
  caution: 'bg-warn-soft text-warn ring-warn/25',
  positive: 'bg-good-soft text-good ring-good/25',
  info: 'bg-brand-soft text-brand-text ring-brand/20',
};

const ALERT_GLYPHS: Record<Tone, string> = {
  critical: '⚠',
  caution: '⚠',
  positive: '✓',
  info: 'i',
};

export function Alert({
  tone = 'critical',
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cx(
        'flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-sm ring-1',
        ALERT_TONES[tone],
        className,
      )}
    >
      {/* Decorative: the tone is already carried by the words, which is what
          somebody who cannot separate these colours is relying on.
          No tinted disc behind it -- a glyph on a 15% tint of its own colour
          is about 3.9:1 against that tint, which looks muddy at 11px. On the
          alert's own background it is 4.6:1. */}
      <span aria-hidden="true" className="mt-0.5 shrink-0 text-sm font-bold">
        {ALERT_GLYPHS[tone]}
      </span>
      <div className="min-w-0 flex-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        <div className={cx(title && 'mt-0.5 opacity-90')}>{children}</div>
      </div>
    </div>
  );
}

// --- Card -----------------------------------------------------------------

export function Card({
  title,
  description,
  actions,
  footer,
  children,
  padded = true,
  className,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  /** Off for a card whose body is a full-bleed table. */
  padded?: boolean;
  className?: string;
}) {
  return (
    <section
      className={cx(
        'overflow-hidden rounded-xl bg-raised shadow-e1 ring-1 ring-line',
        className,
      )}
    >
      {title || actions ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-sm font-semibold text-heading">{title}</h2>
            ) : null}
            {description ? (
              <p className="mt-0.5 text-xs text-muted">{description}</p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
          ) : null}
        </header>
      ) : null}

      <div className={padded ? 'p-5' : undefined}>{children}</div>

      {footer ? (
        <footer className="border-t border-line bg-sunken/60 px-5 py-3">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}

// --- Section heading ------------------------------------------------------

export function PageHeading({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-heading">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-prose text-sm text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

// --- Skeleton -------------------------------------------------------------

/**
 * A placeholder shaped like the thing that is coming.
 *
 * Preferred over a centred spinner for lists and tables: the layout does not
 * jump when the data lands, which on a slow connection is the difference
 * between a page settling and a page flickering.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cx(
        'relative overflow-hidden rounded-md bg-line',
        'after:absolute after:inset-0 after:-translate-x-full',
        'after:bg-gradient-to-r after:from-transparent after:via-surface/60 after:to-transparent',
        'after:animate-[shimmer_1.6s_infinite]',
        className ?? 'h-4 w-full',
      )}
    />
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className={cx('h-4', index === 0 ? 'w-2/5' : 'w-full')} />
      ))}
    </div>
  );
}

// --- Empty state ----------------------------------------------------------

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="text-sm font-medium text-body">{title}</p>
      {children ? (
        <p className="max-w-sm text-sm text-muted">{children}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export { cx };
