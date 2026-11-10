// Everyone the Users list holds, page after page: GET /api/admin/users answers at most 500 people a page (`limit`,
// `offset`) and says where the next page starts (`next_offset`, null after the last).

import { api } from '../../../common/api';

export const USERS_PAGE = 500;

type Page<T> = { users: T[]; next_offset?: number | null };

export async function allUsers<T>(filters: Record<string, string> = {}, fetchPage = api<Page<T>>): Promise<T[]> {
  const found: T[] = [];
  let offset: number | null = 0;
  while (offset !== null) {
    const page: Page<T> = await fetchPage(
      '/api/admin/users?' + new URLSearchParams({ ...filters, limit: String(USERS_PAGE), offset: String(offset) }),
    );
    found.push(...page.users);
    const next: number | null = page.next_offset ?? null;
    offset = next !== null && next > offset ? next : null; // a next page that does not move on ends it
  }
  return found;
}
