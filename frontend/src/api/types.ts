// Mirrors the Pydantic schemas in backend/app/schemas.
//
// Hand-written for now. Once the surface stops moving, generating these from
// the OpenAPI document the backend already publishes at /openapi.json removes
// the chance of the two drifting apart.

export type Role = 'admin' | 'faculty' | 'student';
export type TermStatus = 'pending' | 'open' | 'closed';

export interface Account {
  id: number;
  role: Role;
  school_id: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  class_group_id: number | null;
  avatar: string | null;
}

export interface AcademicTerm {
  id: number;
  year: string;
  semester: number;
  status: TermStatus;
  is_current: boolean;
}

export interface ClassGroup {
  id: number;
  curriculum: string;
  level: string;
  section: string;
  label: string;
}

export interface Subject {
  id: number;
  code: string;
  name: string;
  description: string | null;
}

export interface Criterion {
  id: number;
  name: string;
  position: number;
}

export interface Question {
  id: number;
  term_id: number;
  criterion_id: number;
  text: string;
  position: number;

  // null asks it of the whole college; a curriculum asks it only of that
  // department.
  curriculum: string | null;
}

export interface TeachingAssignment {
  id: number;
  term_id: number;
  faculty_id: number;
  faculty_name: string;
  class_group_id: number;
  class_label: string;
  subject_id: number;
  subject_code: string;
  subject_name: string;
}

export interface PendingAssignment {
  assignment_id: number;
  faculty_id: number;
  faculty_name: string;
  subject_id: number;
  subject_code: string;
  subject_name: string;
}

export interface QuestionnaireBlock {
  criterion_id: number;
  name: string;
  questions: { id: number; text: string }[];
}

export type CommentPrompt = 'helped' | 'change';

export interface Questionnaire {
  term: Pick<AcademicTerm, 'id' | 'year' | 'semester' | 'status'>;
  criteria: QuestionnaireBlock[];
  comment_prompts: { prompt: CommentPrompt; text: string }[];
}

export interface Comment {
  id: number;
  prompt: CommentPrompt;
  text: string;
  withheld?: boolean;
  withheld_reason?: string | null;
}

/** Why written feedback is or is not being shown. An empty list alone cannot
 *  say whether nobody wrote anything or the rules are holding it back. */
export type CommentState = 'released' | 'window_open' | 'too_few_responses';

/** The middle half of what comparable subjects scored.
 *
 *  Carries no names, no ids, no position and no percentile — a percentile is a
 *  ranking with one row visible, and a ranking gets used for decisions this
 *  data cannot support. */
export interface CohortBand {
  size: number;
  p25: number;
  median: number;
  p75: number;
  basis: string;
}

/** How much weight the figures on a row can carry.
 *  - insufficient: too few responses for a mean to be published at all
 *  - low:          a real mean, but from a small share of the class
 *  - adequate:     enough people, and enough of the class */
export type Reliability = 'insufficient' | 'low' | 'adequate';

/** `mean` is null in two cases: nothing was answered, or too few people
 *  answered for a mean to be honest. `responses` and `reliability` separate
 *  them — the UI must not render both as a blank cell. */
export interface QuestionReport {
  question_id: number;
  text: string;

  // null where the whole college answered it; a curriculum where only that
  // department did. Shown, because a department block and the shared core are
  // not the same population.
  curriculum: string | null;
  counts: Record<string, number>;
  percentages: Record<string, number>;
  responses: number;
  mean: number | null;
  mean_range: [number, number] | null;
  reliability: Reliability;
}

export interface CriterionReport {
  criterion_id: number;
  name: string;
  questions: QuestionReport[];
  mean: number | null;
}

export interface AssignmentReport {
  assignment_id: number;
  subject_id: number;
  subject_code: string;
  subject_name: string;
  class_group_id: number;
  class_label: string;
  eligible_students: number;
  responses: number;
  response_rate: number | null;
  reliability: Reliability;
  criteria: CriterionReport[];
  mean: number | null;
  cohort: CohortBand | null;
  comments: Comment[];
  comment_state: CommentState;
  comment_total: number;
}

export interface FacultyReport {
  faculty_id: number;
  faculty_name: string;
  term: Pick<AcademicTerm, 'id' | 'year' | 'semester' | 'status'>;
  assignments: AssignmentReport[];
  mean: number | null;
}
