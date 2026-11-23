"""The generation queue, shared by all users, with live progress. Each waiting job of a model goes to a key the
router picks (providers/router.py) as soon as one is free: a Scene provider's (Studio_automation) or On this PC's.
Edits and motion graphics, which are made on this machine, are jobs too and have a lane of their own (see edits.py).

A job is either one call to a provider, or a chain: several clips where each one starts on the last frame of the clip
before it, joined into one video at the end (_run_provider_chain).
"""

import asyncio
import inspect
import contextvars
import copy
import json
import mimetypes
import re
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from . import core, edits, errors, guardrails, health, langfuse_trace, media, memory, moderation, motion, placement, sequence, sharing, traces
from .comfy import workflows
from .agent import AgentError
from .providers import base as provider_base, v1 as provider_v1, workflows as provider_workflows
from .providers import router as provider_router
from .providers.router import NoProvider
from . import outputs as outputs_mod
from .db import as_everyone, offload
from .references import REFERENCES, keep_reference, kept_reference

VIDEO_TYPES = {".mp4", ".webm", ".mov", ".mkv", ".gif"}
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_TYPES = {".mp3", ".flac", ".wav", ".opus", ".ogg", ".m4a"}
TEXT_TYPES = {".json", ".srt", ".txt"}   # a transcript, a list of times: filed as "text"
STYLED_ENGINE = "gemini"   # the speech model's only voices that take style_instructions
STYLE_REFUSED = "style_instructions_not_supported"   # the provider's code when a voice takes none
NO_VOICE = ("No voice is chosen for this voiceover, and the provider has no voice to pick from. Pick one in its "
            "Voice id setting (the agent's voices tool lists them), or set a default voice on the generation server.")
# A clip the provider's content filter flags (often passing on another try: Seedance 2.5 with sound and spoken lines,
# 22 Nov 2026): the tries after the first, in order. "same" as it was, "no_sound" without its sound (its lines then go
# on as a voiceover), "stand_in" on another model (FILTER_STAND_IN). After the last the job fails and says why.
FILTER_LADDER = ("same", "same", "no_sound", "stand_in")
FILTER_STAND_IN = {"seedance_2_5": ("seedance_2_0", "kling_4.0"), "seedance_2_5_flash": ("seedance_2_0", "kling_4.0"),
                   "seedance_2_0": ("kling_4.0",), "seedance_2_0_fast": ("seedance_2_0", "kling_4.0"),
                   "seedance_2_0_mini": ("seedance_2_0", "kling_4.0")}
FLAGGED = ("flagged by the content filter", "content_filter", "content filter")
VOICES_LOOKED_AT = 20   # this module's latest voiceovers looked at for the voice they were made with
CLIP_BREAK = re.compile(r"^\s*-{3,}\s*$", re.M)  # a line of dashes separates per-clip prompts
JUST_FINISHED = 300  # seconds a finished job stays in its owner's list whatever came after it (the canvas waits for its result)
PROVIDER = "The provider"
# What the provider answers when it is only not ready yet for a job (the reference pictures just sent still being
# registered): the job is tried again a little later (_not_ready), not failed.
NOT_READY = ("references_registering",)
NOT_READY_WAIT = 20     # seconds before it is queued again
NOT_READY_TRIES = 3   # times a job the provider was not ready for is queued again before it fails
# A provider job cancelled once it was sent: the studio stops following it, the provider does not stop.
PROVIDER_CANCELLED = ("Cancelled. The provider has no cancel: if the clip had started there, it still finishes it and "
                      "charges for it. Your studio credits came back.")
LOOK_AHEAD = 200     # waiting jobs the queue looks at each time (those past it wait for a later look)
RENDER_MOST = 4 * 3600   # seconds one call to a provider may take, waiting in its own queue too: past it, it is given up
# A job of a workflow no provider offers as a model: one of ComfyUI's, which the studio no longer uses.
NOT_A_MODEL = ("{} was a ComfyUI workflow, which the studio no longer uses: make it again with one of the models "
               "(Create, or ask the agent).")
# A provider job cancelled before it reached the provider (the provider said it is not charged).
PROVIDER_CANCELLED_FREE = "Cancelled before the provider made it: nothing was charged there, and your studio credits came back."
OUTPUT_KINDS = {"video": "video", "image": "image", "audio": "audio", "text": "text"}
# File endings of the outputs a provider may send with no name, by their mime (mimetypes knows no subtitles).
OUTPUT_SUFFIXES = {"application/json": ".json", "application/x-subrip": ".srt", "text/srt": ".srt", "text/plain": ".txt",
                   "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "video/mp4": ".mp4"}
CLEAN_VOICE = "separate_voice"   # the model that takes a voice out of music and effects (On this PC's, Studio_automation's)
NO_CLEAN_VOICE = ("The voice can't be taken out of the music: voice separation is not set up on this PC. Make it without "
                  "that, or set it up (docs/servers.md).")


# The plan and step being queued now (plans.py): JobManager.add writes them into the job's own row.
QUEUEING = contextvars.ContextVar("queueing", default=None)

# Where a job stands in the queue: a plan's jobs where the plan was approved, in the order of its steps, so a plan whose
# later shots are queued only once the shot they start on is made keeps its place ahead of what was asked for after it
# (another module's video ran between them). Every other job where it was asked for. Ahead of both: what was put first.
QUEUE_AT = "COALESCE((SELECT approved FROM agent_plans p WHERE p.id = jobs.plan_id), jobs.created)"
QUEUE_ORDER = "priority DESC, {}, plan_step, created".format(QUEUE_AT)


def _suffix_of_output(out):
    """An output's file ending: its name's, else its mime's (without its parameters: "application/json; charset=utf-8")."""
    suffix = Path(str(out.get("name") or "")).suffix
    if suffix:
        return suffix.lower()
    mime = str(out.get("mime") or "").split(";")[0].strip().lower()
    return OUTPUT_SUFFIXES.get(mime) or mimetypes.guess_extension(mime) or ""


def _label_of_output(out, suffix):
    """What one of a job's several files is, for its name in the library: its name's stem (voice, music_fx), except
    subtitles, which share the transcript's stem (transcript.json, transcript.srt) and are called "subtitles"."""
    if suffix == ".srt":
        return "subtitles"
    return Path(str(out.get("name") or "")).stem[:40] or str(out.get("type") or "")[:40]


def _kind_of_output(out, suffix):
    """What a provider's output is: by its "type" when it says, else by its file's ending."""
    kind = OUTPUT_KINDS.get(str(out.get("type") or ""), "")
    if kind:
        return kind
    return "video" if suffix in VIDEO_TYPES else "image" if suffix in IMAGE_TYPES else "audio" if suffix in AUDIO_TYPES else "text"

def flagged(error):
    """Whether a provider's refusal is its content filter's (a flag on what was made, not on the request)."""
    said = "{} {}".format(getattr(error, "code", "") or "", error).lower()
    return any(words in said for words in FLAGGED)


def made_how(sound_off, model):
    """What a clip made past the content filter gave up, in words kept with it ("" for nothing)."""
    parts = []
    if sound_off:
        parts.append("made without its sound after the content filter flagged it: lay its lines on as a voiceover "
                     "(and lip sync them if a face speaks)")
    if model:
        parts.append("made on {} after the content filter flagged it on its own model".format(model))
    return "; ".join(parts)


def filter_gave_up(name, rung, sound_off, model):
    """Why a clip the content filter kept flagging failed, for the user: what was tried, and what to change."""
    tried = ["{} tries as it was".format(1 + sum(1 for r in FILTER_LADDER[:rung] if r == "same"))]
    if sound_off:
        tried.append("one without sound")
    if model:
        tried.append("one on {}".format(model))
    return ("The provider's content filter flagged “{}” on every try ({}). Change what happens in it (an animal in "
            "distress, a hit, a fall, a real person's or a brand's name), then make it again.").format(
        name or "this clip", ", ".join(tried))


class Cancelled(Exception):
    pass


class JobError(Exception):
    """A job that can't be made, in words for its owner."""


class Closed(HTTPException):
    """A new job refused while the studio is under maintenance (health.maintenance). It is an HTTP answer (503), so a
    route that adds a job says it as it says any refusal, and so does the agent, which reads its steps' refusals."""

    def __init__(self, text):
        super().__init__(503, text)


class JobManager:
    def __init__(self, db, catalog, credits, outputs, notify, tmp_dir, node_path="", assets_dir=None):
        self.db = db
        self.assets_dir = Path(assets_dir) if assets_dir else None   # where a result kept for reuse is copied as an asset
        self.node_path = node_path      # the Node.js program that renders motion graphics
        self.storage = None       # where the input files are kept (references.keep_reference; main.py sets it)
        self.working = set()      # the jobs of models running now
        self.catalog = catalog
        self.credits = credits
        self.outputs = outputs          # where each user's finished work goes
        self.tmp_dir = Path(tmp_dir)    # working files of chained videos and clean voices
        self.notify = notify      # notify(user_id, library_changed=False)
        self.live = {}            # job id -> progress of the running job (not stored)
        self.agent = None         # the agent's model, which writes the captions some image models need (main.py sets it)
        self.langfuse = None      # each finished job, as a span of its turn's trace (langfuse_trace.Sender; main.py sets it)
        self.finished = []        # functions(job, status) told when a job ends (aftercare.install: the agent checks its shots)
        self.ahead = None         # () -> the queue place of a plan's next step being queued now, or None (plans.py)
        self.wake = asyncio.Event()
        self.woken = 0   # wakes counted: a worker that read the count before it looked misses none (_idle)
        try:   # the loop the workers wait on: add() and pause() may be called from a database thread (db.offload)
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None
        # Which provider and key make each job (providers/router.py; main.py sets it).
        self.router = None
        # A job that was running when the app stopped can't be picked up again. Waiting jobs stay queued.
        for job in db.all("SELECT id, user_id, cost FROM jobs WHERE status = 'running'"):
            db.run("UPDATE jobs SET status = 'failed', error = ?, finished = ? WHERE id = ?",
                   ("The app was restarted before this job finished.", time.time(), job["id"]))
            self._refund(job)

    # ------------------------------------------------------------ public

    def snapshot(self, user_id):
        now = time.time()
        # A job waits only behind the jobs of its own lane: renders behind renders, edits behind edits.
        waiting, busy = {True: [], False: []}, {True: 0, False: 0}
        servers = 1   # a place in the queue counts the jobs ahead, whatever runs them
        with as_everyone():   # where the user's jobs stand in the queue depends on everyone's
            queue = self.db.all("SELECT id, workflow, status FROM jobs WHERE status IN ('queued', 'running') ORDER BY " + QUEUE_ORDER)
        for r in queue:
            if r["status"] == "running":
                busy[edits.is_edit(r["workflow"])] += 1
            else:
                waiting[edits.is_edit(r["workflow"])].append(r["id"])
        jobs = []
        # The latest 40, and however many more are waiting, running or just finished: the canvas holds each one's place
        # until what it made comes in, so a job left off this list would see its result land at the bottom instead.
        # (Three lookups joined, each on an index of its own: one OR over them read every job of the user.)
        for row in self.db.all(
                "SELECT * FROM jobs WHERE id IN ("
                "SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 AND status IN ('queued', 'running') "
                "UNION SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 AND finished > ? "
                "UNION (SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 ORDER BY created DESC LIMIT 40)) "
                "ORDER BY created DESC", (user_id, user_id, now - JUST_FINISHED, user_id)):
            live = self.live.get(row["id"], {})
            row["settings"] = json.loads(row["settings"])
            lane = edits.is_edit(row["workflow"])
            row.update(step=live.get("step", 0), steps=live.get("steps", 0), node=live.get("node", ""),
                       clip=live.get("clip", 0), clips=live.get("clips", 0), eta_seconds=self._eta(row, live, now),
                       position=(waiting[lane].index(row["id"]) + busy[lane]) // (1 if lane else servers) + 1
                       if row["id"] in waiting[lane] else None)
            if row["status"] == "failed":   # why, in words its owner reads (the canvas shows a failed job)
                row["reason"] = errors.for_user(row["error"])
            del row["hidden"], row["user_id"]
            jobs.append(row)
        return jobs

    def add(self, user_id, name, workflow_id, settings, summary, est_seconds, cost=0, project_id=None, seconds=None,
            during_maintenance=False):
        """`cost` has already been taken from the user: it is held for the job until it finishes or is refunded.
        `seconds` is the length of the result that was asked for, which is what the price is based on.
        Under maintenance it is refused, and what was taken for it is given back, unless it is `during_maintenance`
        (an admin's test run, which is what maintenance is for)."""
        closed = health.maintenance(self.db)
        if closed and not during_maintenance:
            if cost:
                self.credits.add(user_id, cost, "refund", note="Maintenance")
            raise Closed(closed["text"])
        stop = guardrails.stop_problem(self.db)   # the studio's stop (guardrails.py): no new work
        if stop:
            if cost:
                self.credits.add(user_id, cost, "refund", note="Studio stopped")
            raise HTTPException(503, stop)
        if moderation.refusal(self.db, user_id, settings):   # a prompt with words the studio does not make
            if cost:
                self.credits.add(user_id, cost, "refund", note="Prompt refused")
            raise HTTPException(400, "This prompt can't be made here. Change its words and try again.")
        # The turn it belongs to, for Langfuse: the one the agent planned it in (a plan's step carries it to its
        # approval), else the one queueing it now.
        settings["turn"] = langfuse_trace.job_turn(settings) or traces.mark()
        shot = settings.get("shot") if isinstance(settings.get("shot"), dict) else {}
        if self.langfuse is not None and isinstance(settings.get("parent"), int) and int(shot.get("take") or 1) >= 2:
            # Langfuse: a shot made again (a retake after a failed review, or another take the user asked for)
            self.langfuse.item_score(settings["parent"], "retaken", 1, "retaken-{}".format(settings["parent"]))
        job_id = uuid.uuid4().hex[:12]
        plan, step = QUEUEING.get() or (None, None)   # a plan's step: recorded in the same write that queues it
        self.db.run(
            "INSERT INTO jobs (id, user_id, name, workflow, kind, settings, summary, status, est_seconds, cost, "
            "credits_required, credits_reserved, seconds_requested, project_id, run, created, plan_id, plan_step) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, user_id, name, workflow_id, workflow_id.split("/", 1)[0], json.dumps(settings), summary,
             est_seconds, cost, cost, cost, seconds, project_id, str(settings.get("run_of") or settings.get("run") or "")[:32], time.time(),
             plan, step))
        self._wake()
        self.notify(user_id)
        return job_id

    def remove(self, user_id, job_id):
        """Cancel a waiting or running job, or take a finished one off the list."""
        job = self.db.one("SELECT id, user_id, status, cost FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id))
        if job is None:
            return False
        if job["status"] == "queued":
            self.db.run("UPDATE jobs SET status = 'cancelled', finished = ? WHERE id = ?", (time.time(), job_id))
            self._refund(job)
        elif job["status"] == "running":
            self.live.setdefault(job_id, {})["cancel"] = True  # the worker stops following it on its next look
        else:
            self.db.run("UPDATE jobs SET hidden = 1 WHERE id = ?", (job_id,))
        self.notify(user_id)
        return True

    async def run_forever(self, local=False):
        """Take the waiting jobs of one lane. There are two lanes, each with its own worker: the models' jobs, each given
        a provider key as soon as one is free (_place_renders), and edits (`local`), one at a time, oldest first, which
        are made on this machine and so never wait behind a model's job."""
        if not local:
            return await self._place_renders()
        while True:
            seen = self.woken   # before the look below: a wake after it is never lost
            job = await self.db.aone("SELECT * FROM jobs WHERE status = 'queued' AND workflow LIKE 'edit/%' ORDER BY {} LIMIT 1".format(
                QUEUE_ORDER))
            if job is None:
                await self._idle(seen)
                continue
            await self._start(job, None, local=True)

    async def _place_renders(self):
        """The models' worker. Each look goes through the waiting jobs in queue order and starts every one that a key
        which can make it has room for (the router's pick: the least busy). A job that has to wait (every key that
        could is busy, resting or over its cap) does not hold up the ones behind it that other keys can make; when its
        keys free up it is first again, as it is ahead of them. A job no key could ever make fails at once, saying why."""
        while True:
            seen = self.woken   # before the looks below: a wake after them is never lost
            # An admin can pause the models' jobs (while a provider is being changed, say). Edits keep running.
            if await offload(self.paused):
                await self._idle(seen, 5)
                continue
            waiting = await self.db.aall(
                "SELECT *, {} AS queue_at FROM jobs WHERE status = 'queued' AND workflow NOT LIKE 'edit/%' ORDER BY {} LIMIT {}".format(
                    QUEUE_AT, QUEUE_ORDER, LOOK_AHEAD))
            # A plan ahead of them is queueing its next shot (the one before it was just made): that shot goes first, so
            # what was asked for after the plan waits the moment it takes. What was put first (priority) does not.
            held = self.ahead() if self.ahead and waiting else None
            started, soon = 0, None
            for job in waiting:
                if held is not None and held < job.pop("queue_at") and not job["priority"]:
                    soon = 1
                    continue
                job.pop("queue_at", None)
                server, problem = await self._place(job)
                if problem:   # nothing could ever make it: it fails now, its credits given back
                    await self._start(job, None, problem=problem)
                    started += 1
                elif server is not None:
                    await self._start(job, server)
                    started += 1
            if started:   # what started may have freed a place for another look
                continue
            await self._idle(seen, soon)

    async def _not_ready(self, job, error):
        """The provider refused to start a job only because it was not ready yet (the reference pictures just sent were
        still being registered): nothing was made or charged. The job is queued again NOT_READY_WAIT seconds later, its
        credits still held, at most NOT_READY_TRIES times, instead of failing (a plan's next shot waits on it). Returns
        whether it was."""
        said = str(error or "").lower()
        if not any(word in said for word in NOT_READY):
            return False
        settings = job["settings"] if isinstance(job["settings"], dict) else {}
        tries = int(settings.get("not_ready_tries") or 0)
        if tries >= NOT_READY_TRIES:
            return False
        settings = dict(settings, not_ready_tries=tries + 1)
        dropped = await self._drop_frames(job, settings) if tries >= 1 else ""
        print("Job {}: the provider was not ready ({}); queued again in {} s ({} of {}){}.".format(
            job["id"], error, NOT_READY_WAIT, tries + 1, NOT_READY_TRIES, " " + dropped if dropped else ""))

        async def later():
            await asyncio.sleep(NOT_READY_WAIT)
            await self.db.arun("UPDATE jobs SET status = 'queued', started = NULL, error = '', settings = ?, "
                               "priority = CASE WHEN priority < 50 THEN 50 ELSE priority END WHERE id = ? AND status = 'running'",
                               (json.dumps(settings), job["id"]))
            self.notify(job["user_id"])
            self._wake()
        task = asyncio.ensure_future(later())   # its slot is free meanwhile; the job shows as still being made
        self.waiting_again = getattr(self, "waiting_again", set())
        self.waiting_again.add(task)   # held until done: a task nobody holds may be collected half-way
        task.add_done_callback(self.waiting_again.discard)
        return True

    async def _drop_frames(self, job, settings):
        """A clip given a first or last frame and reference pictures that the provider will not start ("references
        registering", again and again: Seedance with a frame and references) is sent with its references only, the way
        such shots are made (its prompt cites them). Changes `settings`; returns what was done, in words, or ""."""
        try:
            schema = workflows.describe(await self.catalog.load(job["workflow"]))
        except workflows.WorkflowError:
            return ""
        refs = {slot: given for slot, given in (settings.get("refs") or {}).items() if given}
        slots = schema.get("slots") or {}
        frames = {slots.get("first_frame"), slots.get("last_frame")} & set(refs)
        pictures = {r["id"] for r in schema["refs"] if r["kind"] == "image"} - frames
        if not frames or not set(refs) & pictures:
            return ""
        for slot in frames:
            refs.pop(slot)
        settings["refs"] = refs
        settings["frames_dropped"] = sorted(frames)
        return "without its first or last frame, from its references only"

    async def _place(self, job):
        """Where one waiting job goes now: (the key the router took for it, or None while it waits; why nothing could
        ever make it, or "")."""
        if self.router is None or not provider_workflows.is_provider_id(job["workflow"]):
            return None, NOT_A_MODEL.format(job["workflow"])
        return await self._place_provider(job)

    async def _place_provider(self, job):
        """A provider's model: the key the router picks (providers/router.py), taken for this job at once. It waits
        while every key that could is busy, resting or over its cap; it fails now when none ever could."""
        model = provider_workflows.model_id_of(job["workflow"])
        choice, problem = await offload(self.router.pick, model)
        if problem:
            return None, problem
        if choice is None:
            return None, ""
        self.router.take(choice, job["id"])
        return {"name": choice["provider"]["name"], "choice": choice}, ""

    async def _start(self, job, server, local=False, problem=""):
        """Start one job taken from the queue: an edit here (`local`, waited for), a model's job on the key the router
        took (`server`, on its own while the worker places the next), or one nothing can make (`problem`), which fails
        at once."""
        job["settings"] = json.loads(job["settings"])
        job["started"] = time.time()
        self.live[job["id"]] = {"step": 0, "steps": 0, "titles": {}}
        if problem:
            job["unplaced"], name = problem, ""
        elif server is not None:
            name = server["name"]   # the provider, as Servers & APIs → Providers names it
            job["choice"] = server["choice"]   # the key the router took for it
        else:   # an edit: the machine it runs on, as the Pricing section names it (what it draws is costed by that name)
            found = await self.db.aone("SELECT name FROM servers WHERE renders = 0 AND active = 1 ORDER BY id LIMIT 1")
            name = found["name"] if found else ""
        await self.db.arun("UPDATE jobs SET status = 'running', started = ?, server = ? WHERE id = ?",
                    (job["started"], name, job["id"]))
        job["server"] = name
        await offload(self._notify_all_waiting, job["user_id"])
        if local:
            await self._work(job, local)
            return
        task = asyncio.ensure_future(self._work(job, local))
        self.working.add(task)
        task.add_done_callback(self.working.discard)

    async def _work(self, job, local):
        """Run one job that was taken from the queue, and record how it ended."""
        try:
            await self._finish(job, local)
        finally:
            if job.get("choice") is not None and self.router is not None:   # the provider key it held
                self.router.release(job["choice"], job["id"])
            self._woke()   # its slot is free again

    async def _finish(self, job, local):
        status, error = "done", None
        try:
            if job.get("unplaced"):
                raise JobError(job["unplaced"])
            if not local and isinstance(job["settings"].get("caption"), dict):
                await self._captions(job)
            await self._run(job)
        except Cancelled:
            status = "cancelled"
            live = self.live.get(job["id"]) or {}
            if live.get("provider"):
                error = PROVIDER_CANCELLED_FREE if live.get("charged") is False else PROVIDER_CANCELLED
        except (JobError, workflows.WorkflowError, media.MediaError, motion.MotionError, sequence.SequenceError) as e:
            status, error = "failed", str(e)
        except NoProvider as e:   # no key could ever make it: said as the router says it
            status, error = "failed", str(e)
        except provider_base.ProviderError as e:   # the provider's own words (a test key: "Test mode: would cost …")
            status, error = "failed", "{}: {}".format(PROVIDER, str(e).rstrip(".") + ".")
        except Exception as e:  # keep the queue alive whatever one job does
            status, error = "failed", "{}: {}".format(type(e).__name__, e)
        self.live.pop(job["id"], None)
        if status == "failed" and await self._not_ready(job, error):
            return   # the provider was not ready yet (its references still registering): queued again in a moment
        # Its credits are settled before anyone can see that it ended (the list of jobs, a plan that waits on it): a
        # job shown done, failed or cancelled has nothing still held for it.
        if status == "done":
            await self.db.arun("UPDATE jobs SET status = ?, error = ?, finished = ?, credits_reserved = 0, credits_consumed = cost, "
                        "output_size = (SELECT SUM(size) FROM generations WHERE job_id = jobs.id) WHERE id = ?",
                        (status, error, time.time(), job["id"]))
        else:
            await offload(self._refund, job)
            await self.db.arun("UPDATE jobs SET status = ?, error = ?, finished = ? WHERE id = ?",
                        (status, error, time.time(), job["id"]))
        await offload(self._traced, job, status, error)
        self.notify(job["user_id"], library_changed=status == "done")
        if status == "done" and job.get("project_id"):   # the others in a shared project see it on their canvas too
            for person in await offload(sharing.people_of, self.db, job["project_id"]):
                if person != job["user_id"]:
                    self.notify(person, library_changed=True)
        await offload(self._notify_all_waiting, None)
        for told in self.finished:   # what is done once a job ends must never stop the queue
            try:
                if inspect.iscoroutinefunction(told):
                    await told(job, status)
                else:
                    told(job, status)
            except Exception as problem:
                print("A finished job's follow-up failed: {}".format(problem))

    def _wake(self):
        """Wake the workers: on their loop, wherever this is called from."""
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if self.loop is not None and here is not self.loop:
            self.loop.call_soon_threadsafe(self._woke)
        else:
            self._woke()

    def _woke(self):
        self.woken += 1
        self.wake.set()

    async def _idle(self, seen, seconds=None):
        """Wait until a wake after the count `seen` (self.woken, read before the worker looked at the queue), or
        `seconds`. The event is cleared only while nothing was woken since then: a job added between the worker's look
        and this wait, or the other lane's clear, can no longer be lost. (It was: with no job found the worker waited
        with no time limit, and a job added in that gap stayed queued until another one came.)"""
        loop = asyncio.get_running_loop()
        until = None if seconds is None else loop.time() + seconds
        while self.woken == seen:
            self.wake.clear()
            left = None if until is None else until - loop.time()
            if left is not None and left <= 0:
                return
            try:
                await asyncio.wait_for(self.wake.wait(), left)
            except asyncio.TimeoutError:
                return

    def paused(self):
        return self.db.setting("queue_paused", "0") == "1" or guardrails.stopped(self.db) is not None

    def pause(self, paused):
        self.db.set_setting("queue_paused", "1" if paused else "0")
        self._wake()
        self._notify_all_waiting(None)

    def to_front(self, job_id):
        """Put a waiting job ahead of every other waiting job."""
        with as_everyone():
            top = self.db.one("SELECT MAX(priority) n FROM jobs WHERE status = 'queued'")["n"] or 0
            self.db.run("UPDATE jobs SET priority = ? WHERE id = ? AND status = 'queued'", (top + 1, job_id))
        self._notify_all_waiting(None)

    def _traced(self, job, status, error):
        """The job, finished, as a span of its turn's trace in Langfuse: how long it waited and ran, where, and its price.
        Nothing here may stop the queue."""
        if self.langfuse is None:
            return
        try:
            turn = langfuse_trace.job_turn(job["settings"]) or {"run": "", "name": "Render"}
            options = job["settings"].get("options") if isinstance(job["settings"].get("options"), dict) else {}
            ended = time.time()
            self.langfuse.span(
                "{} {}".format("edit" if edits.is_edit(job["workflow"]) else "render", job["workflow"]), job["started"], ended,
                turn["run"], {"name": turn["name"], "tags": [job["kind"]],
                              "metadata": {"project": job.get("project_id"), "quality": options.get("quality")}},
                {"workflow": job["workflow"], "kind": job["kind"], "status": status, "server": job.get("server") or "",
                 "server_url": job.get("server_url") or "", "queue_seconds": round(job["started"] - job["created"], 1),
                 "render_seconds": round(ended - job["started"], 1), "credits": job["cost"] if status == "done" else 0,
                 "job": job["id"],
                 # a provider's model: its provider, model, key label and the provider's request id (never the key)
                 **({"provider": {k: v for k, v in job["provider_note"].items() if k != "key_id"}} if job.get("provider_note") else {})},
                user=job["user_id"], error=error if status == "failed" else None, fallback=turn["name"])
        except Exception as problem:   # Langfuse is a help: the job is done all the same
            print("The job could not be readied for Langfuse: {}".format(problem))

    def _refund(self, job):
        """Give back what was held for a job that did not finish."""
        self.credits.add(job["user_id"], job["cost"], "refund", job["id"])
        self.db.run("UPDATE jobs SET credits_reserved = 0, credits_refunded = cost WHERE id = ?", (job["id"],))

    # ------------------------------------------------------------ one job

    async def _run_edit(self, job):
        """An edit or a motion graphic, made on this machine. It reports no steps; a cancel stops it within a second."""
        live = self.live[job["id"]]
        work = asyncio.ensure_future(edits.run(job, await offload(self.outputs.folder, job["user_id"]), self.db, self.node_path, self.tmp_dir))
        while not work.done():
            await asyncio.wait([work], timeout=1)
            if live.get("cancel") and not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
                raise Cancelled()
        made = work.result()
        if made[0][2]["duration"]:
            job["summary"] = "{} · {:.0f} s".format(job["summary"], made[0][2]["duration"])
            await self.db.arun("UPDATE jobs SET summary = ? WHERE id = ?", (job["summary"], job["id"]))
        for target, kind, ctx in made:
            # An op that makes several files names each (a keyframe's time) and may keep each in the run (save_to).
            name, keep_path, keep = ctx.pop("_name", None), ctx.pop("_keep_at", None), ctx.pop("_keep", None)
            item_id = await offload(self._record, job, kind, target, ctx, name)
            if keep_path and item_id:
                await offload(edits.keep_at, self.db, job, item_id, keep_path, keep)

    async def _captions(self, job):
        """Write the structured caption this job needs (an image model such as Ideogram is trained on them), and those of
        every render waiting with one, in one go: the agent's model is loaded once for them all, and the renders after
        it run one after another with the image model loaded. A caption that cannot be written fails its own job only."""
        live = self.live[job["id"]]
        with as_everyone():
            rows = await self.db.aall("SELECT id, user_id, settings FROM jobs WHERE status = 'queued' AND settings::text LIKE ?", ('%"caption": {%',))
        todo = [(job["id"], job["settings"])] + [(r["id"], json.loads(r["settings"])) for r in rows if r["id"] != job["id"]]
        live["node"] = "Writing the caption…"
        self.notify(job["user_id"])
        if self.agent is None:
            raise JobError("This model needs a structured caption, which the agent writes, and there is no agent here.")
        for job_id, settings in todo:
            rule = settings.get("caption")
            if not isinstance(rule, dict):
                continue
            try:
                caption = await self.agent.caption(rule["template"], str(settings.get("prompt") or ""), str(rule.get("ratio") or "auto"))
            except AgentError as error:
                if job_id == job["id"]:
                    raise JobError("This model needs a structured caption, which the agent writes from your prompt. {}".format(error))
                continue   # that job tries again when its turn comes
            settings.setdefault("values", {})[rule["prompt"]] = caption
            settings.pop("caption", None)
            with as_everyone():
                await self.db.arun("UPDATE jobs SET settings = ? WHERE id = ?", (json.dumps(settings), job_id))
        live["node"] = ""

    async def _run(self, job):
        if edits.is_edit(job["workflow"]):
            return await self._run_edit(job)
        if job.get("choice") is None:
            raise JobError(NOT_A_MODEL.format(job["workflow"]))
        return await self._run_provider(job, self.live[job["id"]])

    async def _run_provider(self, job, live):
        """A provider's model (providers/workflows.py), made by its provider over the Scene Provider API v1 (or by the
        tools on this PC, which answer the same way): the graph is built as any workflow's and its provider node is the
        job's `input`; its files are uploaded, the job started with an Idempotency-Key of this job (a retry never pays
        twice), followed until it ends, and its outputs fetched and filed. The router fails over to another key or
        provider only before the job has started there: once it started, a problem ends this job (and its credits come
        back). A long video of several clips is a chain (_run_provider_chain)."""
        wf = await self.catalog.load(job["workflow"])
        settings = await self._clean_voice_here(job, live, wf)
        clips = workflows.clip_count(workflows.describe(wf), settings)
        live["provider"] = True
        if clips > 1:
            await self._run_provider_chain(job, live, wf, settings, clips)
            return
        (adapter, choice, started, answer), ctx = await self._provider_clip(job, live, wf, settings)
        outputs = [o for o in answer.get("outputs") or [] if isinstance(o, dict)]
        live["node"] = "Fetching the result"
        self.notify(job["user_id"])
        folder, stem = await offload(self._target, job)
        saved = 0
        for n, out in enumerate(outputs):
            suffix = _suffix_of_output(out)
            kind = _kind_of_output(out, suffix)
            target = folder / "{}{}{}".format(stem, "_{}".format(saved + 1) if saved else "", suffix)
            await adapter.fetch_output(choice["secret"], started["id"], n, target, outputs)
            found = await media.probe(target) if kind != "text" else {}
            made = dict(ctx)
            if kind == "audio":
                made["duration"] = round(found.get("seconds") or 0, 1)
            elif kind in ("image", "video") and found.get("width"):
                made.update(width=found["width"], height=found["height"])
            if kind == "video":
                made["fps"] = await media.frame_rate(target)
            # Several files of one job (a voice and the music, a transcript and its subtitles): each named by what it is
            label = _label_of_output(out, suffix) if len(outputs) > 1 else ""
            await offload(self._record, job, kind, target, dict(made, output=label) if label else made,
                          name="{} · {}".format(job["name"], label)[:120] if label else None)
            saved += 1
        if not saved:
            raise provider_base.ProviderProblem("The provider finished but sent no file.")

    async def _provider_clip(self, job, live, wf, settings, clip=None):
        """One call to the provider for this job (one clip of a chain when `clip` is its number): started on the key the
        router picks (the job's own while it holds one), followed until it ended well. Returns ((adapter, Choice,
        started, last answer), context). The job's provider note says what ran it; a chain's lists every clip.
        Only Gemini voices take style instructions: a voice the provider refuses them for is asked once more without
        them (the [bracketed] cues in the text still direct the delivery).
        A clip the provider's content filter flags goes up the ladder (FILTER_LADDER): the same twice more (it often
        passes), then without its sound, then on a stand-in model (FILTER_STAND_IN); after that it fails and says so."""
        plain, rung, sound_off, model = False, 0, False, None
        while True:
            try:
                found = await self._provider_clip_once(job, live, wf, settings, clip, plain=plain, rung=rung,
                                                       sound_off=sound_off, model=model)
            except (provider_base.ProviderError, provider_base.RequestProblem) as error:
                if not plain and (STYLE_REFUSED in str(error) or getattr(error, "code", "") == STYLE_REFUSED):
                    print("Job {}: the voice takes no style instructions; asked again without them.".format(job["id"]))
                    plain = True
                    continue
                if not flagged(error):
                    raise
                if live.get("cancel"):
                    raise Cancelled()
                step = await self._next_rung(job, wf, rung, sound_off, model, settings)
                if step is None:
                    raise provider_base.RequestProblem(filter_gave_up(job.get("name"), rung, sound_off, model)) from error
                rung, sound_off, model, said = step
                print("Job {}{}: flagged by the content filter; {}.".format(job["id"], " clip {}".format(clip) if clip else "", said))
                live["node"] = "Flagged by the content filter: {}".format(said)
                self.notify(job["user_id"])
                continue
            if sound_off or model:   # what was given up to get it made, kept with it for the agent and the user
                found[1]["content_filter"] = made_how(sound_off, model)
            return found

    async def _next_rung(self, job, wf, rung, sound_off, model, settings):
        """The next try after a content filter's flag: (rung, sound_off, model, what it does in words), or None when
        the ladder is done. A rung that changes nothing (no sound to turn off, no stand-in offered) is passed over."""
        provider = wf["profile"]["provider"]
        while True:
            rung += 1
            if rung > len(FILTER_LADDER):
                return None
            what = FILTER_LADDER[rung - 1]
            if what == "same":
                return rung, sound_off, model, "trying again as it was ({} of {})".format(rung, len(FILTER_LADDER))
            if what == "no_sound":
                graph, _ = workflows.build_prompt(wf, dict(settings, clips=1))
                if provider_workflows.provider_input(wf, graph).get("sound") is True:
                    return rung, True, model, "trying again without sound (the lines can be laid on as a voiceover)"
                continue
            if what == "stand_in":
                stand_in = await self._stand_in(provider["model"], provider.get("capability"))
                if stand_in:
                    return rung, sound_off, stand_in, "trying on {} instead".format(stand_in)
                continue

    async def _inputs_for(self, model_id, capability, inputs):
        """The job's inputs as a stand-in model takes them: only the settings it has, a choice only when it offers it
        (else its default), and no more reference files than it takes."""
        other = await self.catalog.load(provider_workflows.workflow_id(capability, model_id))
        node = other["nodes"][provider_workflows.PROVIDER_NODE]["inputs"]
        names = {name.partition("#")[0] for name in node}
        refs = (other["profile"].get("refs") or {})
        if refs.get("target_input"):
            names.add(refs["target_input"].partition("#")[0])
        offered = {o["id"]: {c["id"] for c in o["choices"]} for o in other["profile"].get("options") or []}
        names |= set(offered)   # a choice (sound, shape, resolution) is written into the node by a rule, not linked
        most = refs.get("max")
        kept = {}
        for name, value in inputs.items():
            if name not in names:
                continue
            if name in offered and provider_workflows._choice_id(value) not in offered[name]:
                continue
            if isinstance(value, list) and isinstance(most, int) and refs.get("target_input", "").startswith(name + "#"):
                value = value[:most]
            kept[name] = value
        return kept

    async def _stand_in(self, model_id, capability):
        """The first of FILTER_STAND_IN's models for this one that a key offers now, or None."""
        for other in FILTER_STAND_IN.get(model_id, ()):
            wid = provider_workflows.workflow_id(capability, other)
            try:
                if wid and await self.catalog.load(wid):
                    return other
            except Exception:   # not offered now: the next one
                continue
        return None

    def _voice_before(self, job, wf):
        """The voice the latest voiceover of this job's module (its user's, on the same model) was made with, or "".
        Each earlier job's settings are built again as they were sent, so it is the voice the provider was given."""
        if not job.get("project_id"):
            return ""
        with as_everyone():
            rows = self.db.all("SELECT settings FROM jobs WHERE user_id = ? AND project_id = ? AND workflow = ? AND id <> ? "
                               "AND status = 'done' ORDER BY created DESC LIMIT ?",
                               (job["user_id"], job["project_id"], job["workflow"], job["id"], VOICES_LOOKED_AT))
        for row in rows:
            try:
                earlier = json.loads(row["settings"]) if isinstance(row["settings"], str) else row["settings"]
                graph, _ = workflows.build_prompt(wf, dict(earlier or {}, clips=1))
                voice = str(provider_workflows.provider_input(wf, graph).get("voice_id") or "").strip()
            except Exception:   # a job of an older shape of this model: looked past
                continue
            if voice:
                return voice
        return ""

    async def _provider_clip_once(self, job, live, wf, settings, clip=None, plain=False, rung=0, sound_off=False, model=None):
        """One try (see _provider_clip): rung, the try of the content filter's ladder (each a request of its own);
        sound_off, the clip asked without its sound; model, a stand-in model asked instead of the job's own."""
        provider = wf["profile"]["provider"]
        graph, ctx = workflows.build_prompt(wf, dict(settings, clips=1))
        inputs = provider_workflows.provider_input(wf, graph)
        if "language_code" in inputs:   # "English", "en" -> en-IN: the provider takes a language and region
            inputs["language_code"] = provider_router.language_tag(inputs["language_code"])
            if not inputs["language_code"]:
                inputs.pop("language_code")
        if "voice_id" in inputs and not str(inputs.get("voice_id") or "").strip():
            # A voiceover with no voice chosen (the provider may have no default of its own): the voice this module's
            # last voiceover was made with, so a retake sounds the same, else the provider's first in its language.
            picked = await offload(self._voice_before, job, wf) or await self.router.default_voice(inputs.get("language_code"))
            if not picked:
                raise provider_base.RequestProblem(NO_VOICE)
            inputs["voice_id"] = picked
        if str(inputs.get("style_instructions") or "").strip() and (plain or inputs.get("voice_id")):
            engine = "" if plain else await self.router.voice_engine(inputs["voice_id"])
            if plain or (engine and engine != STYLED_ENGINE):
                inputs.pop("style_instructions")
        metadata = await offload(self._who, job)   # {"scene": {"user", "project", "module", "job"}}
        live["node"] = "Sending it to the provider"
        self.notify(job["user_id"])

        tries = int((job.get("settings") or {}).get("not_ready_tries") or 0) if isinstance(job.get("settings"), dict) else 0
        key = provider_v1.idempotency_key(job["id"], clip, tries + (1000 if plain else 0) + 100 * rung)   # a re-try is a new request
        if sound_off and "sound" in inputs:
            inputs["sound"] = False
        model_id = provider["model"]
        if model:   # the stand-in takes what it has a setting for, with values it offers; the rest is its own default
            inputs = await self._inputs_for(model, provider.get("capability"), inputs)
            model_id = model

        async def attempt(choice):
            adapter = await offload(self.router.adapter, choice["provider"])
            sent = await self._provider_files(adapter, choice["secret"], inputs)
            started = await adapter.start(choice["secret"], model_id, sent, metadata, key)
            return adapter, started

        (adapter, started), choice = await self.router.run(model_id, attempt, job_id=job["id"], first=None if model else job.get("choice"))
        job["choice"] = choice
        note = dict(choice.described(), job=started["id"], request_id=started.get("request_id") or "",
                    quote=started.get("quote"), test=bool(started.get("test")))
        if clip:
            earlier = job.get("provider_note") or {}
            note["clips"] = list(earlier.get("clips") or []) + [{"clip": clip, "job": started["id"]}]
        job["provider_note"] = note
        await self.db.arun("UPDATE jobs SET provider_key = ?, provider = ?, server = ? WHERE id = ?",
                           (choice["key"]["id"] if choice["key"]["id"] > 0 else None, json.dumps(note), choice["provider"]["name"], job["id"]))
        print("Job {}{}: {} on {} (key {}), the provider's job {}, request {}.".format(
            job["id"], " clip {}".format(clip) if clip else "", model_id, choice["provider"]["name"], choice["key"]["label"],
            started["id"], note["request_id"] or "-"))
        live["node"] = "Waiting for the provider"
        self.notify(job["user_id"])

        def progress(answer):
            done = answer.get("progress")
            if isinstance(done, (int, float)) and not isinstance(done, bool):
                now, step = time.time(), int(max(0.0, min(1.0, done)) * 100)
                if "first_step" not in live:
                    live["first_step"] = (now, step)
                live.update(step=step, steps=100, step_time=now)
            if answer.get("message"):
                live["node"] = str(answer["message"])[:120]
            self.notify(job["user_id"])

        answer = await adapter.follow(choice["secret"], started["id"], progress, lambda: bool(live.get("cancel")), RENDER_MOST)
        cost = answer.get("cost") if not answer.get("studio_cancelled") else None   # cost_of'd by status()
        if clip:
            note["clips"][-1]["cost"] = cost
            costs = [c.get("cost") for c in note["clips"]]
            cost = sum(costs) if all(isinstance(c, (int, float)) for c in costs) else None   # the whole chain's, once known
        note.update(status=answer.get("status"), cost=cost, quote=answer.get("quote") or note["quote"],
                    request_id=answer.get("request_id") or note["request_id"])
        await self.db.arun("UPDATE jobs SET provider = ? WHERE id = ?", (json.dumps(note), job["id"]))
        if answer.get("studio_cancelled"):
            live["charged"] = bool(answer.get("charged", True))
            raise Cancelled()
        if answer.get("status") == "failed":
            raise provider_v1.job_problem(answer)
        if answer.get("status") != "succeeded":
            raise provider_base.RequestProblem("The provider cancelled the job.")
        return (adapter, choice, started, answer), ctx

    async def _run_provider_chain(self, job, live, wf, settings, clips):
        """A long video made of several clips by a provider's model, each starting on the last frame of the one before
        it, then joined into one video. The prompt may give each clip its own part, separated
        by a line of dashes (CLIP_BREAK); the job's last frame is the end of the final clip only. Each clip is its own
        call with its own Idempotency-Key (the job's and the clip's number), on the job's key."""
        schema = workflows.describe(wf)
        slots, roles = schema["slots"], {c["role"]: c for c in schema["controls"] if c["role"]}
        full_ctx = workflows.context(schema, settings)
        prompt = str((settings.get("values") or {}).get(roles["prompt"]["id"], roles["prompt"]["default"]) or "")
        prompts = [part.strip() for part in CLIP_BREAK.split(prompt) if part.strip()] or [prompt]
        refs = dict(settings.get("refs") or {})
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.tmp_dir) as tmp:
            tmp = Path(tmp)
            parts, previous = [], None
            for i in range(clips):
                live.update(clip=i + 1, clips=clips, step=0, steps=0, node="")
                live.pop("first_step", None)
                self.notify(job["user_id"])
                clip_settings = copy.deepcopy(settings)
                clip_settings["values"] = dict(settings.get("values") or {})
                clip_settings["values"][roles["prompt"]["id"]] = prompts[min(i, len(prompts) - 1)]
                clip_refs = dict(refs)
                if previous:
                    clip_refs[slots["first_frame"]] = {"comfy_name": previous, "name": "end of clip {}".format(i)}
                if i < clips - 1:
                    clip_refs.pop(slots.get("last_frame"), None)   # only the final clip ends on the last-frame image
                clip_settings["refs"] = clip_refs
                (adapter, choice, started, answer), _ = await self._provider_clip(job, live, wf, clip_settings, clip=i + 1)
                outputs = [o for o in answer.get("outputs") or [] if isinstance(o, dict)]
                n = next((n for n, o in enumerate(outputs)
                          if _kind_of_output(o, Path(str(o.get("name") or "")).suffix or ".mp4") == "video"), None)
                if n is None:
                    raise provider_base.ProviderProblem("The provider finished clip {} but sent no video.".format(i + 1))
                part = tmp / "clip_{}.mp4".format(i)
                live["node"] = "Fetching clip {}".format(i + 1)
                self.notify(job["user_id"])
                await adapter.fetch_output(choice["secret"], started["id"], n, part, outputs)
                parts.append(part)
                if i < clips - 1:
                    frame = await media.last_frame(part, tmp / "frame_{}.png".format(i))
                    previous = await keep_reference(self.storage, "chain_{}_{}.png".format(job["id"], i + 1), frame.read_bytes())
            live.update(node="Joining the clips", step=0, steps=0)
            self.notify(job["user_id"])
            folder, stem = await offload(self._target, job)
            target = folder / (stem + ".mp4")
            await media.join(parts, target)
        found = await media.probe(target)
        made = dict(full_ctx, fps=await media.frame_rate(target))
        if found.get("width"):
            made.update(width=found["width"], height=found["height"])
        await offload(self._record, job, "video", target, made)

    async def _clean_voice_here(self, job, live, wf):
        """A provider's job (a lip sync) whose voice track has music, effects or other people under the voice, and asks
        for it to be taken out ("clean_voice"): the voice is separated first by whichever provider offers separate_voice
        through the router (Studio_automation's key, or On this PC where it is set up), and its voice track becomes
        the voice alone, kept as a reference file of its own. The job keeps its own settings, so making it again cleans
        the original track again. None offers it: the job fails with NO_CLEAN_VOICE."""
        settings = job["settings"]
        slot = (workflows.describe(wf).get("slots") or {}).get("voice_track")
        given = (settings.get("refs") or {}).get(slot) if slot and settings.get("clean_voice") is True else None
        if not given or not given.get("comfy_name"):
            return settings
        name = given["comfy_name"]
        if not await offload(kept_reference, self.storage, name):
            raise provider_base.RequestProblem("The voice track {} is missing: add it to the job again.".format(name))
        voice = await self._separate_voice(job, live, name)
        live["node"] = ""
        return dict(settings, refs=dict(settings["refs"], **{slot: {"comfy_name": voice, "name": "the voice of {}".format(given.get("name") or "the track")}}))

    async def _separate_voice(self, job, live, name):
        """The voice of the reference file `name`, separated by the provider the router picks for CLEAN_VOICE (its key
        held for this step alone, then let go), and kept as a reference file of its own: its name. While every key
        that offers it is busy it waits, as a queued job would."""
        if self.router is None:
            raise provider_base.RequestProblem(NO_CLEAN_VOICE)
        holder = "{}-clean-voice".format(job["id"])   # what holds the key in the router's count: not the job's own key
        own = (job.get("choice") or {}).get("key") or {}
        first = None
        while True:
            choice, problem = await offload(self.router.pick, CLEAN_VOICE)
            if problem:
                raise provider_base.RequestProblem(NO_CLEAN_VOICE)
            if choice is not None:
                break
            # Busy because this very job holds the key (one Studio_automation key for the lip sync and the separation,
            # one job at a time): the separation runs on it, before the lip sync, without counting it twice.
            first = next((c for c in await offload(self.router.candidates, CLEAN_VOICE) if own.get("id") is not None
                          and c["key"]["id"] == own["id"] and self.router.why_not(c) == "full"), None)
            if first is not None:
                holder = None
                break
            if live.get("cancel"):
                raise Cancelled()
            live["node"] = "Waiting for voice separation"
            self.notify(job["user_id"])
            await asyncio.sleep(2)
        data = await offload(self.storage.read_bytes, REFERENCES, name)
        metadata = await offload(self._who, job)
        tries = int((job.get("settings") or {}).get("not_ready_tries") or 0) if isinstance(job.get("settings"), dict) else 0
        key = provider_v1.idempotency_key(job["id"], None, tries) + "-clean-voice"

        async def attempt(armed):
            adapter = await offload(self.router.adapter, armed["provider"])
            sent = await adapter.upload(armed["secret"], name=name, data=data)
            return adapter, await adapter.start(armed["secret"], CLEAN_VOICE, {"audio": sent}, metadata, key)

        try:
            (adapter, started), choice = await self.router.run(CLEAN_VOICE, attempt, job_id=holder, first=first)
        except provider_router.NoProvider:
            raise provider_base.RequestProblem(NO_CLEAN_VOICE)
        try:
            here = choice["provider"]["kind"] == provider_router.LocalTools.kind
            live["node"] = "Taking the voice out of the music ({})".format("on this PC" if here else choice["provider"]["name"])
            self.notify(job["user_id"])
            print("Job {}: the voice taken out on {} (key {}), the provider's job {}.".format(
                job["id"], choice["provider"]["name"], choice["key"]["label"], started["id"]))
            answer = await adapter.follow(choice["secret"], started["id"], None, lambda: bool(live.get("cancel")), RENDER_MOST)
            if answer.get("studio_cancelled"):
                live["charged"] = bool(answer.get("charged", True))
                raise Cancelled()
            if answer.get("status") == "failed":
                raise provider_v1.job_problem(answer)
            if answer.get("status") != "succeeded":
                raise provider_base.RequestProblem("The provider cancelled the voice separation.")
            outputs = [o for o in answer.get("outputs") or [] if isinstance(o, dict)]
            n = next((n for n, o in enumerate(outputs) if Path(str(o.get("name") or "")).stem == "voice"), None)
            if n is None:   # no output named voice: the first sound (the contract's order is voice, then music_fx)
                n = next((n for n, o in enumerate(outputs) if _kind_of_output(o, _suffix_of_output(o)) == "audio"), None)
            if n is None:
                raise provider_base.ProviderProblem("The voice separation finished but sent no voice.")
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.tmp_dir) as tmp:
                target = Path(tmp) / ("voice" + (_suffix_of_output(outputs[n]) or ".wav"))
                await adapter.fetch_output(choice["secret"], started["id"], n, target, outputs)
                return await keep_reference(self.storage, "voice_" + Path(name).stem + target.suffix, target.read_bytes())
        finally:
            if holder is not None:
                self.router.release(choice, holder)

    async def _provider_files(self, adapter, secret, inputs):
        """The job's `input` with each file ({"file": the studio's name}) uploaded to the provider and given as its
        file id. The files are the studio's own copies (references.keep_reference)."""
        async def one(value):
            if isinstance(value, list):
                return [await one(v) for v in value]
            if not (isinstance(value, dict) and "file" in value):
                return value
            name = value["file"]
            if not await offload(kept_reference, self.storage, name):
                raise provider_base.RequestProblem("The file {} is missing: add it to the job again.".format(name))
            data = await offload(self.storage.read_bytes, REFERENCES, name)
            return await adapter.upload(secret, name=name, data=data)
        return {name: await one(value) for name, value in inputs.items()}

    def _who(self, job):
        """The metadata sent with each call to a provider: who the job is for and where it was made, {"scene":
        {"user", "project", "module", "job"}} (what it lacks left out). Studio_automation logs, limits and sorts its
        jobs by it. A module is a project with a parent (its canvas); a job on a project's own canvas is in the
        project's main canvas, named as the canvas is."""
        scene = {"job": {"id": job["id"], "name": job.get("name") or ""}}
        with as_everyone():
            user = self.db.one("SELECT id, name, email FROM users WHERE id = ?", (job["user_id"],))
            place = self.db.one("SELECT id, ref, name, canvas_name, parent_id FROM projects WHERE id = ?",
                                (job["project_id"],)) if job.get("project_id") else None
            top = self.db.one("SELECT id, ref, name, canvas_name FROM projects WHERE id = ?",
                              (place["parent_id"],)) if place and place["parent_id"] else place
        if user:
            scene["user"] = {"id": user["id"], "name": user["name"], "email": user["email"]}
        if top:
            scene["project"] = {"id": top["id"], "ref": top["ref"], "name": top["name"]}
            module = place if place["parent_id"] else None
            scene["module"] = ({"id": module["id"], "ref": module["ref"], "name": module["name"]} if module
                               else {"id": top["id"], "ref": top["ref"], "name": top["canvas_name"] or outputs_mod.MAIN_CANVAS})
        return {"scene": scene}

    def _target(self, job):
        folder = self.outputs.folder(job["user_id"]) / self.outputs.relative(job.get("project_id"))   # its project's folder
        folder.mkdir(parents=True, exist_ok=True)
        stem = "{}_{}".format(re.sub(r"[^\w.-]+", "_", job["name"]).strip("._") or "scene",
                              time.strftime("%Y%m%d_%H%M%S"))
        return folder, stem

    def _record(self, job, kind, target, ctx, name=None):
        if job.get("project_id") and not self.db.one("SELECT 1 FROM projects WHERE id = ?", (job["project_id"],)):
            media.remove_result(target)   # its project was deleted while it ran: nothing to file it in, nothing kept
            return
        # Its path inside the user's folder, in its project's folder (an edit writes at the top: it is moved there).
        filename = self.outputs.settle(job["user_id"], job.get("project_id"), target)
        target = self.outputs.folder(job["user_id"]) / filename
        item_id = self.db.run(
            "INSERT INTO generations (user_id, job_id, project_id, workflow, kind, name, filename, summary, settings, "
            "context, seconds, size, run, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job["user_id"], job["id"], job.get("project_id"), job["workflow"], kind, name or job["name"], filename,
             job["summary"], json.dumps({k: v for k, v in job["settings"].items() if k != "turn"}), json.dumps(ctx), round(time.time() - job["started"], 1),
             target.stat().st_size, placement.run_of(job), time.time()))
        if kind in ("image", "video"):   # its thumbnail, made now rather than when the canvas first asks for it
            try:
                asyncio.get_running_loop().create_task(media.make_poster_soon(target))
            except RuntimeError:   # on one of the database's threads (db.offload): the workers' loop makes it
                if self.loop is not None:
                    self.loop.call_soon_threadsafe(lambda: self.loop.create_task(media.make_poster_soon(target)))
        # A step the agent told where to keep its result ("save_to": /videos/3) puts it there; earlier tries become takes.
        slot = (job.get("settings") or {}).get("save_to_state")
        if slot and item_id:
            core.keep_take(self.db, job["user_id"], slot, item_id)
        # A job that names a board of the canvas ("board": Characters, Outputs) puts its result there (placement.py).
        if item_id:
            placement.place(self.db, job, item_id)
        # A step the agent planned as something to reuse ("keep": a character called Maya) goes into shared memory.
        keep = (job.get("settings") or {}).get("keep")
        if keep and item_id and self.assets_dir:
            try:
                memory.keep_made(self.db, self.assets_dir / str(job["user_id"]), job["user_id"], item_id, target, kind, keep)
            except OSError:
                pass   # the result is in the library either way; only its copy for reuse is missing
        return item_id

    # ------------------------------------------------------------ helpers

    def history(self):
        """Earlier runs, for time estimates."""
        with as_everyone():   # every user's runs: how long a workflow takes does not depend on who ran it
            rows = self.db.all("SELECT workflow, context, seconds FROM generations ORDER BY created DESC LIMIT 500")
        return [dict(r, context=json.loads(r["context"])) for r in rows]

    def _notify_all_waiting(self, also):
        users = {r["user_id"] for r in self.db.all("SELECT DISTINCT user_id FROM jobs WHERE status = 'queued'")}
        for user_id in users | ({also} if also else set()):
            self.notify(user_id)

    @staticmethod
    def _eta(job, live, now):
        if job["status"] != "running":
            return None
        clips, clip = live.get("clips") or 1, live.get("clip") or 1
        per_clip = (job.get("est_seconds") or 0) / clips
        first = live.get("first_step")
        if first and live.get("steps") and live["step"] > first[1]:
            per_step = (live["step_time"] - first[0]) / (live["step"] - first[1])
            current = max(0, per_step * (live["steps"] - live["step"]) - (now - live["step_time"]))
            return current + per_clip * (clips - clip)
        if job.get("est_seconds"):
            return max(0, job["est_seconds"] - (now - job["started"]))
        return None
