"""What happens once a shot the agent planned is made: it is checked straight away, with the agent panel open or not.

A job the agent planned carries a "shot" in its settings (workspace.py gives every planned generation one). When it is
done (jobs.JobManager.finished, see install) and no other planned shot of that project is still waiting or being made,
so that a batch is checked together, its result is checked in the background WAIT seconds later:

- a picture or a clip is reviewed by the agent's model (review.review_item), against the references the step used
  ("review_refs") and the project's always-on entries;
- a sound (music, a voice track) is measured (review.review_sound): its length against what was asked, its loudness,
  its silences.

The verdict is kept with the item (generations.review), where the agent panel, NeuralCore and the agent's next plan
read it. An agent panel that is open reviews a finished shot itself, with the shot before it, inside WAIT: the
background then finds the verdict kept and leaves it. Reviews are not charged (as on the panel); measuring costs nothing.

"Retry a failed shot once by itself" (retry_on; each user's own, off unless they turn it on): a picture or a clip that
fails its review is made again once, at once, with the review's fixed prompt and a new seed, charged like any render.
The retake is take 2 of the same shot; when it fails too, nothing more is tried: its verdict says so ("twice"), and the
agent tells the user what the model cannot do and offers another way, as its rules say for a second failure.
"""

import asyncio
import json

from . import review
from .db import as_everyone

WAIT = 30              # seconds after a job is done before the background looks at its result
BATCH_POLL = 15        # seconds between looks at whether the rest of a batch is made
RETRY_KEY = "agent_retry_once.{}"   # a user's "Retry a failed shot once by itself", in the settings table
REVIEWED = ("image", "video", "audio")
running = {}           # item id -> the task reviewing it now, so the panel and the background never review it twice at once


def retry_on(db, user_id):
    """Whether this user lets a failed shot be made again once without asking. Off unless they turned it on."""
    return db.setting(RETRY_KEY.format(int(user_id)), "0") == "1"


def set_retry(db, user_id, on):
    db.set_setting(RETRY_KEY.format(int(user_id)), "1" if on else "0")


def agent_made(settings):
    """Whether a job's settings are those of a step the agent planned."""
    return isinstance(settings, dict) and isinstance(settings.get("shot"), dict) and bool(settings["shot"].get("id"))


def install(state):
    """Check every finished job the agent planned, from now on (main.py calls this once the job manager is made)."""
    def finished(job, status):
        if status != "done" or not agent_made(job.get("settings")):
            return
        task = asyncio.get_running_loop().create_task(_quietly(after_batch(state, dict(job))))
        state.jobs.working_after = getattr(state.jobs, "working_after", set())
        state.jobs.working_after.add(task)   # kept until done: a task nobody holds may be collected half-way
        task.add_done_callback(state.jobs.working_after.discard)
    state.jobs.finished.append(finished)


async def _quietly(work):
    try:
        await work
    except asyncio.CancelledError:
        raise
    except Exception as error:   # a check that fails leaves the result as it is: the user still has it
        print("A finished shot could not be checked: {}".format(error))


async def once(item_id, work):
    """Run `work` (a coroutine giving a verdict) for an item, or wait for the one already running for it."""
    task = running.get(item_id)
    if task is None:
        task = running[item_id] = asyncio.ensure_future(work)
        task.add_done_callback(lambda _: running.pop(item_id, None))
    else:
        work.close()
    return await asyncio.shield(task)


def references_of(state, user_id, settings, item):
    """[(name, path)] of the pictures a shot was made with: the step's "review_refs" ({"id"} or {"asset"}), else the
    project's always-on entries."""
    from . import kit
    found = []
    for use in settings.get("review_refs") or [] if isinstance(settings.get("review_refs"), list) else []:
        if not isinstance(use, dict):
            continue
        if isinstance(use.get("asset"), int) and use["asset"]:
            row = state.db.one("SELECT name, kind, filename FROM assets WHERE id = ? AND user_id = ?", (use["asset"], user_id))
            path = row and state.assets_dir / str(user_id) / row["filename"]
        elif isinstance(use.get("id"), int):
            row = state.db.one("SELECT name, kind, filename FROM generations WHERE id = ? AND user_id = ?", (use["id"], user_id))
            path = row and state.outputs.folder(user_id) / row["filename"]
        else:
            continue
        if row and row["kind"] in ("image", "video") and path.is_file():
            found.append((row["name"], path))
    if not found and item.get("project_id"):
        for e in kit.always(state.db, user_id, item["project_id"]):
            path = state.assets_dir / str(user_id) / e["filename"]
            if e["kind"] in ("image", "video") and e["made_from"] != item["id"] and path.is_file():
                found.append((e["name"], path))
    return found


def batch_running(state, job):
    """Whether another shot the agent planned for this user and project is still waiting or being made."""
    with as_everyone():   # outside any request: the statement names the user itself
        rows = state.db.all("SELECT settings, project_id FROM jobs WHERE user_id = ? AND id != ? AND status IN ('queued', 'running')",
                            (job["user_id"], job["id"]))
    return any(r["project_id"] == job.get("project_id") and agent_made(json.loads(r["settings"] or "{}")) for r in rows)


async def after_batch(state, job):
    """Check a finished job once the batch it belongs to is made, so its shots are checked together."""
    while batch_running(state, job):
        await asyncio.sleep(BATCH_POLL)
    await after(state, job)


async def after(state, job, wait=None):
    """Check the result of one finished job the agent planned, unless it is checked already; retake it once when the
    user allows it and it failed. Returns the verdict, or None when there was nothing to check."""
    await asyncio.sleep(WAIT if wait is None else wait)
    user_id = job["user_id"]
    with as_everyone():   # outside any request: every statement names the user itself
        rows = state.db.all("SELECT * FROM generations WHERE job_id = ? AND user_id = ? ORDER BY id", (job["id"], user_id))
        item = next((r for r in rows if r["kind"] in REVIEWED), None)
        if item is None or review.load(item):
            return None
        settings = job["settings"] if isinstance(job.get("settings"), dict) else json.loads(item["settings"] or "{}")
        if item["kind"] == "audio":
            asked = job.get("seconds_requested")
            return await once(item["id"], _sound(state, user_id, item, asked if isinstance(asked, (int, float)) and asked > 0 else None))
        verdict = await once(item["id"], _picture(state, user_id, item, settings))
        if verdict and not verdict["passed"]:
            verdict = await failed(state, user_id, item, settings, verdict)
        return verdict


async def _sound(state, user_id, item, asked):
    verdict = await review.review_sound(state, user_id, item, asked)
    return keep(state, user_id, item, dict(verdict, by="auto"))


async def _picture(state, user_id, item, settings):
    verdict = await review.review_item(state, user_id, item, "", references_of(state, user_id, settings, item))
    return keep(state, user_id, item, dict(verdict, by="auto"))


def keep(state, user_id, item, verdict):
    state.db.run("UPDATE generations SET review = ? WHERE id = ? AND user_id = ?", (json.dumps(verdict), item["id"], user_id))
    return verdict


def take_of(settings):
    shot = settings.get("shot") if isinstance(settings.get("shot"), dict) else {}
    return shot.get("take") if isinstance(shot.get("take"), int) else 1


async def failed(state, user_id, item, settings, verdict):
    """A shot that failed its review in the background: a second failure is marked so; a first is made again once when
    the user allows it (retry_on). Returns the verdict kept with the item, which says what was done."""
    if take_of(settings) >= 2:
        return keep(state, user_id, item, dict(verdict, twice=True))
    if not retry_on(state.db, user_id):
        return verdict
    queued = await retake_now(state, user_id, item, verdict)
    return keep(state, user_id, item, dict(verdict, **queued))


async def retake_now(state, user_id, item, verdict):
    """Queue the retake of a failed item at once, charged like any render. Returns {"retake_job", "retake_credits"}, or
    {"retake_not_made": why}."""
    from fastapi import HTTPException
    from .api.studio import price
    from .api.workspace import _retake
    from .comfy import workflows
    planned = await _retake(state, {"id": user_id}, item, verdict, None)
    if planned is None:
        return {"retake_not_made": "the review gave no new prompt, or the workflow is gone"}
    settings = dict(planned["settings"], prompt=planned["prompt"], auto_retake=True)
    try:
        wf = await state.catalog.load(settings["workflow"])
        schema = workflows.describe(wf)
        quote = await price(state, wf, settings, user_id)
        over = state.credits.cap_problem(user_id, quote["credits"])
        if over:
            return {"retake_not_made": over}
        if not state.credits.charge(user_id, quote["credits"], "generation"):
            return {"retake_not_made": "there are not enough credits for it"}
        job_id = state.jobs.add(user_id, settings["name"], wf["id"], settings, workflows.summary(schema, workflows.context(schema, settings)),
                                quote["minutes"] * 60 if quote["minutes"] else None, quote["credits"], item["project_id"], quote["seconds"])
    except (HTTPException, workflows.WorkflowError, ValueError, KeyError) as error:
        return {"retake_not_made": str(getattr(error, "detail", None) or error)}
    state.notify(user_id)
    return {"retake_job": job_id, "retake_credits": quote["credits"]}
