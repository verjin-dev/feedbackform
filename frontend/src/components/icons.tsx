import type { SVGProps } from 'react';

/**
 * Hand-drawn 24px outline icons.
 *
 * A library would be roughly 300 KB for the twenty shapes actually used here,
 * on a bundle students load over college wifi. These are decorative in every
 * place they appear — each one sits beside its own label — so they carry
 * `aria-hidden` by default and never become the only cue for anything.
 */
type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="size-[1.125rem] shrink-0"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const Icons = {
  overview: (p: IconProps) => (
    <Icon {...p}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Icon>
  ),
  calendar: (p: IconProps) => (
    <Icon {...p}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </Icon>
  ),
  classes: (p: IconProps) => (
    <Icon {...p}>
      <path d="M12 4 3 8l9 4 9-4-9-4Z" />
      <path d="M6 10v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-5" />
    </Icon>
  ),
  book: (p: IconProps) => (
    <Icon {...p}>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5Z" />
      <path d="M19 18v3H6.5A2.5 2.5 0 0 1 4 18.5" />
    </Icon>
  ),
  criteria: (p: IconProps) => (
    <Icon {...p}>
      <path d="M9 5h11M9 12h11M9 19h11" />
      <path d="m3 5 1.5 1.5L7 4M3 12l1.5 1.5L7 11M3 19l1.5 1.5L7 18" />
    </Icon>
  ),
  questionnaire: (p: IconProps) => (
    <Icon {...p}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M9 8h6M9 12h6M9 16h3" />
    </Icon>
  ),
  assignments: (p: IconProps) => (
    <Icon {...p}>
      <path d="M4 7h6v10H4zM14 7h6v10h-6z" />
      <path d="M10 12h4" />
    </Icon>
  ),
  faculty: (p: IconProps) => (
    <Icon {...p}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
    </Icon>
  ),
  students: (p: IconProps) => (
    <Icon {...p}>
      <circle cx="9" cy="8" r="3" />
      <path d="M2.5 19a6.5 6.5 0 0 1 13 0" />
      <path d="M16.5 5.5a3 3 0 0 1 0 5.9M18 19a6.4 6.4 0 0 0-2-4.6" />
    </Icon>
  ),
  shield: (p: IconProps) => (
    <Icon {...p}>
      <path d="M12 3l7 3v5.5c0 4.3-2.9 8.1-7 9.5-4.1-1.4-7-5.2-7-9.5V6l7-3Z" />
      <path d="m9 12 2 2 4-4" />
    </Icon>
  ),
  upload: (p: IconProps) => (
    <Icon {...p}>
      <path d="M12 15V4m0 0L8 8m4-4 4 4" />
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </Icon>
  ),
  participation: (p: IconProps) => (
    <Icon {...p}>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </Icon>
  ),
  comment: (p: IconProps) => (
    <Icon {...p}>
      <path d="M20 15a2 2 0 0 1-2 2H8l-4 3.5V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9Z" />
    </Icon>
  ),
  report: (p: IconProps) => (
    <Icon {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5M9 14h6M9 17h4" />
    </Icon>
  ),
  export: (p: IconProps) => (
    <Icon {...p}>
      <path d="M12 4v11m0 0 4-4m-4 4-4-4" />
      <path d="M5 19h14" />
    </Icon>
  ),
  key: (p: IconProps) => (
    <Icon {...p}>
      <circle cx="8" cy="15" r="4" />
      <path d="m11 12 8-8 2 2-2 2 1.5 1.5L18 12l-2-2-2 2" />
    </Icon>
  ),
  history: (p: IconProps) => (
    <Icon {...p}>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" />
      <path d="M3 4v4h4M12 8v4.5l3 1.7" />
    </Icon>
  ),
  star: (p: IconProps) => (
    <Icon {...p}>
      <path d="m12 4 2.5 5.2 5.5.8-4 4 1 5.6-5-2.7-5 2.7 1-5.6-4-4 5.5-.8L12 4Z" />
    </Icon>
  ),
  pulse: (p: IconProps) => (
    <Icon {...p}>
      <path d="M2 12h4l3-7 4 14 3-7h6" />
    </Icon>
  ),
  sun: (p: IconProps) => (
    <Icon {...p}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
    </Icon>
  ),
  moon: (p: IconProps) => (
    <Icon {...p}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
    </Icon>
  ),
  monitor: (p: IconProps) => (
    <Icon {...p}>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M9 20h6M12 16v4" />
    </Icon>
  ),
  menu: (p: IconProps) => (
    <Icon {...p}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Icon>
  ),
  close: (p: IconProps) => (
    <Icon {...p}>
      <path d="m6 6 12 12M18 6 6 18" />
    </Icon>
  ),
  signOut: (p: IconProps) => (
    <Icon {...p}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="M10 16l-4-4 4-4M6 12h9" />
    </Icon>
  ),
};

export type IconName = keyof typeof Icons;
