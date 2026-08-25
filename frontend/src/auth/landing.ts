import type { Role } from '@/api/types';

/** Where each role belongs after signing in.
 *
 * The legacy app kept this as a folder name on the session and included pages
 * out of it, which was also its entire authorization model.
 */
export const LANDING_BY_ROLE: Record<Role, string> = {
  admin: '/admin',
  faculty: '/results',
  student: '/evaluate',
};

export function landingFor(role: Role): string {
  return LANDING_BY_ROLE[role];
}
