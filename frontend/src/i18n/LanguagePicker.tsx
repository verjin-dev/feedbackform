import { LANGUAGES, LANGUAGE_NAMES, isLanguage } from '@/i18n/strings';
import { useLanguage } from '@/i18n/useLanguage';

/**
 * A select rather than a flag, and each option written in its own language.
 *
 * Flags name countries, not languages, and Tamil is spoken across several. The
 * point of the control is to be findable by somebody who cannot read the rest
 * of the page, which is why the options are not translated into the current
 * language.
 */
export function LanguagePicker({ className }: { className?: string }) {
  const { language, setLanguage, isSaving } = useLanguage();

  return (
    <label className={className}>
      <span className="sr-only">Language / மொழி</span>
      <select
        value={language}
        disabled={isSaving}
        onChange={(event) => {
          const next = event.target.value;
          if (isLanguage(next)) void setLanguage(next);
        }}
        className="rounded-md bg-white px-2 py-1.5 text-sm text-ink-800 ring-1 ring-ink-200 disabled:opacity-60"
      >
        {LANGUAGES.map((code) => (
          <option key={code} value={code} lang={code}>
            {LANGUAGE_NAMES[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
