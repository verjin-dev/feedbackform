import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, api } from '@/api/client';

function mockFetch(status: number, body: unknown) {
  // 204 and friends are null-body statuses; the Response constructor rejects
  // even an empty string for them.
  const payload = body === null ? null : JSON.stringify(body);
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(payload, { status })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('returns the parsed body on success', async () => {
    mockFetch(200, { id: 7, full_name: 'Asha Raman' });

    await expect(api.get('/auth/me')).resolves.toEqual({
      id: 7,
      full_name: 'Asha Raman',
    });
  });

  it('returns undefined for 204 rather than trying to parse it', async () => {
    mockFetch(204, null);

    await expect(api.post('/auth/logout')).resolves.toBeUndefined();
  });

  it('surfaces a string detail as the message', async () => {
    mockFetch(409, { detail: 'You have already submitted feedback for this subject.' });

    await expect(api.post('/evaluations', {})).rejects.toThrow(
      'You have already submitted feedback for this subject.',
    );
  });

  it('flattens a validation error list into something showable', async () => {
    // FastAPI returns 422 as a list of objects, which would otherwise render
    // as "[object Object]".
    mockFetch(422, {
      detail: [
        { loc: ['body', 'password'], msg: 'String should have at least 12 characters' },
        { loc: ['body', 'email'], msg: 'value is not a valid email address' },
      ],
    });

    await expect(api.post('/accounts', {})).rejects.toThrow(
      'String should have at least 12 characters. value is not a valid email address',
    );
  });

  it('classifies statuses so callers can branch without magic numbers', async () => {
    mockFetch(401, { detail: 'Not authenticated' });

    const error = await api.get('/auth/me').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isUnauthenticated).toBe(true);
    expect((error as ApiError).isForbidden).toBe(false);
  });

  it('reports a network failure as a readable message, not a raw TypeError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    await expect(api.get('/auth/me')).rejects.toThrow('Could not reach the server');
  });

  it('sends credentials so the session cookie travels', async () => {
    mockFetch(200, {});
    await api.get('/auth/me');

    const [, init] = vi.mocked(fetch).mock.calls[0] as [unknown, RequestInit];
    expect(init.credentials).toBe('same-origin');
  });

  it('appends query parameters and skips undefined ones', async () => {
    mockFetch(200, []);
    await api.get('/accounts', { role: 'faculty', class_group_id: undefined });

    const [url] = vi.mocked(fetch).mock.calls[0] as [URL, unknown];
    expect(url.searchParams.get('role')).toBe('faculty');
    expect(url.searchParams.has('class_group_id')).toBe(false);
  });
});
