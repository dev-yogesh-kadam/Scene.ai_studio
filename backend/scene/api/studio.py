"""Creating: workflows, estimates, jobs and the live event stream."""

import contextlib
import json
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

import httpx

from .. import guardrails, sharing, health, kit, media, memory, placement, runs, storage
from ..db import as_everyone, offload
from ..catalog import KINDS
from ..comfy import workflows
from ..references import media_kind, owns_upload, read_upload, upload_reference
from ..security import same_origin
from .deps import COOKIE, current_user, limited, uploading, user_for_token

router = APIRouter(prefix="/api", tags=["studio"])
PAGE = re.compile(r"^#/[a-z]{1,20}$")   # a page of the studio, as the browser names it: "#/canvas"


def current_announcement(db):
    try:
        found = json.loads(db.setting("announcement", "{}") or "{}")
    except ValueError:
        return {}
    if not found.get("text") or (found.get("until") and found["until"] < time.time()):
        return {}
    return {"text": found["text"], "level": found.get("level", "info"), "until": found.get("until")}


def by_source(wf):
    """Whether a job is as long as the video it is given, and billed by that: an upscale, and any workflow whose presets
    file says {"pricing": {"source": "video"}} (a lip sync)."""
    return wf["id"].startswith("upscaler/") or (wf["profile"].get("pricing") or {}).get("source") == "video"


async def billed_seconds(state, wf, schema, settings, user_id=None):
    """The length of the result these settings ask for, which is what a per-second price is based on. None when
    the workflow does not say."""
    ctx = workflows.context(schema, settings)
    if ctx.get("duration"):
        return ctx["duration"] * ctx.get("clips", 1)
    # A workflow that always makes the same length says so in its presets file ({"pricing": {"fixed_seconds": 15}}).
    fixed = (wf["profile"].get("pricing") or {}).get("fixed_seconds")
    if isinstance(fixed, (int, float)) and not isinstance(fixed, bool) and fixed > 0:
        return float(fixed)
    # A workflow whose length is not a duration control names the control in its presets file.
    named = (wf["profile"].get("pricing") or {}).get("seconds")
    control = next((c for c in schema["controls"] if c["id"] == named), None)
    if control:
        try:
            return max(0.0, float((settings.get("values") or {}).get(control["id"], control["default"])))
        except (TypeError, ValueError):
            return None
    if not by_source(wf):
        return None
    # An upscale (or a lip sync) is as long as the video it is made from. For a file the user brought, the browser says how long
    # it is for the estimate, and the job is charged by what the server measures (see create_job).
    given = settings.get("source_seconds")
    if isinstance(given, (int, float)) and not isinstance(given, bool) and 0 < given < 86400:
        return float(given)
    parent = settings.get("parent")
    if user_id and isinstance(parent, int):
        row = await state.db.aone("SELECT filename, context FROM generations WHERE id = ? AND user_id = ? AND kind = 'video'", (parent, user_id))
        if row:
            known = json.loads(row["context"] or "{}").get("duration")
            path = None if known else await offload(storage.here, await offload(state.outputs.folder, user_id) / row["filename"])
            return float(known) if known else (await media.probe(path))["seconds"] if path.is_file() else None
    return None


async def price(state, wf, settings, user_id=None):
    """Time estimate and credit cost of a job with these settings. The cost follows what was asked for, not the time."""
    schema = workflows.describe(wf)
    estimate = workflows.estimate(wf, settings, await offload(state.jobs.history))
    estimate["seconds"] = await billed_seconds(state, wf, schema, settings, user_id)
    chosen = workflows.context(schema, settings)
    estimate["credits"] = await offload(state.credits.cost, wf["id"], estimate["seconds"], chosen)
    # What each other resolution and quality would cost, for the page to show beside them ("1080p · 200 cr").
    others = {"quality": [c["id"] for o in schema["options"] if o["id"] == "quality" for c in o["choices"]],
              "resolution": list(schema["resolutions"]) if "resolution" in chosen else []}
    estimate["choices"] = {group: {str(v): await offload(state.credits.cost, wf["id"], estimate["seconds"], dict(chosen, **{group: v})) for v in values}
                           for group, values in others.items() if values}
    return await offload(guardrails.check_quote, state.db, estimate)   # a length or price that makes no sense is refused


def switched_on(state, workflow_id, user):
    if not state.credits.enabled(workflow_id, user):
        raise HTTPException(400, "This workflow is switched off for now.")


def fit_resolution(state, schema, settings):
    """Make a job at a resolution an admin has not switched off (credits.fit_resolution): the one asked for, or the next
    one allowed, written back into the settings. Returns the note that says so ("" when nothing changed), which is also
    kept as settings["resolution_note"]."""
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    settings.pop("resolution_note", None)
    if schema.get("size"):
        asked = settings.get("resolution") or schema["size"]["resolution"]
    elif "resolution" in roles:
        values = settings["values"] = settings.get("values") if isinstance(settings.get("values"), dict) else {}
        asked = values.get(roles["resolution"]["id"], roles["resolution"]["default"])
    else:
        return ""
    try:
        used, note = state.credits.fit_resolution(schema["id"], asked, schema["resolutions"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    if note:
        if schema.get("size"):
            settings["resolution"] = used
        else:
            settings["values"][roles["resolution"]["id"]] = used
        settings["resolution_note"] = note
    return note


@router.get("/status")
async def status(request: Request, user: dict = Depends(current_user)):
    """Whether the render server answers, and the version of the page files (a tab opened before a change offers to
    reload). Every open tab asks every 15 s: the render server is asked once for all of them, every few seconds."""
    state = request.app.state

    async def ask():
        try:
            stats = await state.comfy.stats()
            state.saw_server(True)
            return {"online": True, "version": stats.get("system", {}).get("comfyui_version")}
        except (httpx.HTTPError, ValueError):
            state.saw_server(False)
            return {"online": False}
    return dict(await health.remembered(state, "status", ask), page=state.page_version())


@router.get("/announcement")
async def announcement(request: Request, user: dict = Depends(current_user)):
    """The message an admin wants every user to see, while it lasts. Empty when there is none. Under maintenance, its
    message, in place of any other."""
    db = request.app.state.db
    closed = await offload(health.maintenance, db)
    if closed:
        return {"text": closed["text"], "level": "warning", "until": None, "maintenance": True}
    return await offload(current_announcement, db)


@router.get("/workflows")
async def list_workflows(request: Request, user: dict = Depends(current_user)):
    state = request.app.state
    listed = [w for w in await state.catalog.listing() if await offload(state.credits.enabled, w["id"], user)]
    return {"workflows": listed, "kinds": KINDS, "default": state.catalog.current(state.settings.default_workflow)}


@router.get("/workflows/{kind}/{name}")
async def get_workflow(kind: str, name: str, request: Request, user: dict = Depends(current_user)):
    schema = workflows.describe(await request.app.state.catalog.load("{}/{}".format(kind, name)))
    # Only the resolutions an admin left on are offered; "resolutions_off" names the others, for a page to say so.
    allowed = await offload(request.app.state.credits.allowed_resolutions, schema["id"], schema["resolutions"])
    schema["resolutions_off"] = [r for r in schema["resolutions"] if r not in allowed]
    schema["resolutions"] = allowed
    return schema


@router.post("/estimate", dependencies=[limited("estimate", 120, 60)])
async def estimate(settings: dict, request: Request, user: dict = Depends(current_user)):
    state = request.app.state
    wf = await state.catalog.load(str(settings.get("workflow", "")))
    await offload(switched_on, state, wf["id"], user)
    note = await offload(fit_resolution, state, workflows.describe(wf), settings)   # priced at the resolution it would be made at
    return dict(await price(state, wf, settings, user["id"]), balance=await offload(state.credits.balance, user["id"]), resolution_note=note)


@router.get("/jobs")
async def list_jobs(request: Request, user: dict = Depends(current_user)):
    return {"jobs": await offload(request.app.state.jobs.snapshot, user["id"])}


def needs_caption(wf, settings, prompt_id):
    """Some image models only work well with a structured JSON caption (a presets file says so with "caption"). A
    prompt in plain words is turned into one by the agent's model, with the instructions the workflow carries, when
    the job is about to render (see JobManager._captions): Generate does not wait for it, and the captions of the jobs
    waiting are written together, so the image model stays loaded between them. The plain prompt stays in
    settings["prompt"], which is what the library shows."""
    rule = wf["profile"].get("caption")
    plain = settings["prompt"].strip()
    if not rule or not plain:
        return
    try:
        if isinstance(json.loads(plain), dict):
            return   # already a caption
    except ValueError:
        pass
    node, _, name = str(rule.get("template", "")).rpartition(":")
    template = (wf["nodes"].get(node) or {}).get("inputs", {}).get(name)
    if not isinstance(template, str):
        raise HTTPException(400, "{}.studio.json names a caption template that is not in the workflow.".format(wf["id"]))
    values = settings.setdefault("values", {})
    ratio = str(values.get(rule.get("ratio")) or wf["nodes"].get(str(rule.get("ratio", "")).rpartition(":")[0], {})
                .get("inputs", {}).get(str(rule.get("ratio", "")).rpartition(":")[2]) or "auto").split(" ")[0]
    settings["caption"] = {"prompt": prompt_id, "template": template, "ratio": ratio}


async def _video_seconds(state, data, filename):
    """How long a video that arrived as bytes is, or None when it can't be read as one."""
    folder = state.storage_dir / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "measure_{}{}".format(uuid.uuid4().hex, Path(filename or "").suffix[:8])
    try:
        path.write_bytes(data)
        return (await media.probe(path))["seconds"] or None
    except media.MediaError:
        return None
    finally:
        path.unlink(missing_ok=True)


@router.post("/jobs", dependencies=[limited("jobs", 30, 60), uploading])
async def create_job(request: Request, user: dict = Depends(current_user)):
    """Multipart form: "settings" (JSON) plus one file per filled reference slot, named "ref:<slot id>".

    A slot can instead reuse a file: {"comfy_name": ...} for one this user already put on the render server,
    or {"asset_id": ...} for one of the user's saved assets.
    """
    state = request.app.state
    form = await request.form(max_files=24, max_fields=64)
    try:
        settings = json.loads(form["settings"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "Missing or broken settings.")
    wf = await state.catalog.load(str(settings.get("workflow", "")))
    await offload(switched_on, state, wf["id"], user)
    schema = workflows.describe(wf)
    settings["workflow"] = wf["id"]   # the id it goes by now, if it was asked for by the id of a workflow it replaced
    slots = workflows.refs_in_use(schema, settings)   # a file for a slot the chosen mode does not read is not sent on

    project_id = settings.get("project_id") or None
    if project_id:   # the user's own project, or one shared with them as a creator or more
        await offload(sharing.require, state.db, user, project_id, "creator")

    # The library item this is made from, if any: the canvas puts the result on the same row.
    parent = settings.get("parent")
    owned = isinstance(parent, int) and await state.db.aone("SELECT 1 FROM generations WHERE id = ? AND user_id = ?", (parent, user["id"]))
    if isinstance(parent, int) and not owned and project_id:   # another member's frame in the same shared project
        with as_everyone():
            owned = await state.db.aone("SELECT 1 FROM generations WHERE id = ? AND project_id = ?", (parent, project_id))
    settings["parent"] = parent if owned else None
    # A result the agent planned as something to reuse is kept in shared memory when it is done: only a type and a name.
    settings["keep"] = memory.clean_keep(settings.get("keep"), wf["id"].split("/", 1)[0])
    settings["shot"] = memory.clean_shot(settings.get("shot"))
    # Where it goes on the canvas: the number of its shot, and a board of references or deliverables (placement.py).
    settings["shot_number"] = placement.clean_shot_number(settings.get("shot_number"))
    settings["board"] = placement.clean_board(settings.get("board"))
    settings["placement_group"] = placement.clean_group(settings.get("placement_group"))
    # The voice track has music or noise under it: the voice is taken out first, when the job runs (jobs._clean_voice).
    settings["clean_voice"] = settings.get("clean_voice") is True and bool(schema["slots"].get("voice_track"))

    # The length of a video the user brought to an upscaler or a lip sync, measured here: it is what the job is charged by.
    videos = {r["id"] for r in schema["refs"] if r["kind"] == "video"} if by_source(wf) else set()
    settings.pop("source_seconds", None)

    async def measure(slot, data, filename):
        if slot in videos:
            settings["source_seconds"] = await _video_seconds(state, data, filename) or settings.get("source_seconds")

    # @names of the project's kit in the prompt ("@Violet at @Bonfire Clearing") go into the free slots that fit them,
    # and the prompt calls them by the words the model ties to those slots.
    prompt_id = next((c["id"] for c in schema["controls"] if c["role"] == "prompt"), None)
    values = settings.get("values") if isinstance(settings.get("values"), dict) else {}
    if prompt_id and "@" in str(values.get(prompt_id) or ""):
        given = {s for s, r in (settings.get("refs") or {}).items() if r} | {k[4:] for k in form.keys() if k.startswith("ref:")}
        values[prompt_id], placed = kit.mentions(schema, values[prompt_id], await offload(kit.entries, state.db, user["id"], project_id), given, slots)
        settings["refs"] = {**(settings.get("refs") or {}), **{slot: {"asset_id": asset} for slot, asset in placed.items()}}

    refs = {}
    for slot, ref in (settings.get("refs") or {}).items():
        if slot not in slots or not isinstance(ref, dict):
            continue
        if ref.get("asset_id"):
            keeper = await offload(kit.keeper_of, state.db, user["id"], project_id) if project_id else user["id"]   # a shared project's kit is its owner's
            with as_everyone() if keeper != user["id"] else contextlib.nullcontext():
                asset = await state.db.aone("SELECT * FROM assets WHERE id = ? AND user_id = ?", (ref["asset_id"], keeper))
            path = asset and await offload(storage.here, state.assets_dir / str(keeper) / asset["filename"])
            if not asset or not path.is_file():
                raise HTTPException(400, "A saved asset used here no longer exists.")
            data = path.read_bytes()
            await measure(slot, data, asset["filename"])
            refs[slot] = {"comfy_name": await upload_reference(state.comfy, asset["filename"], data, db=state.db, user_id=user["id"]),
                          "name": asset["name"]}
        elif ref.get("comfy_name"):
            # Only a file this user put on the render server: another user's file name must not be usable.
            if not await offload(owns_upload, state.db, user["id"], ref["comfy_name"]):
                raise HTTPException(400, "A reference file used here is not one of yours. Add it again.")
            refs[slot] = {"comfy_name": str(ref["comfy_name"]), "name": str(ref.get("name", ""))[:200]}
    kinds = {r["id"]: r["kind"] for r in schema["refs"]}
    labels = {r["id"]: r["label"] for r in schema["refs"]}
    for key, upload in form.multi_items():
        if not key.startswith("ref:") or key[4:] not in slots or not hasattr(upload, "filename"):
            continue
        given, wanted = media_kind(upload.filename), kinds.get(key[4:])
        if wanted and given and given != wanted and not (wanted == "audio" and given == "video"):
            raise HTTPException(400, "{} is not {} file.".format(upload.filename, {"image": "an image", "video": "a video", "audio": "a sound"}[wanted]))
        data = await read_upload(upload)
        await measure(key[4:], data, upload.filename)
        name = await upload_reference(state.comfy, upload.filename, data, upload.content_type, db=state.db, user_id=user["id"])
        refs[key[4:]] = {"comfy_name": name, "name": upload.filename[:200]}
        # Shared memory keeps every file dropped into a job, as an upload of this project, so it can be used again by name.
        try:
            await offload(memory.keep_upload, state.db, state.assets_dir / str(user["id"]), user["id"], project_id, upload.filename,
                               data, given or wanted or "image", labels.get(key[4:], ""))
        except OSError:
            pass   # the job does not depend on the copy
    settings["refs"] = refs

    resolution_note = await offload(fit_resolution, state, schema, settings)   # a resolution switched off is made at the next one allowed
    _, ctx = workflows.build_prompt(wf, dict(settings, clips=1))  # fails here, not in the queue, if a setting is wrong
    ctx = dict(workflows.context(schema, settings), seed=ctx.get("seed"))
    # What the library's details panel shows later: the prompt and each named setting as it was used.
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    values = settings.get("values") or {}
    if "prompt" in roles:
        settings["prompt"] = str(values.get(roles["prompt"]["id"], roles["prompt"]["default"]) or "")
        needs_caption(wf, settings, roles["prompt"]["id"])
    settings["details"] = [[c["label"].split(" (")[0], values.get(c["id"], c["default"])] for c in schema["controls"] if not c["role"]]
    settings["workflow_title"] = schema["title"]
    quote = await price(state, wf, settings, user["id"])
    name = str(settings.get("name") or wf["id"].split("/", 1)[1]).strip()[:80]
    over = await offload(state.credits.cap_problem, user["id"], quote["credits"])
    if over:
        raise HTTPException(429, over)
    run_of = settings.get("run_of") if isinstance(settings.get("run_of"), str) and runs.RUN.match(settings["run_of"]) else ""
    settings["run_of"] = run_of
    over = await offload(guardrails.run_problem, state.db, user["id"], run_of, quote["credits"])   # the most one run may use
    if over:
        raise HTTPException(429, over)
    if not await offload(state.credits.charge, user["id"], quote["credits"], "generation"):
        raise HTTPException(402, "This needs {} credits and you have {}. Ask an admin for more.".format(
            quote["credits"], await offload(state.credits.balance, user["id"])))
    job_id = await offload(state.jobs.add, user["id"], name, wf["id"], settings, workflows.summary(schema, ctx),
                            quote["minutes"] * 60 if quote["minutes"] else None, quote["credits"], project_id, quote["seconds"])
    return {"id": job_id, "credits": quote["credits"], "resolution_note": resolution_note}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    if not await offload(request.app.state.jobs.remove, user["id"], job_id):
        raise HTTPException(404, "No such job.")
    return {"ok": True}


@router.get("/ref-preview")
async def ref_preview(name: str, request: Request, user: dict = Depends(current_user)):
    """Show a reference of this user's that is already in ComfyUI's input folder (used by "Re-run")."""
    if not await offload(owns_upload, request.app.state.db, user["id"], name):
        raise HTTPException(404, "No such file.")
    response = await request.app.state.comfy.view(name, "", "input")
    if response.status_code != 200:
        await response.aclose()
        raise HTTPException(404, "ComfyUI no longer has this file.")

    async def body():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
    return StreamingResponse(body(), media_type=response.headers.get("content-type", "application/octet-stream"))


@router.websocket("/events")
async def events(ws: WebSocket):
    state = ws.app.state
    token = ws.cookies.get(COOKIE)
    user = await offload(user_for_token, state.db, token)
    if user is None or not same_origin(ws):   # another site's page must not open a connection with the user's cookie
        await ws.close(code=4401)
        return
    await ws.accept()
    state.hub.add(user["id"], ws)
    try:
        await ws.send_text(await state.db.offload(state.live_message, user["id"]))
        while True:
            # The page tells which part of the studio it shows, for the admin's list of who is online. It also asks
            # now and then whether the connection still works ("ping"), and is answered with where its jobs stand.
            try:
                said = json.loads(await ws.receive_text())
                if said.get("ping"):
                    # The session is checked again: one signed out, ended by an admin or of a disabled account stops here.
                    if await offload(user_for_token, state.db, token) is None:
                        await ws.close(code=4401)
                        return
                    await ws.send_text(await state.db.offload(state.live_message, user["id"]))
                    continue
                page = str(said.get("page", ""))
            except (ValueError, AttributeError):
                continue
            if PAGE.match(page):
                state.hub.set_page(ws, page)
    except WebSocketDisconnect:
        pass
    finally:
        state.hub.discard(user["id"], ws)
