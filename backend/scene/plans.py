"""The agent's plans, carried out by the server after Approve (docs/r1-plan-runner-design.md).

A plan's steps are what the agent planned: generations, motion graphics, a sound on a video, cuts and joins, and the
finished cut. Approve reserves the plan's price at once; then a worker queues the steps in order through the same
route functions the studio's pages call, takes earlier results as references where a step starts on one, waits for
what the cut needs, and saves where it is after every step. A job a plan queues carries its plan and step in its own
row, written in the same statement that queues it, so after a restart a running plan goes on without queueing any
step twice. When the plan ends, what is left of the reservation goes back to the balance.

Review and retakes are the client's (the take chosen for the cut comes back through choose()).
"""

import asyncio
import json
import threading
import time
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.datastructures import FormData

from .credits import PREPAID
from .jobs import QUEUEING
from .db import offload
from . import content_check, guardrails, moderation

RUNNING = ("running", "stopping")
ENDED_JOB = ("done", "failed", "cancelled")
LOOK_EVERY = 5   # seconds between looks at the jobs table while waiting, besides being told when a job ends


class Refused(Exception):
    """A step could not be queued: the plan stops there, as the client's runner did."""


class Inside:
    """What a route function reads from a request, for the runner calling it itself: the app's state, and the form
    a job's settings arrive in. The limits on requests from browsers are not the runner's."""

    def __init__(self, state, settings=None):
        self.app = SimpleNamespace(state=state)
        self._settings = settings

    async def form(self, **_):
        return FormData([("settings", json.dumps(self._settings))])


class PlanRunner:
    def __init__(self, state):
        self.state = state
        self.db = state.db
        self.tasks = {}            # plan id -> its running task
        self.steps_lock = threading.Lock()   # one change of a plan's progress at a time (_set_step)
        self.ended = asyncio.Event()   # set whenever a job ends: the plans waiting on one look again
        try:   # the loop the plans wait on: stop() and choose() may be called from a database thread (db.offload)
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def _wake(self):
        """The plans waiting on a job look again: on their loop, wherever this is called from."""
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if self.loop is not None and here is not self.loop:
            self.loop.call_soon_threadsafe(self.ended.set)
        else:
            self.ended.set()

    # ------------------------------------------------------------ the plan as stored and answered

    def _row(self, plan_id, user_id=None):
        sql = "SELECT * FROM agent_plans WHERE id = ?" + (" AND user_id = ?" if user_id is not None else "")
        return self.db.one(sql, (plan_id,) + ((user_id,) if user_id is not None else ()))

    def shown(self, row):
        progress = json.loads(row["progress"])
        return {"id": row["id"], "state": row["state"], "total": row["total"], "reserved_left": row["reserved_left"],
                "error": row["error"], "created": row["created"], "approved": row["approved"], "finished": row["finished"],
                "tab": row["tab"], "project_id": row["project_id"], "name": row["name"],
                "steps": [{"job": p.get("job"), "made": p.get("made"), "error": p.get("error", ""), "waiting": bool(p.get("waiting")),
                           "skipped": bool(p.get("skipped")), "chosen": p.get("chosen")} for p in progress]}

    def _set_step(self, plan_id, step, only_job=None, **changes):
        """Change one step's progress: read, changed and written back under one lock, so two at once (the runner and a
        job that ends, on two of the database's threads) never write over each other. `only_job`: only while that job is
        still the step's (a late word from a job the step has gone past is not its news). Returns the progress."""
        with self.steps_lock:
            row = self._row(plan_id)
            if row is None:
                return None
            progress = json.loads(row["progress"])
            if not 0 <= step < len(progress) or (only_job and progress[step].get("job") not in (None, only_job)):
                return progress
            progress[step].update(changes)
            self._save(plan_id, progress)
            return progress

    def _save(self, plan_id, progress=None, **fields):
        if progress is not None:
            fields["progress"] = json.dumps(progress)
        if fields:
            self.db.run("UPDATE agent_plans SET {} WHERE id = ?".format(", ".join(k + " = ?" for k in fields)),
                        (*fields.values(), plan_id))
        self.tell(plan_id)

    def tell(self, plan_id):
        """Sends the plan to its owner's open pages (the live connection's `plans`)."""
        row = self._row(plan_id)
        say = getattr(self.state, "tell_plans", None)
        if row and say:
            say(row["user_id"], [self.shown(row)])

    def get(self, user, plan_id):
        row = self._row(plan_id, user["id"])
        if row is None:
            raise HTTPException(404, "No such plan.")
        return row

    def listing(self, user, tab="", project=None):
        sql, values = "SELECT * FROM agent_plans WHERE user_id = ?", [user["id"]]
        if tab:
            sql, values = sql + " AND tab = ?", values + [tab]
        if project == 0:
            sql += " AND project_id IS NULL"
        elif project is not None:
            sql, values = sql + " AND project_id = ?", values + [project]
        return [self.shown(r) for r in self.db.all(sql + " ORDER BY id DESC LIMIT 50", tuple(values))]

    # ------------------------------------------------------------ made, approved, stopped, resumed

    async def create(self, user, body):
        steps = body.get("steps")
        if not isinstance(steps, list) or not steps or len(steps) > 200 or not all(isinstance(s, dict) for s in steps):
            raise HTTPException(400, "A plan needs its steps.")
        problem = await offload(moderation.plan_problem, self.db, steps)   # words the studio refuses: said before Approve
        if problem:
            raise HTTPException(400, problem)
        # the content check, as the agent's route ran it (its verdict of the same words is remembered: not asked again)
        problem = content_check.problem(await content_check.check(getattr(self.state, "agent", None), self.db, user["id"], steps, body.get("name") or ""))
        if problem:
            raise HTTPException(400, problem)
        project_id = body.get("project_id") or None
        if project_id:
            from . import sharing
            await offload(sharing.require, self.db, user, project_id, "creator")
        progress = [{"skipped": bool(s.get("skipped"))} for s in steps]
        plan_id = await self.db.arun(
            "INSERT INTO agent_plans (user_id, project_id, tab, name, steps, progress, state, created) VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)",
            (user["id"], project_id, str(body.get("tab") or "")[:80], str(body.get("name") or "")[:120], json.dumps(steps),
             json.dumps(progress), time.time()))
        total = await self.price(user, steps, progress)
        await self.db.arun("UPDATE agent_plans SET total = ? WHERE id = ?", (total, plan_id))
        return self.shown(await offload(self._row, plan_id))

    async def price(self, user, steps, progress):
        """What the steps not queued yet cost now: a generation as Generate would price it, motion graphics by length,
        edits and the cut nothing."""
        from .api import studio, workspace
        from .comfy import workflows
        total = 0
        for step, p in zip(steps, progress):
            if p.get("skipped") or p.get("job"):
                continue
            try:
                if step.get("motion"):
                    total += (await workspace._motion_price(self.state, user, dict(step["motion"])))[1]
                elif step.get("settings") and not (step.get("assemble") or step.get("sound") or step.get("edit")):
                    settings = json.loads(json.dumps(step["settings"]))
                    uses = step.get("uses") or []   # the video it is made from, as _queue gives it: priced by its real length
                    parent = step["start"]["id"] if step.get("start") else uses[0].get("id") if uses else None
                    if isinstance(parent, int):
                        settings["parent"] = parent
                        settings.pop("source_seconds", None)   # not the length the plan says, which may be anything
                    wf = await self.state.catalog.load(str(settings.get("workflow", "")))
                    await offload(studio.switched_on, self.state, wf["id"], user)
                    await offload(studio.fit_resolution, self.state, workflows.describe(wf), settings)   # it reads the database
                    total += (await studio.price(self.state, wf, settings, user["id"]))["credits"]
            except HTTPException:
                raise
            except Exception as e:   # a step that can't be priced can't be made: said now, before anything is charged
                raise HTTPException(400, "“{}” can't be priced: {}".format(step.get("name") or "A step", e))
        return total

    async def approve(self, user, plan_id, again=False):
        """Reserve the plan's price and run it. A plan already running or done is answered as it is: approving twice
        charges once. `again` (resume): a stopped or failed plan runs on from where it stopped."""
        row = await offload(self.get, user, plan_id)
        from_states = ("stopped", "failed") if again else ("waiting",)
        if row["state"] not in from_states:
            return self.shown(row)
        marks = ", ".join("?" * len(from_states))
        if not await self.db.achange("UPDATE agent_plans SET state = 'running', error = '' WHERE id = ? AND state IN ({})".format(marks),
                              (plan_id, *from_states)):
            return self.shown(await offload(self._row, plan_id))   # approved at the same moment by another request
        try:
            steps, progress = json.loads(row["steps"]), json.loads(row["progress"])
            if again:   # what failed is tried again: a step not queued, or whose job failed or was cancelled
                for p in progress:
                    job = p.get("job") and await self.db.aone("SELECT status FROM jobs WHERE id = ?", (p["job"],))
                    # its job's end may not have been told to the plan yet (job_ended runs after the job is shown ended)
                    ended = bool(job) and job["status"] in ("failed", "cancelled")
                    if not p.get("made") and (ended or (p.get("error") and not job)):
                        p.update(error="", job=None)
            total = await self.price(user, steps, progress)
            problem = await offload(guardrails.plan_problem, self.db, user, total)   # the studio's stop, the plan limit
            if problem:
                raise HTTPException(429, problem)
            # What is still reserved for this plan pays first: only what it lacks is charged now. A plan that ended gave
            # its reservation back (_finish), so a resume reserves what is left to make; one reservation, never two.
            held = row["reserved_left"]
            need = max(0, total - held)
            over = await offload(self.state.credits.cap_problem, user["id"], need)   # the daily limit, checked here, at approval
            if over:
                raise HTTPException(429, over)
            if need and not await offload(self.state.credits.charge, user["id"], need, "generation", note="Reserved for plan {}".format(plan_id),
                                                      project_id=row["project_id"]):
                raise HTTPException(402, "This plan needs {} credits and you have {}. Ask an admin for more.".format(
                    need, await offload(self.state.credits.balance, user["id"])))
        except BaseException:
            await self.db.arun("UPDATE agent_plans SET state = ? WHERE id = ?", (row["state"], plan_id))
            raise
        await self.db.arun("UPDATE agent_plans SET total = ?, reserved_left = reserved_left + ?, approved = COALESCE(approved, ?), finished = NULL, "
                    "progress = ? WHERE id = ?", (total, need, time.time(), json.dumps(progress), plan_id))
        self.run(plan_id)
        await offload(self.tell, plan_id)
        sender = getattr(getattr(self.state, "traces", None), "langfuse", None)
        planned = next((s["settings"] for s in steps if isinstance(s.get("settings"), dict) and s["settings"].get("turn")), None)
        if sender is not None and planned and not again:   # Langfuse: the user approved what the turn planned
            await offload(sender.turn_score, planned, "approved", 1, "plan-approved-{}".format(plan_id))
        return self.shown(await offload(self._row, plan_id))

    def stop(self, user, plan_id):
        """The steps not queued yet stay unqueued; what is queued runs on. The plan is stopped once that has ended."""
        self.get(user, plan_id)
        if self.db.change("UPDATE agent_plans SET state = 'stopping' WHERE id = ? AND state = 'running'", (plan_id,)):
            self._wake()   # a step waiting on another stops waiting
            self.tell(plan_id)
        return self.shown(self._row(plan_id))

    def choose(self, user, plan_id, step, item):
        """The take of a shot the finished cut uses (the user's choice from the client's review and retakes)."""
        row = self.get(user, plan_id)
        progress = json.loads(row["progress"])
        if not isinstance(step, int) or not 0 <= step < len(progress):
            raise HTTPException(400, "No such step.")
        if item is not None and not self.db.one("SELECT 1 FROM generations WHERE id = ? AND user_id = ?", (item, user["id"])):
            raise HTTPException(400, "That take is not one of yours.")
        self._set_step(plan_id, step, chosen=item)
        self._wake()
        return self.shown(self._row(plan_id))

    # ------------------------------------------------------------ the worker

    def start(self):
        """After a restart: every plan that was running goes on (found on the database's threads, then run here)."""
        async def resume():
            for row in await self.db.aall("SELECT id FROM agent_plans WHERE state IN ('running', 'stopping')"):
                self.run(row["id"])
        self.tasks[None] = asyncio.ensure_future(resume())

    def run(self, plan_id):
        task = self.tasks.get(plan_id)
        if task and not task.done():
            return
        self.tasks[plan_id] = asyncio.ensure_future(self._run(plan_id))

    async def job_ended(self, job, status):
        """A job ended (JobManager.finished): the plans it belongs to are told, on the database's threads."""
        await offload(self._job_ended, job, status)

    def _job_ended(self, job, status):
        """Told by the queue whenever a job ends: a plan's step is made (or not), and the plans waiting look again."""
        step = job.get("plan_step")
        if job.get("plan_id") is not None and isinstance(step, int):
            # Only while this job is still the step's: a step tried again after a failure has a new job, and the old
            # one's end (late, from a thread) must not mark it failed again.
            if status == "done":
                self._set_step(job["plan_id"], step, only_job=job["id"], job=job["id"], made=self._made(job["id"]))
            else:
                self._set_step(job["plan_id"], step, only_job=job["id"], job=job["id"], error="Not made ({}).".format(status))
        self._wake()

    def _made(self, job_id):
        found = self.db.one("SELECT id FROM generations WHERE job_id = ? ORDER BY id LIMIT 1", (job_id,))
        return found["id"] if found else None

    def _queued(self, plan_id, step):
        """The job queued for this step that is not over and failed: a step tried again after failing gets a new one."""
        found = self.db.one("SELECT id FROM jobs WHERE plan_id = ? AND plan_step = ? AND status NOT IN ('failed', 'cancelled') "
                            "ORDER BY created DESC LIMIT 1", (plan_id, step))
        return found["id"] if found else None

    async def _pause(self):
        self.ended.clear()
        try:
            await asyncio.wait_for(self.ended.wait(), LOOK_EVERY)
        except asyncio.TimeoutError:
            pass

    async def _run(self, plan_id):
        try:
            await self._walk(plan_id)
        except Exception as problem:   # a plan never stops the server; it says what went wrong
            await offload(self._finish, plan_id, "failed", "{}: {}".format(type(problem).__name__, problem))

    async def _walk(self, plan_id):
        row = await offload(self._row, plan_id)
        if row is None or row["state"] not in RUNNING:
            return
        user = await self.db.aone("SELECT * FROM users WHERE id = ?", (row["user_id"],))
        steps = json.loads(row["steps"])
        for i, step in enumerate(steps):
            row = await offload(self._row, plan_id)
            if row["state"] != "running":
                break
            progress = json.loads(row["progress"])
            p = progress[i]
            if p.get("skipped") or p.get("made"):
                continue
            job = p.get("job") or await offload(self._queued, plan_id, i)   # queued before, even before a restart: never again
            if job:
                if p.get("job") != job:
                    await offload(self._set_step, plan_id, i, job=job)
                continue
            try:
                job = await self._queue(plan_id, user, steps, i)
            except _Stopping:
                break
            except Refused as refused:
                await offload(self._set_step, plan_id, i, error=str(refused), waiting=False)
                return await offload(self._finish, plan_id, "failed", "“{}” was not made: {}".format(step.get("name") or "A step", refused))
            await offload(self._set_step, plan_id, i, job=job, error="", waiting=False)
        # Every queued step ends before the plan does.
        while True:
            row = await offload(self._row, plan_id)
            progress = json.loads(row["progress"])
            jobs = [p["job"] for p in progress if p.get("job")]
            marks = ", ".join("?" * len(jobs))
            open_jobs = (await self.db.aone("SELECT COUNT(*) AS n FROM jobs WHERE id IN ({}) AND status NOT IN ('done', 'failed', 'cancelled')".format(marks),
                                    tuple(jobs)))["n"] if jobs else 0
            if not open_jobs:
                break
            await self._pause()
        for i, p in enumerate(progress):   # a step made while no one was told (a restart)
            if p.get("job") and not p.get("made"):
                p["made"] = await offload(self._made, p["job"])
                if p["made"]:
                    await offload(self._set_step, plan_id, i, only_job=p["job"], made=p["made"])
        row = await offload(self._row, plan_id)
        failed = any(p.get("error") or (p.get("job") and not p.get("made")) for p in progress if not p.get("skipped"))
        unqueued = any(not p.get("job") and not p.get("made") and not p.get("skipped") for p in progress)
        state = "stopped" if row["state"] == "stopping" or (unqueued and not failed) else "failed" if failed else "done"
        await offload(self._finish, plan_id, state, row["error"])

    def _finish(self, plan_id, state, error=""):
        """The plan has ended: said so, and what is left of its reservation goes back to the balance, once."""
        row = self._row(plan_id)
        if row is None:
            return
        left = row["reserved_left"]
        if left > 0 and self.db.change("UPDATE agent_plans SET reserved_left = 0 WHERE id = ? AND reserved_left = ?", (plan_id, left)):
            self.state.credits.add(row["user_id"], left, "refund", note="Plan {}: not used".format(plan_id))
        self._save(plan_id, state=state, error=error or "", finished=time.time())
        notify = getattr(self.state.jobs, "notify", None) if hasattr(self.state, "jobs") else None
        if notify:
            notify(row["user_id"])   # the balance, back

    # ------------------------------------------------------------ one step

    async def _queue(self, plan_id, user, steps, i):
        """Queue step i through the route that queues it for the studio's pages; returns its job's id."""
        from .api import library, studio, workspace
        row = await offload(self._row, plan_id)
        step = steps[i]
        project_id = row["project_id"]
        inside = Inside(self.state)
        try:
            token = PREPAID.set(plan_id)
            queueing = QUEUEING.set((plan_id, i))
            try:
                if step.get("assemble"):
                    body = await self._cut(plan_id, steps, i, step["assemble"], project_id)
                    return (await workspace.assemble(body, inside, user))["job"]
                if step.get("motion"):
                    return (await workspace.motion_render({**step["motion"], "project_id": project_id}, inside, user))["job"]
                if step.get("sound"):
                    return (await workspace.add_sound({**step["sound"], "project_id": project_id}, inside, user))["job"]
                if step.get("edit"):
                    clips = step["edit"].get("clips") or []
                    body = {"name": step.get("name"), "clips": clips, "parent": clips[0]["id"] if clips else None, "project_id": project_id}
                    return (await workspace.export_timeline(body, inside, user))["job"]
                uses = step.get("uses") or []
                settings = {**step["settings"], "refs": {}, "project_id": project_id,
                            "parent": step["start"]["id"] if step.get("start") else uses[0].get("id") if uses else None}
                for use in uses:   # each attached item goes into the slot the plan named for it
                    if use.get("asset"):   # a saved asset from the agent's memory: the server takes it by its id
                        settings["refs"][use["slot"]] = {"asset_id": use["asset"], "name": use.get("name", "")}
                        continue
                    ref = await library.as_reference(use["id"], inside, use.get("kind") or "image", user)
                    settings["refs"][use["slot"]] = {"comfy_name": ref["comfy_name"], "name": ref["name"]}
                if step.get("start"):
                    ref = await library.as_reference(step["start"]["id"], inside, "image", user)
                    settings["refs"][step["start"]["slot"]] = {"comfy_name": ref["comfy_name"], "name": ref["name"]}
                if step.get("after"):   # this shot starts on what an earlier step makes: waited for, then its first frame
                    earlier = await self._result(plan_id, steps, step["after"]["step"], i)
                    ref = await library.as_reference(earlier, inside, "image", user)
                    settings["refs"][step["after"]["slot"]] = {"comfy_name": ref["comfy_name"], "name": ref["name"]}
                    settings["parent"] = earlier
                return (await studio.create_job(Inside(self.state, settings), user))["id"]
            finally:
                QUEUEING.reset(queueing)
                PREPAID.reset(token)
        except HTTPException as refused:
            raise Refused(refused.detail if isinstance(refused.detail, str) else "It was refused.")
        except (Refused, _Stopping):
            raise
        except Exception as problem:
            raise Refused(str(problem) or type(problem).__name__)

    async def _result(self, plan_id, steps, step, waiting_step):
        """The library item step `step` made, waiting for its job if it is still being made. A failed or cancelled job,
        or a step that was not queued, fails the step that waits on it."""
        await offload(self._mark_waiting, plan_id, waiting_step, True)
        try:
            while True:
                row = await offload(self._row, plan_id)
                if row["state"] != "running":
                    raise _Stopping()
                p = json.loads(row["progress"])[step]
                if p.get("made"):
                    return p.get("chosen") or p["made"]
                job = p.get("job") or await offload(self._queued, plan_id, step)
                if not job:
                    raise Refused("The step this one starts on was not made.")
                found = await self.db.aone("SELECT status FROM jobs WHERE id = ?", (job,))
                if found and found["status"] in ("failed", "cancelled"):
                    raise Refused("The step this one starts on did not finish.")
                if found and found["status"] == "done":
                    made = await offload(self._made, job)
                    if made:
                        return p.get("chosen") or made
                    raise Refused("The step this one starts on has no result in the library.")
                await self._pause()
        finally:
            await offload(self._mark_waiting, plan_id, waiting_step, False)

    def _mark_waiting(self, plan_id, step, waiting):
        self._set_step(plan_id, step, waiting=waiting)

    async def _cut(self, plan_id, steps, i, cut, project_id):
        """The finished cut: its shots (the take chosen of each) in order, a fade where a new place starts, and the music."""
        clips = list(cut.get("clips") or [])
        last = None
        for index in cut.get("steps") or []:
            shot = steps[index] if isinstance(index, int) and 0 <= index < len(steps) else None
            if not shot or shot.get("skipped"):
                continue
            made = await self._result(plan_id, steps, index, i)
            fade = bool(last and shot.get("place") and last.get("place") and shot["place"] != last["place"])
            clips.append({"id": made, "start": 0, "end": 0, "fade": fade})
            last = shot
        music = await self._result(plan_id, steps, cut["music_step"], i) if cut.get("music_step") is not None else cut.get("music")
        return {"name": cut.get("name"), "clips": clips, "music": music, "title": cut.get("title"), "end": cut.get("end"),
                "look": cut.get("look"), "shape": cut.get("shape"), "project_id": project_id}


class _Stopping(Exception):
    """The plan was stopped while a step waited."""
