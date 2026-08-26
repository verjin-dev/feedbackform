import { Icons } from '@/components/icons';
import { cx } from '@/components/ui';
import { THEMES, useTheme, type Theme } from '@/theme/useTheme';

const OPTIONS: Record<Theme, { label: string; Icon: typeof Icons.sun }> = {
  system: { label: 'Match my device', Icon: Icons.monitor },
  light: { label: 'Light', Icon: Icons.sun },
  dark: { label: 'Dark', Icon: Icons.moon },
};

/**
 * Three states, shown as three buttons rather than a two-way switch.
 *
 * "System" is a real option, not the absence of one: a toggle that only offers
 * light and dark forces a permanent choice the first time somebody touches it,
 * and afterwards stops following the machine at sunset. Making it visible and
 * selectable is the difference between a preference and a trap.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cx(
        'inline-flex items-center gap-0.5 rounded-lg bg-sunken p-0.5 ring-1 ring-line',
        className,
      )}
    >
      {THEMES.map((option) => {
        const { label, Icon } = OPTIONS[option];
        const selected = theme === option;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={selected}
            // The icon alone is not a name. Without this the control reads as
            // three unlabelled buttons.
            aria-label={label}
            title={label}
            onClick={() => setTheme(option)}
            className={cx(
              'flex size-9 items-center justify-center rounded-md transition-colors',
              selected
                ? 'bg-raised text-brand-text shadow-e1'
                : 'text-faint hover:text-body',
            )}
          >
            <Icon className="size-4" />
          </button>
        );
      })}
    </div>
  );
}
