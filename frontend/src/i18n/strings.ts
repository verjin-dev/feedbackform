/**
 * The student-facing interface, in English and Tamil.
 *
 * Scope is deliberate. Students are asked to say something candid about their
 * teacher, and asking that in a language somebody is merely competent in gets
 * a shorter, blander answer than asking it in the language they think in. The
 * admin screens, the faculty reports and the accreditation exports stay in
 * English, which is the language the institution already conducts that work in
 * — and translating a report would mean two people looking at the same figures
 * saw different text.
 *
 * Question wording is not here. It belongs to the college rather than to the
 * application, is entered per question, and falls back to English until
 * somebody supplies the Tamil.
 *
 * A dictionary rather than an i18n library: two languages, no plural rules
 * beyond one counter, and no runtime locale negotiation. react-i18next would
 * add about 40 KB to a bundle students load over college wifi to do one thing.
 * If a third language arrives with real plural or date requirements, that
 * trade changes and this should be revisited.
 *
 * The Tamil is written to be read by a first-year student rather than to be
 * formally correct, and uses the polite plural throughout. It should be
 * reviewed by a Tamil speaker at the college before it goes in front of
 * anybody.
 */

export const LANGUAGES = ['en', 'ta'] as const;
export type Language = (typeof LANGUAGES)[number];

export const LANGUAGE_NAMES: Record<Language, string> = {
  en: 'English',
  // Named in the language it names: somebody looking for Tamil is looking for
  // this word, not for "Tamil".
  ta: 'தமிழ்',
};

const en = {
  // --- Signing in ---------------------------------------------------------
  'app.title': 'Faculty Evaluation',
  'auth.email': 'Email',
  'auth.password': 'Password',
  'auth.signIn': 'Sign in',
  'auth.signingIn': 'Signing in',
  'auth.checkingSession': 'Checking your session',
  'auth.failed': 'Something went wrong. Please try again.',
  'auth.language': 'Language',

  // --- The evaluation form ------------------------------------------------
  'evaluate.heading': 'Subjects to review',
  'evaluate.notAvailable': 'Not available yet',
  'evaluate.notStarted': 'Not started yet',
  'evaluate.closed': 'Feedback is closed',
  'evaluate.allDone': 'All done',
  'evaluate.ready': 'Ready to submit.',
  'evaluate.remaining': '{count} left.',
  'evaluate.submit': 'Submit feedback',
  'evaluate.saveFailed': 'Your feedback could not be saved. Please try again.',
  'evaluate.optional': 'Leave blank if you would rather not.',
  'evaluate.anonymous':
    'Your answers are not linked to your name. Your teacher sees the totals, never who said what.',

  'rating.1': 'Poor',
  'rating.2': 'Satisfactory',
  'rating.3': 'Good',
  'rating.4': 'Very good',
  'rating.5': 'Excellent',

  // --- The mid-term pulse -------------------------------------------------
  'pulse.optional': 'Optional.',
  'pulse.sendFailed': 'That could not be sent.',
  'pace.1': 'Much too slow',
  'pace.2': 'A little slow',
  'pace.3': 'About right',
  'pace.4': 'A little fast',
  'pace.5': 'Much too fast',
} as const;

export type StringKey = keyof typeof en;

/** Every key the interface uses, so a test can hold the translations to the
 *  same list rather than to a hand-maintained copy of it. */
export const STRING_KEYS = Object.keys(en) as StringKey[];

/**
 * Missing keys fall back to English rather than rendering the key.
 *
 * The same rule as the questionnaire itself: a half-translated screen is
 * usable, one showing `evaluate.ready` where a sentence belongs is not — and a
 * key added in a hurry must not be able to break the form for Tamil readers.
 */
const ta: Partial<Record<StringKey, string>> = {
  'app.title': 'ஆசிரியர் மதிப்பீடு',
  'auth.email': 'மின்னஞ்சல்',
  'auth.password': 'கடவுச்சொல்',
  'auth.signIn': 'உள்நுழையவும்',
  'auth.signingIn': 'உள்நுழைகிறது',
  'auth.checkingSession': 'உங்கள் அமர்வு சரிபார்க்கப்படுகிறது',
  'auth.failed': 'ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்.',
  'auth.language': 'மொழி',

  'evaluate.heading': 'மதிப்பிட வேண்டிய பாடங்கள்',
  'evaluate.notAvailable': 'இன்னும் கிடைக்கவில்லை',
  'evaluate.notStarted': 'இன்னும் தொடங்கவில்லை',
  'evaluate.closed': 'கருத்து அளிக்கும் காலம் முடிந்தது',
  'evaluate.allDone': 'அனைத்தும் முடிந்தது',
  'evaluate.ready': 'சமர்ப்பிக்கத் தயார்.',
  'evaluate.remaining': 'இன்னும் {count} மீதம்.',
  'evaluate.submit': 'கருத்தைச் சமர்ப்பிக்கவும்',
  'evaluate.saveFailed':
    'உங்கள் கருத்தைச் சேமிக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.',
  'evaluate.optional': 'விரும்பவில்லை என்றால் காலியாக விடலாம்.',
  'evaluate.anonymous':
    'உங்கள் பதில்கள் உங்கள் பெயருடன் இணைக்கப்படவில்லை. ஆசிரியருக்கு மொத்த முடிவுகள் மட்டுமே தெரியும், யார் என்ன சொன்னார்கள் என்பது தெரியாது.',

  'rating.1': 'மோசம்',
  'rating.2': 'திருப்திகரம்',
  'rating.3': 'நன்று',
  'rating.4': 'மிக நன்று',
  'rating.5': 'சிறப்பு',

  'pulse.optional': 'விருப்பத்திற்குரியது.',
  'pulse.sendFailed': 'அதை அனுப்ப முடியவில்லை.',
  'pace.1': 'மிகவும் மெதுவாக',
  'pace.2': 'சற்று மெதுவாக',
  'pace.3': 'சரியாக உள்ளது',
  'pace.4': 'சற்று வேகமாக',
  'pace.5': 'மிகவும் வேகமாக',
};

const DICTIONARIES: Record<Language, Partial<Record<StringKey, string>>> = { en, ta };

export function isLanguage(value: string | null | undefined): value is Language {
  return value === 'en' || value === 'ta';
}

/** Anything unrecognised reads as English rather than failing: the worst case
 *  is a student seeing English and switching again. */
export function normaliseLanguage(value: string | null | undefined): Language {
  const code = (value ?? '').trim().toLowerCase().split('-')[0];
  return isLanguage(code) ? code : 'en';
}

export function translate(
  language: Language,
  key: StringKey,
  values?: Record<string, string | number>,
): string {
  const text = DICTIONARIES[language]?.[key] ?? en[key];
  if (values === undefined) return text;
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}
