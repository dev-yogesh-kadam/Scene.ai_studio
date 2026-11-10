import { describe, expect, it, vi } from 'vitest';
import { allUsers } from './allUsers';

describe('allUsers', () => {
  it('asks for the next page while there is one, with the filters, and returns everyone in order', async () => {
    const asked: string[] = [];
    const fetchPage = vi.fn(async (url: string) => {
      asked.push(url);
      const offset = Number(new URL(url, 'http://x').searchParams.get('offset'));
      return offset === 0
        ? { users: [{ id: 1 }, { id: 2 }], next_offset: 500 }
        : offset === 500
          ? { users: [{ id: 3 }], next_offset: 1000 }
          : { users: [{ id: 4 }], next_offset: null };
    });
    expect(await allUsers({ q: 'ada', show: '' }, fetchPage)).toEqual([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }]);
    expect(asked).toEqual([
      '/api/admin/users?q=ada&show=&limit=500&offset=0',
      '/api/admin/users?q=ada&show=&limit=500&offset=500',
      '/api/admin/users?q=ada&show=&limit=500&offset=1000',
    ]);
  });

  it('is one call under 500 people, and an answer without next_offset (an older studio) ends it', async () => {
    const fetchPage = vi.fn(async () => ({ users: [{ id: 1 }] }));
    expect(await allUsers({}, fetchPage)).toEqual([{ id: 1 }]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('stops when a next page would not move on', async () => {
    const fetchPage = vi.fn(async () => ({ users: [{ id: 1 }], next_offset: 0 }));
    expect(await allUsers({}, fetchPage)).toEqual([{ id: 1 }]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });
});
