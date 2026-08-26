import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import type { Role } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Icons, type IconName } from '@/components/icons';
import { Button, cx } from '@/components/ui';
import { LanguagePicker } from '@/i18n/LanguagePicker';
import { ThemeToggle } from '@/theme/ThemeToggle';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

/**
 * Replaces the three sidebar.php files. Navigation is derived from the role on
 * the account, not from a folder name held in the session.
 *
 * The admin list is seventeen entries, which as one flat column is a wall.
 * Grouped by what somebody is trying to do — set the term up, run it, read the
 * results, keep the place in order — it is four short lists, and the headings
 * carry most of the wayfinding.
 */
const NAV_BY_ROLE: Record<Role, NavGroup[]> = {
  admin: [
    {
      label: 'Set up',
      items: [
        { to: '/admin', label: 'Overview', icon: 'overview' },
        { to: '/admin/academic-years', label: 'Academic years', icon: 'calendar' },
        { to: '/admin/classes', label: 'Classes', icon: 'classes' },
        { to: '/admin/subjects', label: 'Subjects', icon: 'book' },
        { to: '/admin/criteria', label: 'Criteria', icon: 'criteria' },
        { to: '/admin/questionnaire', label: 'Questionnaire', icon: 'questionnaire' },
        { to: '/admin/assignments', label: 'Assignments', icon: 'assignments' },
      ],
    },
    {
      label: 'People',
      items: [
        { to: '/admin/faculty', label: 'Faculty', icon: 'faculty' },
        { to: '/admin/students', label: 'Students', icon: 'students' },
        { to: '/admin/users', label: 'Administrators', icon: 'shield' },
        { to: '/admin/import', label: 'Bulk import', icon: 'upload' },
      ],
    },
    {
      label: 'This term',
      items: [
        { to: '/admin/participation', label: 'Participation', icon: 'participation' },
        { to: '/admin/comments', label: 'Written feedback', icon: 'comment' },
        { to: '/admin/reports', label: 'Reports', icon: 'report' },
        { to: '/admin/exports', label: 'Accreditation', icon: 'export' },
      ],
    },
    {
      label: 'Administration',
      items: [
        { to: '/admin/sign-in', label: 'College sign-in', icon: 'key' },
        { to: '/admin/audit', label: 'Change log', icon: 'history' },
      ],
    },
  ],
  faculty: [
    {
      label: 'Teaching',
      items: [
        { to: '/results', label: 'My results', icon: 'star' },
        { to: '/pulse', label: 'Mid-term check', icon: 'pulse' },
      ],
    },
  ],
  student: [
    { label: 'Feedback', items: [{ to: '/evaluate', label: 'Give feedback', icon: 'star' }] },
  ],
};

const ROLE_LABEL: Record<Role, string> = {
  admin: 'Administrator',
  faculty: 'Faculty',
  student: 'Student',
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '';
  return (first + last).toUpperCase();
}

export function AppShell() {
  const { account, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);

  // Navigating is the point of the drawer, so it closes itself afterwards.
  // Without this it stays over the page somebody just asked to see.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;

    closeButton.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setDrawerOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [drawerOpen]);

  if (account === null) return null;

  const groups = NAV_BY_ROLE[account.role];
  const linkCount = groups.reduce((total, group) => total + group.items.length, 0);
  // A single-item sidebar is chrome without information, so students get the
  // content full width instead.
  const showSidebar = linkCount > 1;

  async function handleSignOut() {
    await signOut();
    navigate('/login', { replace: true });
  }

  const navigation = (
    <nav aria-label="Sections" className="flex flex-col gap-6">
      {groups.map((group) => (
        <div key={group.label}>
          <h2 className="px-3 pb-1.5 text-[11px] font-semibold tracking-wider text-faint uppercase">
            {group.label}
          </h2>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = Icons[item.icon];
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/admin'}
                    className={({ isActive }) =>
                      cx(
                        'group relative flex items-center gap-2.5 rounded-lg px-3 py-2',
                        'text-sm transition-colors',
                        isActive
                          ? 'bg-brand-soft font-medium text-brand-text'
                          : 'text-muted hover:bg-sunken hover:text-body',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {/* A bar as well as a fill, so the current page is
                            marked by position and not only by colour. */}
                        <span
                          aria-hidden="true"
                          className={cx(
                            'absolute top-1.5 bottom-1.5 -left-2 w-1 rounded-full transition-colors',
                            isActive ? 'bg-brand' : 'bg-transparent',
                          )}
                        />
                        <Icon
                          className={cx(
                            'size-[1.125rem] shrink-0 transition-colors',
                            isActive ? 'text-brand' : 'text-faint group-hover:text-muted',
                          )}
                        />
                        <span className="truncate">{item.label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md">
        <div className="flex items-center gap-3 px-4 py-2.5 sm:px-5">
          {showSidebar ? (
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-expanded={drawerOpen}
              className="-ml-1 flex size-9 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-body lg:hidden"
            >
              <Icons.menu />
            </button>
          ) : null}

          <div className="flex min-w-0 items-center gap-2.5">
            <span
              aria-hidden="true"
              className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand text-sm font-bold text-on-brand shadow-e1"
            >
              F
            </span>
            <div className="min-w-0 leading-tight">
              <p className="truncate text-sm font-semibold text-heading">
                Faculty Evaluation
              </p>
              <p className="truncate text-[11px] text-faint">
                {ROLE_LABEL[account.role]}
              </p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {/* Offered to students only. Staff reports and the admin screens
                are English throughout, so a picker there would promise
                something the screens behind it do not deliver. */}
            {account.role === 'student' ? <LanguagePicker /> : null}
            <ThemeToggle className="hidden sm:inline-flex" />

            <div className="hidden items-center gap-2 md:flex">
              <span
                aria-hidden="true"
                className="grid size-8 place-items-center rounded-full bg-sunken text-xs font-semibold text-muted ring-1 ring-line"
              >
                {initials(account.full_name)}
              </span>
              <span className="max-w-40 truncate text-sm text-body">
                {account.full_name}
              </span>
            </div>

            <Button variant="ghost" size="sm" onClick={handleSignOut}>
              <Icons.signOut className="size-4" />
              <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        {showSidebar ? (
          <aside className="sticky top-[3.5rem] hidden h-[calc(100vh-3.5rem)] w-60 shrink-0 overflow-y-auto border-r border-line bg-surface px-4 py-5 lg:block">
            {navigation}
          </aside>
        ) : null}

        {/* Drawer, below lg. The same links, not a reduced set: a phone is
            where most students and a fair number of staff will use this. */}
        {showSidebar && drawerOpen ? (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div
              className="absolute inset-0 bg-overlay backdrop-blur-sm"
              onClick={() => setDrawerOpen(false)}
              aria-hidden="true"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Navigation"
              className="animate-rise absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col overflow-y-auto bg-surface shadow-e3"
            >
              <div className="flex items-center justify-between border-b border-line px-4 py-3">
                <span className="text-sm font-semibold text-heading">Sections</span>
                <button
                  ref={closeButton}
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  aria-label="Close navigation"
                  className="flex size-9 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-body"
                >
                  <Icons.close />
                </button>
              </div>
              <div className="px-4 py-5">{navigation}</div>
              <div className="mt-auto border-t border-line px-4 py-3 sm:hidden">
                <ThemeToggle />
              </div>
            </div>
          </div>
        ) : null}

        <main id="main" className="min-w-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
