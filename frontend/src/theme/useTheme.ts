import { useCallback, useEffect, useState } from 'react';

export const THEMES = ['system', 'light', 'dark'] as const;
export type Theme = (typeof THEMES)[number];

const STORAGE_KEY = 'evaluation.theme';

function isTheme(value: unknown): value is Theme {
  return value === 'system' || value === 'light' || value === 'dark';
}

export function readStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isTheme(stored) ? stored : 'system';
  } catch {
    // Private windows and locked-down browsers throw on access rather than
    // returning null. Following the operating system is a working default.
    return 'system';
  }
}

/**
 * Light, dark, or whatever the machine says.
 *
 * "System" is the default and is a real third state, not a synonym for light:
 * it sets no attribute at all, leaving the `prefers-color-scheme` rules in
 * global.css to decide. Collapsing it into an explicit value would freeze
 * whatever the machine happened to be set to the first time somebody opened
 * the page, and stop tracking it afterwards.
 *
 * The choice lives in this browser rather than on the account. Unlike the
 * language, it is a property of the screen someone is looking at -- the same
 * person wants dark on a phone at night and light on a projector in a lecture
 * hall, and syncing it across their devices would get one of those wrong.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', theme);
    }

    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Not worth surfacing: the theme still applies for this visit.
    }
  }, [theme]);

  // Another tab changing the setting should not leave this one disagreeing
  // with what is now stored.
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY && isTheme(event.newValue)) {
        setThemeState(event.newValue);
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);

  return { theme, setTheme };
}

/**
 * Applied before React mounts, from index.html.
 *
 * Without it the page paints light, then corrects itself once the bundle runs
 * — a white flash on every load for everybody using dark mode.
 */
export const THEME_BOOTSTRAP = `
try {
  var t = localStorage.getItem(${JSON.stringify(STORAGE_KEY)});
  if (t === 'light' || t === 'dark') {
    document.documentElement.setAttribute('data-theme', t);
  }
} catch (e) {}
`;
