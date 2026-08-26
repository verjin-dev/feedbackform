import { describe, expect, it } from 'vitest';

import {
  LANGUAGE_NAMES,
  LANGUAGES,
  STRING_KEYS,
  isLanguage,
  normaliseLanguage,
  translate,
} from '@/i18n/strings';

describe('normaliseLanguage', () => {
  it('reads anything unrecognised as English', () => {
    // The worst case is a student seeing English and switching again, which is
    // better than a blank screen in the middle of a form.
    expect(normaliseLanguage('fr')).toBe('en');
    expect(normaliseLanguage('')).toBe('en');
    expect(normaliseLanguage(null)).toBe('en');
    expect(normaliseLanguage(undefined)).toBe('en');
  });

  it('maps a regional variant to its language', () => {
    expect(normaliseLanguage('ta-IN')).toBe('ta');
    expect(normaliseLanguage('EN-GB')).toBe('en');
  });

  it('narrows the type for a supported code', () => {
    expect(isLanguage('ta')).toBe(true);
    expect(isLanguage('de')).toBe(false);
  });
});

describe('translate', () => {
  it('returns the English wording for an English reader', () => {
    expect(translate('en', 'evaluate.submit')).toBe('Submit feedback');
  });

  it('returns the Tamil wording for a Tamil reader', () => {
    const tamil = translate('ta', 'evaluate.submit');
    expect(tamil).not.toBe(translate('en', 'evaluate.submit'));
    // Tamil block: U+0B80-U+0BFF.
    expect(tamil).toMatch(/[஀-௿]/);
  });

  it('interpolates a count into either language', () => {
    expect(translate('en', 'evaluate.remaining', { count: 3 })).toContain('3');
    expect(translate('ta', 'evaluate.remaining', { count: 3 })).toContain('3');
  });

  it('leaves an unknown placeholder alone rather than blanking it', () => {
    expect(translate('en', 'evaluate.remaining', { other: 1 })).toContain('{count}');
  });

  it('names each language in the language it names', () => {
    // Somebody looking for Tamil is looking for this word, not for "Tamil".
    expect(LANGUAGE_NAMES.ta).toBe('தமிழ்');
    expect(LANGUAGE_NAMES.en).toBe('English');
  });
});

describe('the Tamil dictionary', () => {
  it('translates every key the interface uses', () => {
    // Not a completeness rule for its own sake: a key added in a hurry and
    // left untranslated is a sentence a Tamil reader meets in English in the
    // middle of a Tamil form. Held to STRING_KEYS rather than to a list copied
    // here, so a key added later fails this without anyone remembering to.
    const untranslated = STRING_KEYS.filter(
      (key) => translate('ta', key) === translate('en', key),
    );
    expect(untranslated).toEqual([]);
  });

  it('falls back to English rather than rendering a key', () => {
    // Same rule as the questionnaire: a half-translated screen is usable, one
    // showing `evaluate.ready` where a sentence belongs is not.
    for (const language of LANGUAGES) {
      expect(translate(language, 'evaluate.saveFailed')).not.toContain('evaluate.');
    }
  });
});
