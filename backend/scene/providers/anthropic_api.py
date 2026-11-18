"""Anthropic as a provider: the agent's model (capability agent_llm) with real API keys. Only the check of a key and its
list of models live here; the agent's calls go through claude.py and Claude Code as before, with the key the registry
says is in use (claude_connection.apply)."""

import time

import httpx

from .base import AGENT_LLM, Adapter, KeyProblem, ProviderProblem, RequestProblem

ANTHROPIC = "https://api.anthropic.com"
VERSION = "2023-06-01"
CHECK_WAIT = 10


def _problem(response):
    request_id = response.headers.get("request-id", "")
    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        error = {}
    message = str(error.get("message") or "") or "Anthropic answered {}.".format(response.status_code)
    if response.status_code in (401, 403):
        return KeyProblem("Anthropic refused the API key: " + message, "invalid", None, request_id, "key_invalid")
    if response.status_code == 402 or "credit balance" in message.lower():
        return KeyProblem(message, "no_credit", None, request_id, "insufficient_credit")
    if response.status_code == 429:
        try:
            wait = float(response.headers.get("retry-after", ""))
        except ValueError:
            wait = None
        return KeyProblem(message, "rate_limited", wait, request_id, "rate_limited")
    if response.status_code >= 500 or response.status_code == 529:
        return ProviderProblem(message, request_id, "provider_error")
    return RequestProblem(message, request_id, "invalid_request")


class Anthropic(Adapter):
    kind = "anthropic"

    def __init__(self, base_url="", http=None):
        super().__init__(base_url or ANTHROPIC)
        self.http = http

    async def _get(self, path, key, **params):
        headers = {"x-api-key": str(key or ""), "anthropic-version": VERSION}
        try:
            if self.http is not None:
                response = await self.http.get(self.base_url + path, params=params, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=CHECK_WAIT) as http:
                    response = await http.get(self.base_url + path, params=params, headers=headers)
        except httpx.HTTPError as error:
            raise ProviderProblem("Anthropic's API did not answer ({}).".format(type(error).__name__))
        if response.status_code >= 400:
            raise _problem(response)
        return response.json()

    async def whoami(self, key):
        """Asks for a list of one model: no tokens are spent."""
        if not key:
            raise KeyProblem("No Anthropic API key yet.", "invalid")
        await self._get("/v1/models", key, limit=1)
        return {"key": {"label": "", "mode": "live", "max_concurrent": None},
                "provider": {"name": "Anthropic", "version": VERSION}, "checked": time.time()}

    async def models(self, key):
        body = await self._get("/v1/models", key, limit=100)
        return [{"id": m["id"], "name": m.get("display_name") or m["id"], "capability": AGENT_LLM}
                for m in body.get("data") or [] if isinstance(m, dict) and m.get("id")]
