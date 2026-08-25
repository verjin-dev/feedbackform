import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireRole } from '@/auth/RequireRole';
import { useAuth } from '@/auth/useAuth';
import { landingFor } from '@/auth/landing';
import { AppShell } from '@/components/AppShell';
import { LoginPage } from '@/routes/LoginPage';
import {
  AdminAcademicYears,
  AdminAssignments,
  AdminClasses,
  AdminCriteria,
  AdminFaculty,
  AdminOverview,
  AdminQuestionnaire,
  AdminReports,
  AdminStudents,
  AdminSubjects,
  AdminUsers,
  FacultyResults,
  NotFound,
  StudentEvaluate,
} from '@/routes/placeholders';

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
      <Route path="/" element={<RootRedirect />} />

      <Route element={<RequireRole allow={ADMIN} />}>
        <Route element={<AppShell />}>
          <Route path="/admin" element={<AdminOverview />} />
          <Route path="/admin/academic-years" element={<AdminAcademicYears />} />
          <Route path="/admin/classes" element={<AdminClasses />} />
          <Route path="/admin/subjects" element={<AdminSubjects />} />
          <Route path="/admin/criteria" element={<AdminCriteria />} />
          <Route path="/admin/questionnaire" element={<AdminQuestionnaire />} />
          <Route path="/admin/assignments" element={<AdminAssignments />} />
          <Route path="/admin/faculty" element={<AdminFaculty />} />
          <Route path="/admin/students" element={<AdminStudents />} />
          <Route path="/admin/users" element={<AdminUsers />} />
          <Route path="/admin/reports" element={<AdminReports />} />
        </Route>
      </Route>

      <Route element={<RequireRole allow={FACULTY} />}>
        <Route element={<AppShell />}>
          <Route path="/results" element={<FacultyResults />} />
        </Route>
      </Route>

      <Route element={<RequireRole allow={STUDENT} />}>
        <Route element={<AppShell />}>
          <Route path="/evaluate" element={<StudentEvaluate />} />
        </Route>
      </Route>

      {/* Behind a guard on purpose: an unknown path should ask an anonymous
          visitor to sign in, not reveal that the route does not exist. */}
      <Route element={<RequireRole allow={[...ADMIN, ...FACULTY, ...STUDENT]} />}>
        <Route element={<AppShell />}>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
