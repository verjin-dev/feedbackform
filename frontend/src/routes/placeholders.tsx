import { Card } from '@/components/ui';

/** P6 ships the shell, not the screens. Each of these is replaced by real work
 *  in P7 (admin) and P8 (student and faculty). They exist so every route in the
 *  navigation resolves and the role guards can be exercised end to end. */
function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <Card title={title}>
      <p className="text-sm text-ink-500">
        Not built yet — scheduled for {phase}.
      </p>
    </Card>
  );
}

export const AdminOverview = () => <Placeholder title="Overview" phase="P7" />;
export const AdminAcademicYears = () => <Placeholder title="Academic years" phase="P7" />;
export const AdminClasses = () => <Placeholder title="Classes" phase="P7" />;
export const AdminSubjects = () => <Placeholder title="Subjects" phase="P7" />;
export const AdminCriteria = () => <Placeholder title="Criteria" phase="P7" />;
export const AdminQuestionnaire = () => <Placeholder title="Questionnaire" phase="P7" />;
export const AdminAssignments = () => <Placeholder title="Assignments" phase="P7" />;
export const AdminFaculty = () => <Placeholder title="Faculty" phase="P7" />;
export const AdminStudents = () => <Placeholder title="Students" phase="P7" />;
export const AdminUsers = () => <Placeholder title="Administrators" phase="P7" />;
export const AdminReports = () => <Placeholder title="Reports" phase="P7" />;

export const StudentEvaluate = () => <Placeholder title="Give feedback" phase="P8" />;
export const FacultyResults = () => <Placeholder title="My results" phase="P8" />;

export const NotFound = () => (
  <Card title="Page not found">
    <p className="text-sm text-ink-500">
      That page does not exist, or you do not have access to it.
    </p>
  </Card>
);
