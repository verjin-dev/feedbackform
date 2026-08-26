import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireRole } from '@/auth/RequireRole';
import { useAuth } from '@/auth/useAuth';
import { landingFor } from '@/auth/landing';
import { AppShell } from '@/components/AppShell';
import { LoginPage } from '@/routes/LoginPage';
import {
  ForgotPasswordPage,
  SetPasswordPage,
} from '@/routes/PasswordResetPages';
import {
  AdminUsersPage,
  FacultyPage,
  StudentsPage,
} from '@/routes/admin/AccountsPage';
import { AssignmentsPage } from '@/routes/admin/AssignmentsPage';
import { ExportsPage } from '@/routes/admin/ExportsPage';
import { ImportPage } from '@/routes/admin/ImportPage';
import { OverviewPage } from '@/routes/admin/OverviewPage';
import { AuditPage } from '@/routes/admin/AuditPage';
import { ModerationPage } from '@/routes/admin/ModerationPage';
import { ParticipationPage } from '@/routes/admin/ParticipationPage';
import { QuestionnairePage } from '@/routes/admin/QuestionnairePage';
import { ReportsPage } from '@/routes/admin/ReportsPage';
import {
  AcademicYearsPage,
  ClassesPage,
  CriteriaPage,
  SubjectsPage,
} from '@/routes/admin/SimpleResources';
import { PulsePage } from '@/routes/faculty/PulsePage';
import { ResultsPage } from '@/routes/faculty/ResultsPage';
import { NotFoundPage } from '@/routes/NotFoundPage';
import { EvaluatePage } from '@/routes/student/EvaluatePage';

const ADMIN = ['admin'] as const;
const FACULTY = ['faculty'] as const;
const STUDENT = ['student'] as const;

/** Sends "/" to wherever the signed-in role belongs. */
function RootRedirect() {
  const { account, isResolving } = useAuth();
  if (isResolving) return null;
  return <Navigate to={account ? landingFor(account.role) : '/login'} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<SetPasswordPage mode="reset" />} />
      <Route path="/set-password" element={<SetPasswordPage mode="invite" />} />
      <Route path="/" element={<RootRedirect />} />

      <Route element={<RequireRole allow={ADMIN} />}>
        <Route element={<AppShell />}>
          <Route path="/admin" element={<OverviewPage />} />
          <Route path="/admin/academic-years" element={<AcademicYearsPage />} />
          <Route path="/admin/classes" element={<ClassesPage />} />
          <Route path="/admin/subjects" element={<SubjectsPage />} />
          <Route path="/admin/criteria" element={<CriteriaPage />} />
          <Route path="/admin/questionnaire" element={<QuestionnairePage />} />
          <Route path="/admin/assignments" element={<AssignmentsPage />} />
          <Route path="/admin/faculty" element={<FacultyPage />} />
          <Route path="/admin/students" element={<StudentsPage />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="/admin/import" element={<ImportPage />} />
          <Route path="/admin/participation" element={<ParticipationPage />} />
          <Route path="/admin/comments" element={<ModerationPage />} />
          <Route path="/admin/reports" element={<ReportsPage />} />
          <Route path="/admin/exports" element={<ExportsPage />} />
          <Route path="/admin/audit" element={<AuditPage />} />
        </Route>
      </Route>

      <Route element={<RequireRole allow={FACULTY} />}>
        <Route element={<AppShell />}>
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/pulse" element={<PulsePage />} />
        </Route>
      </Route>

      <Route element={<RequireRole allow={STUDENT} />}>
        <Route element={<AppShell />}>
          <Route path="/evaluate" element={<EvaluatePage />} />
        </Route>
      </Route>

      {/* Behind a guard on purpose: an unknown path should ask an anonymous
          visitor to sign in, not reveal that the route does not exist. */}
      <Route element={<RequireRole allow={[...ADMIN, ...FACULTY, ...STUDENT]} />}>
        <Route element={<AppShell />}>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
