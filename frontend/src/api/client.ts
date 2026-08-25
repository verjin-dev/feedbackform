const BASE_URL = '/api';

/** An error carrying the status and the server's message, so callers can
 *  distinguish "you are signed out" from "that was rejected". */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** A conflict the user can act on: already submitted, name taken, window
   *  closed. Worth showing verbatim; the API writes these for people. */
  get isConflict(): boolean {
    return this.status === 409;
  }
}

/** FastAPI returns `detail` as a string, or as a list of objects for
 *  validation failures. Both must become something showable. */
function readDetail(body: unknown, fallback: string): string {
  if (typeof body !== 'object' || body === null) return fallback;
  const detail = (body as { detail?: unknown }).detail;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        typeof item === 'object' && item !== null && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : null,
      )
      .filter((msg): msg is string => msg !== null);
    if (messages.length > 0) return messages.join('. ');
  }

  return fallback;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  query?: Record<string, string | number | boolean | undefined>;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, query } = options;

  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const init: RequestInit = {
    method,
    // The session lives in an httpOnly cookie the app cannot read. Same-origin
    // is enough for it to travel, and the dev server proxies /api to make it
    // so — see vite.config.ts.
    credentials: 'same-origin',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) init.body = JSON.stringify(body);
  if (signal) init.signal = signal;

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(0, 'Could not reach the server. Check your connection.');
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      readDetail(parsed, `Request failed (${response.status})`),
      parsed,
    );
  }

  return parsed as T;
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query']) =>
    request<T>(path, query ? { query } : {}),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};
