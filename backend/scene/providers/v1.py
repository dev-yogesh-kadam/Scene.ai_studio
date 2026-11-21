"""The Scene Provider API v1 (C:\\Scene\\provider-plan\\02-provider-api-v1.md): the one adapter for every generation
provider that speaks it (Studio_automation now; later any service of ours).

- The key goes in `Authorization: Bearer`, never in the address or the body.
- `POST /v1/jobs` carries an `Idempotency-Key` made from the studio's job id (and clip number), so a retry of the same
  job never pays twice; `metadata.scene` says who a job is for and where it was made (jobs._who).
- A job is followed by polling `GET /v1/jobs/{id}` (every POLL_FIRST seconds, backing off to POLL_MOST).
- Every error is mapped by the contract's table onto the three problem kinds of base.py.
- Every answer's `X-Request-Id` is kept on the problem or the result, for the job's log.

With the first implementer's changes to the contract (its section "Changes by the first implementer"):
- A test key's job ends `failed` with `error.code` "test_mode" and the provider's quote: TestMode, shown as "would cost
  N credits", never retried. It is never an HTTP answer.
- `quote` is {"credits", "source"}: at POST an estimate from the price list ("price_list"; credits null for the tools
  only the provider's quote prices), later "provider" once the provider quoted (quote_of).
- `cost` is null until the job is finished; then `cost.credits` is what it counted, 0 when nothing was charged (cost_of).
- Model ids are the provider's own (seedance_2_5, minimax_h3_max, nano-banana-pro; a tool's id is its capability:
  speech, music …), passed through as they are: nothing here makes or changes one.
- File inputs are marked "x-file": "image" | "audio" | "video" in `input_schema` (file_fields), alone or as the items of
  a list (reference_images[]); each is sent as a file id from POST /v1/files.
- Cancel's `charged` says exactly whether the provider charges the job.
"""

import asyncio
import mimetypes
from pathlib import Path

import httpx

from .base import Adapter, KeyProblem, ProviderProblem, RequestProblem

POLL_FIRST = 3      # seconds before the first look at a job
POLL_MOST = 15      # the longest wait between two looks
POLL_GROWTH = 1.5
TIMEOUT = httpx.Timeout(30, connect=5)
DOWNLOAD_TIMEOUT = httpx.Timeout(300, connect=10)

# The contract's error table: code -> (kind, the key's status). Codes it doesn't name go by the HTTP status.
KEY_CODES = {"key_invalid": "invalid", "key_not_allowed": "", "insufficient_credit": "no_credit",
             "rate_limited": "rate_limited", "limit_reached": "rate_limited"}
REQUEST_CODES = ("invalid_request", "content_refused", "not_found", "idempotency_conflict")
PROVIDER_CODES = ("model_unavailable", "provider_error")
TEST_MODE = "test_mode"   # a job-only code: a test key's job stopped at the quote, as asked
FILE_KINDS = ("image", "audio", "video")


class TestMode(RequestProblem):
    """A test key's job stopped at the provider's quote: nothing was made or charged. `credits` is the quote (None when
    the provider gave none). Never retried."""

    __test__ = False   # not a test class, whatever pytest makes of its name

    def __init__(self, message, credits=None, request_id=""):
        super().__init__(message, request_id, TEST_MODE)
        self.credits = credits


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def quote_of(body):
    """A job object's quote: {"credits": a number or None, "source": "price_list" | "provider" | ""}. At POST it is the
    price list's estimate (credits None for the tools only the provider's quote prices); once quoted, the provider's."""
    quote = body.get("quote") if isinstance(body, dict) and isinstance(body.get("quote"), dict) else {}
    return {"credits": _number(quote.get("credits")), "source": str(quote.get("source") or "")}


def cost_of(body):
    """What a finished job counted (`cost.credits`: the charge, 0 when nothing was charged), or None while it runs or
    when the provider did not say."""
    if not isinstance(body, dict) or body.get("status") not in ("succeeded", "failed", "cancelled"):
        return None
    cost = body.get("cost") if isinstance(body.get("cost"), dict) else {}
    return _number(cost.get("credits"))


def file_fields(input_schema):
    """{input name: (kind, a list?, its most files or None)} of the inputs that take a file: those marked "x-file" (a
    list's items marked so), as the contract's input_schema marks them."""
    found = {}
    properties = (input_schema or {}).get("properties") if isinstance(input_schema, dict) else None
    for name, spec in (properties or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("x-file") in FILE_KINDS:
            found[name] = (spec["x-file"], False, 1)
        elif spec.get("type") == "array" and isinstance(spec.get("items"), dict) and spec["items"].get("x-file") in FILE_KINDS:
            most = spec.get("maxItems")
            found[name] = (spec["items"]["x-file"], True, most if isinstance(most, int) and not isinstance(most, bool) else None)
    return found


def job_problem(body):
    """The problem a job that ended `failed` is, from its `error` ({code, message}): TestMode for "test_mode" (with the
    quote), else by the contract's codes, a RequestProblem when the code is none of them. A job that started is never
    sent again, so this says why it failed rather than where to retry."""
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = str(error.get("code") or "")
    message = str(error.get("message") or "").strip()
    request_id = str(body.get("request_id") or "")
    if code == TEST_MODE:
        credits = quote_of(body)["credits"]
        said = "Test mode: would cost {:,g} credits".format(credits) if credits is not None else "Test mode: stopped at the quote"
        return TestMode(said + (" ({})".format(message) if message else "") + ".", credits, request_id)
    message = message or "The provider could not make it."
    if code in KEY_CODES:
        return KeyProblem(message, KEY_CODES[code], _number(error.get("retry_after")), request_id, code)
    if code in PROVIDER_CODES:
        return ProviderProblem(message, request_id, code)
    return RequestProblem(message, request_id, code or "failed")


def idempotency_key(job_id, clip=None):
    """The Idempotency-Key of one studio job (one clip of a long video): the same on every retry of it."""
    return "scene-job-{}".format(job_id) + ("-clip-{}".format(clip) if clip else "")


def problem_of(response):
    """The problem an error answer is, by the contract's table. `response` is an httpx.Response with status >= 400."""
    request_id = response.headers.get("x-request-id", "")
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
    code = str(error.get("code") or "")
    message = str(error.get("message") or "").strip() or "{} answered {}.".format("The provider", response.status_code)
    listed = (error.get("details") or {}).get("errors") if isinstance(error.get("details"), dict) else None
    if isinstance(listed, list) and listed:   # the input check's readable problems, each said
        message = message.rstrip(".") + ": " + "; ".join(str(e) for e in listed[:6])
    retry_after = error.get("retry_after")
    if not isinstance(retry_after, (int, float)) or isinstance(retry_after, bool):
        try:
            retry_after = float(response.headers.get("retry-after", ""))
        except ValueError:
            retry_after = None
    status = response.status_code
    if code in KEY_CODES:
        return KeyProblem(message, KEY_CODES[code], retry_after, request_id, code)
    if code in REQUEST_CODES:
        return RequestProblem(message, request_id, code)
    if code in PROVIDER_CODES:
        return ProviderProblem(message, request_id, code)
    if status == 401:
        return KeyProblem(message, "invalid", None, request_id, code or "key_invalid")
    if status == 403:
        return KeyProblem(message, "", None, request_id, code or "key_not_allowed")
    if status == 402:
        return KeyProblem(message, "no_credit", retry_after, request_id, code or "insufficient_credit")
    if status == 429:
        return KeyProblem(message, "rate_limited", retry_after, request_id, code or "rate_limited")
    if status >= 500:
        return ProviderProblem(message, request_id, code or "provider_error")
    return RequestProblem(message, request_id, code or "invalid_request")


class V1(Adapter):
    kind = "scene_provider_v1"

    def __init__(self, base_url="", http=None):
        super().__init__(base_url)
        self.http = http   # a client of the caller's (the tests'); else one per call

    def _url(self, path):
        if not self.base_url:
            raise ProviderProblem("This provider has no address yet: add it in Servers & APIs → Providers.")
        return self.base_url + path if path.startswith("/") else path

    async def _call(self, method, path, key, timeout=TIMEOUT, allow=(), **kwargs):
        """One request. An answer of 400 or more is raised as its problem, unless its status is in `allow`."""
        headers = dict(kwargs.pop("headers", None) or {}, Authorization="Bearer " + str(key or ""))
        try:
            if self.http is not None:
                response = await self.http.request(method, self._url(path), headers=headers, timeout=timeout, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=timeout) as http:
                    response = await http.request(method, self._url(path), headers=headers, **kwargs)
        except httpx.HTTPError as error:
            raise ProviderProblem("The provider did not answer ({}).".format(type(error).__name__))
        if response.status_code >= 400 and response.status_code not in allow:
            raise problem_of(response)
        return response

    async def _json(self, method, path, key, **kwargs):
        response = await self._call(method, path, key, **kwargs)
        try:
            body = response.json()
        except ValueError:
            raise ProviderProblem("The provider answered something that is not JSON.", response.headers.get("x-request-id", ""))
        if not isinstance(body, dict):
            raise ProviderProblem("The provider's answer is not an object.", response.headers.get("x-request-id", ""))
        return body, response.headers.get("x-request-id", "")

    async def health(self):
        """GET /v1/health (no key): {"ok", "version"}."""
        body, _ = await self._json("GET", "/v1/health", "")
        return body

    async def whoami(self, key):
        body, _ = await self._json("GET", "/v1/whoami", key)
        return body

    async def models(self, key):
        body, _ = await self._json("GET", "/v1/models", key)
        found = []
        for model in body.get("models") or []:
            if isinstance(model, dict) and model.get("id") and model.get("capability"):
                found.append(model)
        if body.get("ready") is False and not found:
            raise ProviderProblem("The provider is not ready: it has no account signed in.")
        return found

    async def voices(self, key, q="", language=""):
        """GET /v1/voices: the provider's voice library for its speech model, [{"id", "name", "language", "gender",
        "preview_url"}]. None when the provider has no such list (404: a provider from before it), so the caller can
        say so; a key without speech in its scope is a KeyProblem like any other."""
        params = {k: v for k, v in (("q", q), ("language", language)) if v}
        response = await self._call("GET", "/v1/voices", key, allow=(404,), params=params)
        if response.status_code == 404:
            return None
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise ProviderProblem("The provider's voice list is not an object.", response.headers.get("x-request-id", ""))
        found = []
        for v in body.get("voices") or []:
            if isinstance(v, dict) and v.get("id"):
                found.append({"id": str(v["id"])[:200], "name": str(v.get("name") or v["id"])[:120],
                              "language": str(v.get("language") or "")[:40], "gender": str(v.get("gender") or "")[:20],
                              "preview_url": str(v.get("preview_url") or "")[:2000]})
        return found

    async def upload(self, key, path=None, name=None, data=None):
        """POST /v1/files: a file of the job's (a path, or `data` with its `name`); returns its id ("file_…")."""
        if data is None:
            path = Path(path)
            name = name or path.name
            data = path.read_bytes()
        mime = mimetypes.guess_type(name or "")[0] or "application/octet-stream"
        body, _ = await self._json("POST", "/v1/files", key, files={"file": (name or "file", data, mime)},
                                   timeout=DOWNLOAD_TIMEOUT)
        if not body.get("id"):
            raise ProviderProblem("The provider took the file but gave it no id.")
        return str(body["id"])

    async def start(self, key, model, input, metadata, idempotency_key):
        """POST /v1/jobs. `model` is the provider's own id. Returns the job object with "request_id", "replayed" (the
        same job given back for a retry: Idempotent-Replayed), and its quote as quote_of reads it."""
        response = await self._call("POST", "/v1/jobs", key, headers={"Idempotency-Key": idempotency_key},
                                    json={"model": model, "input": input, "metadata": metadata or {}, "webhook_url": None})
        request_id = response.headers.get("x-request-id", "")
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or not body.get("id"):
            raise ProviderProblem("The provider took the job but gave it no id.", request_id)
        replayed = response.headers.get("idempotent-replayed", "").lower() == "true"
        return dict(body, request_id=request_id, replayed=replayed, quote=quote_of(body))

    async def status(self, key, job_ref):
        """GET /v1/jobs/{id}, with "request_id", the quote as quote_of reads it, and "cost" as cost_of reads it (None
        until the job is finished)."""
        body, request_id = await self._json("GET", "/v1/jobs/{}".format(job_ref), key)
        return dict(body, request_id=request_id, quote=quote_of(body), cost=cost_of(body))

    async def cancel(self, key, job_ref):
        """POST /v1/jobs/{id}/cancel: {"status", "charged" (whether the provider charges it: true once the generate call
        was sent, whatever can_cancel says), "message"}. A job that had finished answers its status."""
        body, _ = await self._json("POST", "/v1/jobs/{}/cancel".format(job_ref), key)
        return dict(body, charged=bool(body.get("charged", True)), message=str(body.get("message") or ""))

    async def fetch_output(self, key, job_ref, n, target, outputs=None):
        """Write output `n` of the job to `target`. `outputs`: the job's list when the caller has it."""
        if outputs is None:
            outputs = (await self.status(key, job_ref)).get("outputs") or []
        if n >= len(outputs) or not isinstance(outputs[n], dict) or not outputs[n].get("url"):
            raise ProviderProblem("The provider has no output {} for this job.".format(n + 1))
        url = str(outputs[n]["url"])
        headers = {"Authorization": "Bearer " + str(key or "")}
        try:
            client = self.http or httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT)
            try:
                async with client.stream("GET", self._url(url), headers=headers, timeout=DOWNLOAD_TIMEOUT) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise problem_of(response)
                    with open(target, "wb") as handle:
                        async for chunk in response.aiter_bytes():
                            handle.write(chunk)
            finally:
                if client is not self.http:
                    await client.aclose()
        except httpx.HTTPError as error:
            raise ProviderProblem("The provider's file could not be fetched ({}).".format(type(error).__name__))
        return outputs[n]

    async def follow(self, key, job_ref, on_change=None, cancelled=None, most=None):
        """Poll a job until it ends; returns its last answer. `on_change(answer)` is told each answer; `cancelled()`
        says when the studio's job was cancelled (then the provider is asked to cancel and Cancelled is raised by the
        caller from the answer {"status": "cancelled", "studio_cancelled": True}). A provider that stops answering for
        long is a ProviderProblem. `most`: seconds after which it is given up."""
        wait, failures, waited = POLL_FIRST, 0, 0.0
        while True:
            await asyncio.sleep(wait)
            waited += wait
            if cancelled is not None and cancelled():
                try:
                    said = await self.cancel(key, job_ref)
                except (KeyProblem, ProviderProblem, RequestProblem):
                    said = {"charged": True}   # the job was sent: the provider may well charge it
                return dict(said, status="cancelled", studio_cancelled=True)
            if most is not None and waited > most:
                raise ProviderProblem("The provider had not finished this job after {:g} hours.".format(most / 3600))
            try:
                answer = await self.status(key, job_ref)
                failures = 0
            except ProviderProblem:
                failures += 1
                if failures > 30:
                    raise
                continue
            if on_change is not None:
                on_change(answer)
            if answer.get("status") in ("succeeded", "failed", "cancelled"):
                return answer
            wait = min(POLL_MOST, wait * POLL_GROWTH)
