// Talks to the studio. The phone site (/m/) and the studio's own pages are served by the studio itself, so every
// request goes to the same address, signed in by the studio's own session cookie.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: unknown = null,
  ) {
    super(message);
  }
}

// Called when the studio no longer knows the session (it ran out, or it was signed out elsewhere): back to sign-in.
// It is told the path that was refused: a wrong password at /api/auth/login is a 401 too, and is not a signing out.
let onUnauthorized: ((path: string) => void) | null = null;

export function setOnUnauthorized(handler: ((path: string) => void) | null) {
  onUnauthorized = handler;
}

/** A path on the studio, for players, pictures and downloads (the same address the site is on). */
export function apiUrl(path: string) {
  return path;
}

/** What went wrong, in words, from FastAPI's answer: its "detail" (a list of field errors says so as a whole). */
export function reasonOf(status: number, body: unknown) {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (status === 404 && detail === 'Not Found') {
    // A bare "Not Found" is a route the studio doesn't have: it runs an older version than this site.
    return 'The studio is running an older version that doesn’t know this screen. Restart it (scripts\\start.bat) and reload.';
  }
  if (Array.isArray(detail)) return 'Some fields are missing or wrong.';
  return typeof detail === 'string' && detail ? detail : `Request failed (${status})`;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  // JSON bodies are sent as strings; a FormData body sets its own multipart type.
  if (typeof init.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: 'same-origin' });
  } catch (error) {
    if ((error as Error)?.name === 'AbortError') throw error;
    throw new ApiError(0, "Can't reach the studio. Check your connection and try again.");
  }
  if (!(response.headers.get('content-type') ?? '').includes('json')) {
    throw new ApiError(
      response.status,
      `The studio answered something unexpected (${response.status}). Reload the page.`,
    );
  }
  const body = await response.json().catch(() => null);
  if (response.status === 401) onUnauthorized?.(path);
  if (!response.ok) throw new ApiError(response.status, reasonOf(response.status, body), body);
  // A slow answer (a model loading) is sent late, after its status: an error then says its status as "failed".
  const failed = (body as { failed?: number } | null)?.failed;
  if (failed) throw new ApiError(failed, reasonOf(failed, body), body);
  return body as T;
}

export function postJson<T>(path: string, body: unknown) {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export type ApiOptions = Omit<RequestInit, 'body'> & { json?: unknown; body?: BodyInit | null };

/** A call with an optional JSON body: api('/api/projects', { method: 'POST', json: { name } }). */
export function api<T>(path: string, { json, ...init }: ApiOptions = {}) {
  return request<T>(path, json === undefined ? init : { ...init, body: JSON.stringify(json) });
}
