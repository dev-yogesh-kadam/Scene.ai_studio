"""A fake Scene Provider API v1 server (02-provider-api-v1.md, with the first implementer's changes), for the tests: an
httpx.MockTransport handler, so no port is opened.

Keys: `live` (sa_live_…) and `test` (sa_test_…, a job ends failed with "test_mode" and the quote) keys work; a key in
`revoked` answers 401 key_invalid ("revoked"); `no_credit` 402; `limited` 429 with retry_after 30. A model in
`unavailable` answers 503 at POST /v1/jobs. `refuse` makes POST /v1/jobs answer 400 invalid_request with details.
Each job is running for `polls` looks, then succeeded with one output of its model's kind. What was asked is kept in
`calls` (method, path, the key's last 4, headers that matter, body)."""

import json
import re

import httpx

SEEDANCE = {
    "id": "seedance_2_5", "name": "Seedance 2.5", "capability": "text_to_video", "best_for": "Cinematic multi-shot scenes.",
    "input_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
                     "required": ["prompt"], "properties": {
                         "prompt": {"type": "string"},
                         "duration": {"type": "integer", "minimum": 4, "maximum": 15, "default": 5},
                         "resolution": {"type": "string", "enum": ["480p", "720p"], "default": "480p"},
                         "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16"], "default": "16:9"},
                         "sound": {"type": "boolean", "default": False},
                         "first_frame": {"type": "string", "x-file": "image"},
                         "reference_images": {"type": "array", "maxItems": 9, "items": {"type": "string", "x-file": "image"}}}},
    "limits": {"seconds": {"min": 4, "max": 15}, "resolutions": ["480p", "720p"], "aspect_ratios": ["16:9", "9:16"],
               "max_reference_images": 9, "frames": ["first", "last"], "sound": "choice"},
    "pricing": {"unit": "second", "by": "resolution", "credits": {"480p": 13, "720p": 28}, "credits_with_sound": {"480p": 13, "720p": 28}},
    "typical_seconds": 120, "can_cancel": False}
SPEECH = {"id": "speech", "name": "Speech", "capability": "speech", "best_for": "A voiceover.",
          "input_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"},
                                                                                   "voice_id": {"type": "string", "default": ""}}},
          "limits": {}, "pricing": {"unit": "job", "by": None, "credits": None}, "typical_seconds": 20, "can_cancel": False}
KINDS = {"text_to_video": ("video", "video/mp4", ".mp4"), "speech": ("audio", "audio/mpeg", ".mp3"),
         "image": ("image", "image/png", ".png")}


def _sound_model(model_id):
    """Studio_automation's transcribe, transcribe_video and separate_voice: the same ids, capabilities and schemas as On
    this PC's (providers/local.py), priced by the provider's quote."""
    from scene.providers.local import MODELS
    m = MODELS[model_id]
    return {"id": model_id, "name": m["name"].replace(" (on this PC)", ""), "capability": m["capability"], "best_for": "",
            "input_schema": m["input_schema"], "limits": {}, "pricing": {"unit": "job", "by": None, "credits": None},
            "typical_seconds": m["typical_seconds"], "can_cancel": True}


TRANSCRIBE, TRANSCRIBE_VIDEO, SEPARATE_VOICE = (_sound_model(m) for m in ("transcribe", "transcribe_video", "separate_voice"))
TRANSCRIPT_JSON = (b'{"language": "en", "segments": [{"start": 0.0, "end": 1.2, "speaker": "SPEAKER_00", "text": "Hello there",'
                   b' "words": [{"start": 0.0, "end": 0.5, "word": "Hello"}, {"start": 0.6, "end": 1.2, "word": "there"}]}]}')
TRANSCRIPT_SRT = b"1\n00:00:00,000 --> 00:00:01,200\nHello there\n"
# The outputs of a job by its capability, when it has several: (type, mime, name, the file).
SEVERAL = {"transcribe": [("text", "application/json", "transcript.json", TRANSCRIPT_JSON),
                          ("text", "application/x-subrip", "transcript.srt", TRANSCRIPT_SRT)],
           "separate_voice": [("audio", "audio/wav", "voice.wav", b"just the voice"),
                              ("audio", "audio/wav", "music_fx.wav", b"just the music")]}
# One frame of a real MP4 is not needed: the studio probes it, and an unreadable file reads as 0 seconds.
OUTPUT = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def error(status, code, message, request_id="req_err", **extra):
    body = {"error": dict({"code": code, "message": message, "details": {}}, **extra)}
    return httpx.Response(status, json=body, headers={"X-Request-Id": request_id})


class FakeV1:
    def __init__(self, models=(SEEDANCE, SPEECH), live=("sa_live_alpha1234",), test=("sa_test_beta5678",), polls=1):
        self.models = list(models)
        self.live, self.test = set(live), set(test)
        self.revoked, self.no_credit, self.limited, self.unavailable = set(), set(), set(), set()
        self.refuse = False
        self.polls = polls
        self.voices = None    # GET /v1/voices: None answers 404 (a provider from before the list), else this list
        self.labels = {}      # key -> the label its whoami says (else "fake")
        self.jobs, self.files, self.calls, self.seen = {}, {}, [], {}   # seen: Idempotency-Key -> job id
        self.number = 0
        self.output = OUTPUT   # what every job's output file is (a test that cuts frames from it gives a real MP4)

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle), base_url="http://fake-v1")

    def handle(self, request):
        path = request.url.path
        key = request.headers.get("authorization", "")[7:]
        body = None
        if request.method == "POST" and request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content or b"{}")
        self.calls.append({"method": request.method, "path": path, "last4": key[-4:],
                           "idempotency": request.headers.get("idempotency-key"), "body": body})
        if path == "/v1/health":
            return httpx.Response(200, json={"ok": True, "version": "0.1.0"})
        if key in self.revoked:
            return error(401, "key_invalid", "This key was revoked.")
        if key not in self.live | self.test:
            return error(401, "key_invalid", "This key is not known.")
        if key in self.no_credit:
            return error(402, "insufficient_credit", "The account is out of credit.")
        if key in self.limited:
            return error(429, "rate_limited", "Too many jobs at once.", retry_after=30)
        mode = "test" if key in self.test else "live"
        if path == "/v1/whoami":
            return httpx.Response(200, json={"key": {"id": "key_" + key[-4:], "label": self.labels.get(key, "fake"), "mode": mode, "last4": key[-4:],
                                                     "scopes": ["*"], "max_concurrent": 2, "created_at": "2026-11-13T00:00:00Z"},
                                             "provider": {"name": "Generation server", "version": "0.1.0"},
                                             "credits": {"available": 91296, "used_today": 0}, "alerts": [],
                                             "features": {"webhooks": False, "events": True}},
                                  headers={"X-Request-Id": "req_who"})
        if path == "/v1/voices" and self.voices is not None:
            asked = request.url.params.get("q", "").lower()
            return httpx.Response(200, json={"voices": [v for v in self.voices if asked in v.get("name", "").lower()]})
        if path == "/v1/models":
            return httpx.Response(200, json={"ready": True, "models": self.models})
        if path == "/v1/files" and request.method == "POST":
            self.number += 1
            file_id = "file_{}".format(self.number)
            self.files[file_id] = request.content
            return httpx.Response(201, json={"id": file_id, "name": "f", "mime": "image/png", "bytes": 1, "expires_at": None})
        if path == "/v1/jobs" and request.method == "POST":
            idem = request.headers.get("idempotency-key")
            if not idem:
                return error(400, "invalid_request", "Idempotency-Key is required.")
            if idem in self.seen:
                return httpx.Response(202, json=self._public(self.jobs[self.seen[idem]]), headers={"Idempotent-Replayed": "true"})
            if self.refuse:
                return error(400, "invalid_request", "The input is not valid.", details={"errors": ["duration must be at most 15"]})
            model = next((m for m in self.models if m["id"] == body.get("model")), None)
            if model is None:
                return error(400, "invalid_request", "No such model.")
            if model["id"] in self.unavailable:
                return error(503, "model_unavailable", "The model is down.")
            self.number += 1
            job_id = "job_{}".format(self.number)
            self.seen[idem] = job_id
            price = (model["pricing"].get("credits") or {}).get((body.get("input") or {}).get("resolution", "480p")) \
                if isinstance(model["pricing"].get("credits"), dict) else None
            self.jobs[job_id] = {"id": job_id, "model": model["id"], "status": "queued", "looks": 0, "test": mode == "test",
                                 "input": body.get("input"), "metadata": body.get("metadata"),
                                 "quote": {"credits": price, "source": "price_list"}, "cost": None}
            return httpx.Response(202, json=self._public(self.jobs[job_id]), headers={"X-Request-Id": "req_" + job_id})
        found = re.match(r"^/v1/jobs/(job_\d+)(/cancel|/outputs/(\d+))?$", path)
        if found and found.group(1) in self.jobs:
            job = self.jobs[found.group(1)]
            if found.group(2) == "/cancel":
                charged = job["status"] != "queued"
                job["status"] = "cancelled"
                return httpx.Response(200, json={"id": job["id"], "status": "cancelled", "charged": charged,
                                                 "message": "" if not charged else "The provider still finishes and charges it."})
            if found.group(3) is not None:
                several = SEVERAL.get(self._capability(job))
                if several:
                    n = int(found.group(3))
                    if n >= len(several):
                        return error(404, "not_found", "No such output.")
                    return httpx.Response(200, content=several[n][3], headers={"content-type": several[n][1]})
                return httpx.Response(200, content=self.output, headers={"content-type": KINDS[self._capability(job)][1]})
            self._advance(job)
            return httpx.Response(200, json=self._public(job), headers={"X-Request-Id": "req_poll"})
        return error(404, "not_found", "No such thing.")

    def _capability(self, job):
        return next(m["capability"] for m in self.models if m["id"] == job["model"])

    def _advance(self, job):
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return
        job["looks"] += 1
        if job["looks"] < self.polls:
            job["status"] = "running"
            return
        if job["test"]:
            job.update(status="failed", error={"code": "test_mode", "message": "A test key stops at the quote."},
                       quote={"credits": 65, "source": "provider"}, cost={"credits": 0})
            return
        several = SEVERAL.get(self._capability(job))
        if several:
            job.update(status="succeeded", quote={"credits": 2, "source": "provider"}, cost={"credits": 2},
                       outputs=[{"type": kind, "url": "/v1/jobs/{}/outputs/{}".format(job["id"], n), "mime": mime, "name": name,
                                 "bytes": len(data)} for n, (kind, mime, name, data) in enumerate(several)])
            return
        kind, mime, suffix = KINDS[self._capability(job)]
        job.update(status="succeeded", quote={"credits": 65, "source": "provider"}, cost={"credits": 65},
                   outputs=[{"type": kind, "url": "/v1/jobs/{}/outputs/0".format(job["id"]), "mime": mime,
                             "name": "out" + suffix, "bytes": len(self.output), "seconds": 5.0}])

    def _public(self, job):
        return {k: v for k, v in job.items() if k not in ("looks", "input", "metadata")}
