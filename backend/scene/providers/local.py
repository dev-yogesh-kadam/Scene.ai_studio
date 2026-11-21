"""On this PC: the tools the studio runs itself, as a provider like any other (kind "local_tools"), so the router, the
catalog, the forms, the queue and the console treat them as they treat Studio_automation's models.

- transcribe, transcribe_video: a transcript with times (transcript.json, transcript.srt), of a sound or a video's;
- separate_voice: a voice track and a music-and-effects track (voice.wav, music_fx.wav) that add up to the input.

They run in `backend/local_tools/run.py` with the Python of settings.local_tools_python (.venv-audio, which holds
PyTorch, faster-whisper and Demucs), one process a job, one job at a time (the GPU is shared). They are free: the
quote and the cost are 0, as the contract says for a local backend. A tool whose software is missing is not offered
(models() leaves it out); the console says what to install.

The provider has one key row with no secret, so the router counts its jobs and its "max at
once" (1) like any key's. Its jobs live in this process (JOBS): after a restart a job that was running is lost, and
the queue says so."""

import asyncio
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

from .base import Adapter, ProviderProblem, RequestProblem

KIND = "local_tools"
NAME = "On this PC"
CHECK_FRESH = 600     # seconds what is installed is kept between two looks
POLL = 1.0            # seconds between two looks at a running job
KEEP_DAYS = 2         # job folders older than this are removed when a job starts
SCRIPT = Path(__file__).resolve().parents[2] / "local_tools" / "run.py"
MIMES = {".json": "application/json", ".srt": "application/x-subrip", ".wav": "audio/wav"}
FREE = {"credits": 0, "source": "local"}

# The models: their tool (run.py's), their capability (the contract's, 02-provider-api-v1.md) and their one required
# file, so the agent sees them as work on a sound (agent.takes_sound).
LANGUAGE = {"type": "string", "enum": ["auto", "en", "hi"], "default": "auto", "title": "Language"}
SPEAKERS = {"type": "boolean", "default": False, "title": "Speaker labels",
            "description": "Not set up yet: every line is SPEAKER_00."}
TRANSCRIPT = ("A transcript with each line's and each word's times (transcript.json, and subtitles as transcript.srt): "
              "for subtitles, timing shots to a voice-over, and finding what is said where. Free, on this PC.")
MODELS = {
    "transcribe": {
        "tool": "transcribe", "capability": "transcribe", "name": "Transcribe audio (on this PC)", "best_for": TRANSCRIPT,
        "input_schema": {"type": "object", "x-order": ["audio", "language", "speakers"], "required": ["audio"], "properties": {
            "audio": {"type": "string", "x-file": "audio", "title": "Audio", "description": "The sound to transcribe."},
            "language": LANGUAGE, "speakers": SPEAKERS}},
        "typical_seconds": 60,
    },
    "transcribe_video": {
        "tool": "transcribe", "capability": "transcribe", "name": "Transcribe a video (on this PC)", "best_for": TRANSCRIPT,
        "input_schema": {"type": "object", "x-order": ["video", "language", "speakers"], "required": ["video"], "properties": {
            "video": {"type": "string", "x-file": "video", "title": "Video", "description": "A video: its sound is transcribed."},
            "language": LANGUAGE, "speakers": SPEAKERS}},
        "typical_seconds": 60,
    },
    "separate_voice": {
        "tool": "separate_voice", "capability": "separate_voice", "name": "Separate voice (on this PC)",
        "best_for": "The voice taken out of music and effects (voice.wav), and the music and effects without it "
                    "(music_fx.wav), each the input's exact length. Free, on this PC.",
        "input_schema": {"type": "object", "x-order": ["audio"], "required": ["audio"], "properties": {
            "audio": {"type": "string", "x-file": "audio", "title": "Audio (voice + music + effects)"}}},
        "typical_seconds": 30,
    },
}

JOBS = {}              # job ref -> {"status", "progress", "message", "outputs", "error", "folder", "process", "started"}
_RUN = asyncio.Lock    # made per event loop on first use (_gate)
_gate = {}
_checked = {}          # python path -> (when, {"transcribe": {"ready", "why"}, ...})


def _lock():
    loop = asyncio.get_running_loop()
    if loop not in _gate:
        _gate[loop] = _RUN()
    return _gate[loop]


class LocalTools(Adapter):
    kind = KIND

    def __init__(self, base_url="", python="", work_dir="", models_dir=""):
        super().__init__("")
        self.python = str(python or "")
        self.work_dir = Path(work_dir) if work_dir else Path.cwd() / "local_tools_work"
        self.models_dir = str(models_dir or "")

    # ------------------------------------------------------------ what is installed

    async def installed(self):
        """{"device", "transcribe": {"ready", "why"}, "separate_voice": {...}}, kept CHECK_FRESH seconds."""
        kept = _checked.get(self.python)
        if kept and time.time() - kept[0] < CHECK_FRESH:
            return kept[1]
        if not self.python or not Path(self.python).is_file():
            why = "The tools' Python is not there ({}): set it up as docs/servers.md says (Tools on this PC).".format(self.python or "not set")
            found = {"device": "", **{m["tool"]: {"ready": False, "why": why} for m in MODELS.values()}}
        else:
            try:
                process = await asyncio.create_subprocess_exec(self.python, str(SCRIPT), "check", stdout=asyncio.subprocess.PIPE,
                                                               stderr=asyncio.subprocess.DEVNULL)
                out, _ = await asyncio.wait_for(process.communicate(), 120)
                found = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
            except (OSError, asyncio.TimeoutError, ValueError, IndexError) as error:
                found = {"device": "", **{m["tool"]: {"ready": False, "why": "The tools could not be checked ({}).".format(type(error).__name__)}
                                          for m in MODELS.values()}}
        _checked[self.python] = (time.time(), found)
        return found

    async def whoami(self, key):
        found = await self.installed()
        alerts = sorted({found[m["tool"]]["why"] for m in MODELS.values() if not (found.get(m["tool"]) or {}).get("ready")})
        return {"key": {"label": "This PC", "mode": "live", "max_concurrent": 1, "scopes": ["*"]},
                "provider": {"name": NAME, "version": "1", "device": found.get("device") or ""},
                "credits": {}, "alerts": alerts}

    async def models(self, key):
        found = await self.installed()
        return [{"id": mid, "name": m["name"], "capability": m["capability"], "best_for": m["best_for"], "input_schema": m["input_schema"],
                 "limits": {}, "pricing": {"unit": "job", "credits": 0}, "typical_seconds": m["typical_seconds"], "can_cancel": True}
                for mid, m in MODELS.items() if (found.get(m["tool"]) or {}).get("ready")]

    # ------------------------------------------------------------ files and jobs

    async def upload(self, key, path=None, name=None, data=None):
        """A file of the job's, kept in the work folder until its job ends: its id is its path there."""
        folder = self.work_dir / "files"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "{}_{}".format(uuid.uuid4().hex[:12], Path(str(name or (path and Path(path).name) or "file")).name)
        if data is None:
            shutil.copyfile(path, target)
        else:
            target.write_bytes(data)
        return "local:" + str(target)

    def _path_of(self, value):
        text = str(value or "")
        if not text.startswith("local:"):
            raise RequestProblem("A file for a tool on this PC must be sent to it first.")
        path = Path(text[len("local:"):])
        if not path.is_file() or self.work_dir.resolve() not in path.resolve().parents:
            raise RequestProblem("The file for this job is gone: add it to the job again.")
        return str(path)

    def _clean_old(self):
        if not self.work_dir.is_dir():
            return
        cutoff = time.time() - KEEP_DAYS * 86400
        for child in list(self.work_dir.glob("jobs/*")) + list(self.work_dir.glob("files/*")):
            try:
                if child.stat().st_mtime < cutoff and str(child.name) not in JOBS:
                    shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()
            except OSError:
                pass

    async def start(self, key, model, input, metadata, idempotency_key):
        if model not in MODELS:
            raise RequestProblem("This PC has no tool called {}.".format(model))
        tool = MODELS[model]["tool"]
        if not (((await self.installed()).get(tool)) or {}).get("ready"):
            raise ProviderProblem((await self.installed())[tool]["why"])
        ref = "local_" + "".join(c for c in str(idempotency_key) if c.isalnum() or c in "-_")[:80]
        if ref in JOBS and JOBS[ref]["status"] in ("queued", "running", "succeeded"):
            return {"id": ref, "status": JOBS[ref]["status"], "quote": dict(FREE), "request_id": ref, "replayed": True}
        given = {k: v for k, v in (input or {}).items() if v not in (None, "")}
        wanted = MODELS[model]["input_schema"]["required"][0]
        if not given.get(wanted):
            raise RequestProblem("Give it {}.".format("a video" if wanted == "video" else "an audio file"))
        given = {k: (self._path_of(v) if k == wanted else v) for k, v in given.items() if k == wanted or k not in ("audio", "video")}
        self._clean_old()
        folder = self.work_dir / "jobs" / ref
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        (folder / "job.json").write_text(json.dumps({"input": given, "models_dir": self.models_dir}), encoding="utf-8")
        JOBS[ref] = {"status": "queued", "progress": 0.0, "message": "Waiting for this PC", "outputs": [], "error": None,
                     "folder": str(folder), "process": None, "started": time.time(), "cancel": False}
        asyncio.get_running_loop().create_task(self._run(ref, tool, folder))
        return {"id": ref, "status": "queued", "quote": dict(FREE), "request_id": ref}

    async def _run(self, ref, tool, folder):
        job = JOBS[ref]
        async with _lock():   # one tool at a time: they share the GPU
            if job["cancel"]:
                job.update(status="cancelled", message="Cancelled before it started.")
                return
            job.update(status="running", message="Starting")
            lines = []
            try:
                process = await asyncio.create_subprocess_exec(self.python, str(SCRIPT), tool, str(folder),
                                                               stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                job["process"] = process
                errors = asyncio.ensure_future(process.stderr.read())
                async for raw in process.stdout:
                    try:
                        said = json.loads(raw.decode("utf-8", "replace"))
                    except ValueError:
                        continue
                    lines.append(said)
                    if isinstance(said.get("progress"), (int, float)):
                        job["progress"] = float(said["progress"])
                    if said.get("message"):
                        job["message"] = str(said["message"])[:200]
                await process.wait()
                tail = (await errors).decode("utf-8", "replace").strip().splitlines()[-3:]
            except OSError as error:
                job.update(status="failed", error={"code": "provider_error", "message": "The tool could not start ({}).".format(error)})
                return
            if job["cancel"]:
                job.update(status="cancelled", message="Cancelled.")
                return
            done = next((s for s in reversed(lines) if s.get("done")), None)
            if done:
                outputs = [{"name": o["name"], "mime": o.get("mime") or MIMES.get(Path(o["name"]).suffix, "application/octet-stream")}
                           for o in done.get("outputs") or [] if (folder / o["name"]).is_file()]
                job.update(status="succeeded", progress=1.0, outputs=outputs, message=str(done.get("message") or "")[:200])
                return
            said = next((s.get("error") for s in reversed(lines) if s.get("error")), None)
            print("Local tool {} failed: {}".format(tool, " | ".join(tail)), file=sys.stderr)
            job.update(status="failed", error={"code": "invalid_input" if said and not said.split(":")[0].endswith("Error") else "provider_error",
                                               "message": said or "The tool stopped without saying why (exit {}).".format(process.returncode)})

    def _answer(self, ref):
        job = JOBS.get(ref)
        if job is None:
            return {"id": ref, "status": "failed", "error": {"code": "provider_error",
                    "message": "The studio restarted while this ran on this PC: make it again."}, "quote": dict(FREE), "cost": 0}
        ended = job["status"] in ("succeeded", "failed", "cancelled")
        return {"id": ref, "status": job["status"], "progress": job["progress"], "message": job["message"],
                "outputs": [dict(o) for o in job["outputs"]], "error": job["error"], "quote": dict(FREE),
                "cost": 0 if ended else None, "request_id": ref}

    async def status(self, key, job_ref):
        return self._answer(job_ref)

    async def cancel(self, key, job_ref):
        job = JOBS.get(job_ref)
        if job is not None and job["status"] in ("queued", "running"):
            job["cancel"] = True
            process = job.get("process")
            if process is not None and process.returncode is None:
                process.kill()
        return {"status": "cancelled", "charged": False, "message": "Stopped on this PC: nothing is charged."}

    async def follow(self, key, job_ref, on_change=None, cancelled=None, most=None):
        waited = 0.0
        while True:
            await asyncio.sleep(POLL)
            waited += POLL
            if cancelled is not None and cancelled():
                return dict(await self.cancel(key, job_ref), status="cancelled", studio_cancelled=True)
            if most is not None and waited > most:
                await self.cancel(key, job_ref)
                raise ProviderProblem("The tool on this PC had not finished after {:g} hours: it was stopped.".format(most / 3600))
            answer = self._answer(job_ref)
            if on_change is not None:
                on_change(answer)
            if answer["status"] in ("succeeded", "failed", "cancelled"):
                return answer

    async def fetch_output(self, key, job_ref, n, target, outputs=None):
        job = JOBS.get(job_ref)
        if job is None or n >= len(job["outputs"]):
            raise ProviderProblem("The tool's result is gone.")
        out = job["outputs"][n]
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(job["folder"]) / out["name"], target)
        return out

    async def run_now(self, model, input, label="clean voice"):
        """Run one tool and wait for it, outside the queue (the queue's own steps: taking the voice out of a lip sync's
        voice track first). Returns {output name: path}; the files stay in the work folder for KEEP_DAYS."""
        sent = {}
        for name, value in input.items():
            sent[name] = await self.upload("", path=value) if name in ("audio", "video") else value
        started = await self.start("", model, sent, {}, "{}_{}".format(label.replace(" ", "_"), uuid.uuid4().hex))
        answer = await self.follow("", started["id"])
        if answer["status"] != "succeeded":
            raise ProviderProblem((answer.get("error") or {}).get("message") or "The tool on this PC did not finish.")
        folder = Path(JOBS[started["id"]]["folder"])
        return {o["name"]: str(folder / o["name"]) for o in answer["outputs"]}
