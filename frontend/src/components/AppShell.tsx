import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import type { Role } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Button, cx } from '@/components/ui';

interface NavItem {
  to: string;
  label: string;
}

/** Replaces the three sidebar.php files. Navigation is derived from the role
 *  on the account, not from a folder name held in the session. */
const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  admin: [
    { to: '/admin', label: 'Overview' },
    { to: '/admin/academic-years', label: 'Academic years' },
    { to: '/admin/classes', label: 'Classes' },
    { to: '/admin/subjects', label: 'Subjects' },
    { to: '/admin/criteria', label: 'Criteria' },
    { to: '/admin/questionnaire', label: 'Questionnaire' },
    { to: '/admin/assignments', label: 'Assignments' },
    { to: '/admin/faculty', label: 'Faculty' },
    { to: '/admin/students', label: 'Students' },
    { to: '/admin/users', label: 'Administrators' },
    { to: '/admin/import', label: 'Bulk import' },
    { to: '/admin/participation', label: 'Participation' },
    { to: '/admin/reports', label: 'Reports' },
  ],
  faculty: [{ to: '/results', label: 'My results' }],
  student: [{ to: '/evaluate', label: 'Give feedback' }],
};

export function AppShell() {
  const { account, signOut } = useAuth();
  const navigate = useNavigate();

  if (account === null) return null;

  const items = NAV_BY_ROLE[account.role];

  async function handleSignOut() {
    await signOut();
    navigate('/login', { replace: true });
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-ink-200 bg-white px-5 py-3">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold text-ink-800">
            Faculty Evaluation
          </span>
          <span className="text-xs text-ink-400 capitalize">{account.role}</span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-ink-600">{account.full_name}</span>
          <Button variant="ghost" onClick={handleSignOut}>
            Sign out
          </Button>
        </div>
      </header>

      <div className="flex flex-1 flex-col md:flex-row">
        {/* A single-item sidebar is chrome without information, so students and
            faculty get the content full width instead. */}
        {items.length > 1 ? (
          <nav
            aria-label="Sections"
            className="shrink-0 border-b border-ink-200 bg-white p-3 md:w-56 md:border-b-0 md:border-r"
          >
            <ul className="flex flex-wrap gap-1 md:flex-col">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/admin'}
                    className={({ isActive }) =>
                      cx(
                        'block rounded-md px-3 py-2 text-sm transition-colors',
                        isActive
                          ? 'bg-accent-50 font-medium text-accent-700'
                          : 'text-ink-600 hover:bg-ink-100',
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}

        <main className="flex-1 p-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
