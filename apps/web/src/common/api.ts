// The studio's API client, from packages/shared (one client for the studio, the console and the phone site).

export { ApiError, api, apiUrl, postJson, request, setOnUnauthorized } from '@scene/shared/api/client';
export { requestLines, type Line } from '@scene/shared/api/stream';
