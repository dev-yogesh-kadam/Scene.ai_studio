// Talks to the studio. The phone site is served by the studio itself (/m/), so every request goes to the same
// address, signed in by the studio's own session cookie, as the studio's pages are.

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
let onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(handler: (() => void) | null) {
  onUnauthorized = handler;
}

/** A path on the studio, for players, pictures and downloads (the same address the site is on). */
export function apiUrl(path: string) {
  return path;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  // JSON bodies are sent as strings; a FormData body sets its own multipart type.
  if (typeof init.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, "Can't reach the studio. Check your connection and try again.");
  }
  if (!(response.headers.get('content-type') ?? '').includes('json')) {
    throw new ApiError(response.status, `The studio answered something unexpected (${response.status}). Reload the page.`);
  }
  const body = await response.json().catch(() => null);
  if (response.status === 401) onUnauthorized?.();
  if (!response.ok) {
    // FastAPI puts the reason in "detail". A bare "Not Found" is a route the studio doesn't have: it runs an older
    // version than this site (it was not restarted after an update).
    const detail =
      response.status === 404 && body?.detail === 'Not Found'
        ? 'The studio is running an older version that doesn’t know this screen. Restart it (scripts\\start.bat) and reload.'
        : body && typeof body.detail === 'string'
          ? body.detail
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail, body);
  }
  return body as T;
}

export function postJson<T>(path: string, body: unknown) {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}
