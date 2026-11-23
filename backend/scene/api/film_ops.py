"""The film operations of the canvas and the agent: a timeline joined into one video, a cut assembled, a sound laid under
a video, motion graphics priced and rendered, and what the agent's film tool needs (the fields of render_html and ffmpeg,
the page builder's guides, the takes a step names, waiting for a job). Moved out of api/workspace.py as they were;
workspace imports these names back (plans.py and the tests use `workspace.assemble`, `workspace.motion_render`, ...)."""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import agent, credits, edits, media, motion, sequence, skills
from ..db import as_everyone, offload
from .deps import costly, current_user

router = APIRouter(prefix="/api", tags=["film-ops"])


def _workspace():
    """api/workspace.py, read when a request comes, for the helpers these routes share with it (the project a request
    names, the model picked, the long answer kept alive): it imports this module itself, so not at the top."""
    from . import workspace
    return workspace


MAX_CLIPS = 50
MOTION_WORKFLOW = credits.MOTION   # what a rendered motion graphic is filed and priced under
FILM_WAIT = 900          # seconds the agent waits for one film operation (a long film joined, a retime) before giving up


@router.post("/timeline/export", dependencies=[costly("render")])
async def export_timeline(body: dict, request: Request, user: dict = Depends(current_user)):
    """Queue a job that joins the timeline's clips into one video for the library. Costs no credits: it needs no GPU."""
    state = request.app.state
    clips = body.get("clips") or []
    if not isinstance(clips, list) or not all(isinstance(clip, dict) for clip in clips):
        raise HTTPException(400, "The timeline's clips are not in the expected form.")
    if not 1 <= len(clips) <= MAX_CLIPS:
        raise HTTPException(400, "Put between 1 and {} clips on the timeline.".format(MAX_CLIPS))
    project_id = await offload(_workspace()._project_id, request, user, body.get("project_id")) or None
    parts = []
    for clip in clips:
        row = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind = 'video'",
                           (clip.get("id"), user["id"]))
        if row is None:
            raise HTTPException(404, "A clip on the timeline is no longer in your library.")
        if not (await offload(state.outputs.folder, user["id"]) / row["filename"]).is_file():
            raise HTTPException(404, "The file of {} is missing from storage.".format(row["name"]))
        try:
            parts.append({"id": row["id"], "start": float(clip.get("start") or 0), "end": float(clip.get("end") or 0)})
        except (TypeError, ValueError):
            raise HTTPException(400, "The start and end of {} must be numbers.".format(row["name"]))
    # The item an edit was cut from, if the caller names one of the clips: the canvas puts the result on its row.
    parent = body.get("parent") if body.get("parent") in [part["id"] for part in parts] else None
    name = str(body.get("name") or "").strip()[:80] or "Timeline"
    job_id = await offload(state.jobs.add, user["id"], name, edits.TIMELINE, {"workflow_title": "Timeline export", "clips": parts, "parent": parent},
                            "1 clip joined" if len(parts) == 1 else "{} clips joined".format(len(parts)), None, 0, project_id)
    return {"job": job_id, "name": name}


@router.post("/edit/assemble", dependencies=[costly("render")])
async def assemble(body: dict, request: Request, user: dict = Depends(current_user)):
    """Queue the finished cut: the clips in order, a title card and an end card, music under it. Costs no credits.
    Body: {"name"?, "clips": [{"id", "start"?, "end"?, "fade"?: crossfade in from the clip before}], "music"?: audio item id,
    "title"?, "end"?: {"heading", "text"},
    "look"?, "shape"?, "project_id"?}."""
    state = request.app.state
    clips = body.get("clips") if isinstance(body.get("clips"), list) else []
    if not 1 <= len(clips) <= MAX_CLIPS:
        raise HTTPException(400, "Put between 1 and {} clips in the cut.".format(MAX_CLIPS))
    folder = await offload(state.outputs.folder, user["id"])
    parts, missing = [], []
    for n, clip in enumerate(clips):
        clip = clip if isinstance(clip, dict) else {}
        row = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind = 'video'", (clip.get("id"), user["id"]))
        if row is None or not (folder / row["filename"]).is_file():
            missing.append(str(clip.get("name") or "Clip {}".format(n + 1)))   # every clip looked at: all are named
            continue
        try:
            parts.append({"id": row["id"], "start": float(clip.get("start") or 0), "end": float(clip.get("end") or 0), "fade": clip.get("fade") is True,
                          "name": str(clip.get("name") or row["name"] or "")[:80]})
        except (TypeError, ValueError):
            raise HTTPException(400, "The start and end of {} must be numbers.".format(row["name"]))
    if missing:
        from ..plans import cut_not_ready
        raise HTTPException(404, cut_not_ready(missing))
    music = None
    if body.get("music"):
        row = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind = 'audio'", (body["music"], user["id"]))
        if row is None or not (folder / row["filename"]).is_file():
            raise HTTPException(404, "The music of the cut is no longer in your library.")
        music = row["id"]

    def card(kind):
        given = body.get(kind) if isinstance(body.get(kind), dict) else None
        scenes = sequence.clean_scenes([{"kind": kind, "heading": given.get("heading"), "text": given.get("text"), "seconds": given.get("seconds") or None}]) if given else []
        return scenes[0] if scenes else None

    settings = {"workflow_title": "Final cut", "clips": parts, "music": music, "title": card("title"), "end": card("end"),
                "look": body.get("look") if body.get("look") in sequence.LOOKS else "dark",
                "shape": body.get("shape") if body.get("shape") in agent.ORIENTATIONS else "landscape", "parent": parts[0]["id"]}
    name = " ".join(str(body.get("name") or "").split())[:80] or "Final cut"
    facts = "{} {}{}{}{}".format(len(parts), "shot" if len(parts) == 1 else "shots", " · title card" if settings["title"] else "",
                                 " · music" if music else "", " · end card" if settings["end"] else "")
    project_id = await offload(_workspace()._project_id, request, user, body.get("project_id")) or None
    return {"job": await offload(state.jobs.add, user["id"], name, edits.ASSEMBLE, settings, facts, None, 0, project_id), "name": name}


@router.post("/edit/sound", dependencies=[costly("render")])
async def add_sound(body: dict, request: Request, user: dict = Depends(current_user)):
    """Queue a job that puts one of the user's sounds on one of their videos, for the library. Costs no credits."""
    state = request.app.state
    rows = {}
    for key, kind, what in (("video", "video", "a video"), ("audio", "audio", "a sound")):
        rows[key] = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind = ?", (body.get(key), user["id"], kind))
        if rows[key] is None:
            raise HTTPException(400, "Choose {} from your library.".format(what))
    folder = await offload(state.outputs.folder, user["id"])
    if not (folder / rows["video"]["filename"]).is_file() or \
            not (folder / rows["audio"]["filename"]).is_file():
        raise HTTPException(404, "A file is missing from storage.")
    replace = body.get("replace") is True
    project_id = await offload(_workspace()._project_id, request, user, body.get("project_id")) or rows["video"]["project_id"]
    placed = {}   # the shots it belongs to and its board, for the canvas (placement.py)
    _workspace().planned_fields(placed, body, [])
    name = (" ".join(str(body.get("name") or "").split()) or "{} with sound".format(rows["video"]["name"]))[:80]
    job_id = await offload(state.jobs.add, 
        user["id"], name, edits.SOUND,
        {"workflow_title": "Sound added", "video": rows["video"]["id"], "audio": rows["audio"]["id"], "replace": replace,
         "prompt": json.loads(rows["video"]["settings"]).get("prompt", ""), "parent": rows["video"]["id"], **placed},
        "{} {} {}".format(rows["audio"]["name"], "in place of the sound of" if replace else "under", rows["video"]["name"]), None, 0, project_id)
    return {"job": job_id, "name": name}


@router.get("/motion/templates")
async def motion_templates(request: Request, user: dict = Depends(current_user)):
    """The motion templates and whether this machine can render them."""
    return {**motion.status(request.app.state.settings.node_path), "templates": motion.templates()}


@router.post("/motion/scenes", dependencies=[costly("motion")])
async def motion_scenes(body: dict, request: Request, user: dict = Depends(current_user)):
    return await _workspace()._patient(_motion_scenes(body, request, user))


async def _motion_scenes(body, request, user):
    """Have the agent's model write a whole motion graphics video as scenes, from what it is about. Nothing is
    rendered: the scenes go back to the form, where they can be changed before Render."""
    about = str(body.get("about") or "").strip()[:2000]
    if not about:
        raise HTTPException(400, "Say what the video is about first.")
    await offload(_workspace()._project_id, request, user, body.get("project_id"))   # only in a project the user may work in
    written = await request.app.state.agent.write_scenes(about, **_workspace()._model(body))
    try:
        written["scenes"] = sequence.clean_scenes(written["scenes"])
    except sequence.SequenceError:
        raise HTTPException(400, "The model wrote no scenes. Try again, or add the scenes yourself.")
    return written


async def _motion_price(state, user, body):
    """(seconds, credits) of the motion graphic this body asks for: it is priced by its length, at one rate when it
    is drawn on its own and at a lower one when it is laid over a video the user has. Refuses, as the render would,
    a body that cannot be rendered."""
    seconds, priced_as = await _motion_seconds(state, user, body)
    return seconds, await offload(state.credits.cost, priced_as, seconds)


async def _motion_seconds(state, user, body):
    if "scenes" in body:
        return sum(scene["seconds"] for scene in sequence.clean_scenes(body.get("scenes"))), MOTION_WORKFLOW
    template = next((t for t in motion.templates() if t["id"] == body.get("template")), None)
    if template is None:
        raise HTTPException(404, "There is no such motion template.")
    values = motion.clean(template, body.get("values") if isinstance(body.get("values"), dict) else {})
    if template["needs"] != "video":
        return float(values.get("seconds", 5)), MOTION_WORKFLOW
    row = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind = 'video'", (body.get("source"), user["id"]))
    if row is None:
        raise HTTPException(400, "Select a video on the canvas first: {} is laid over a video.".format(template["title"].lower()))
    source = await offload(state.outputs.folder, user["id"]) / row["filename"]
    if not source.is_file():
        raise HTTPException(404, "The file of {} is missing from storage.".format(row["name"]))
    return (await media.probe(source))["seconds"], credits.OVERLAY


@router.post("/motion/estimate")
async def motion_estimate(body: dict, request: Request, user: dict = Depends(current_user)):
    """What a motion graphic would cost. Nothing is rendered or charged."""
    state = request.app.state
    seconds, cost = await _motion_price(state, user, body)
    return {"seconds": round(seconds, 1), "credits": cost, "balance": await offload(state.credits.balance, user["id"])}


@router.post("/motion/render", dependencies=[costly("render")])
async def motion_render(body: dict, request: Request, user: dict = Depends(current_user)):
    """Queue the render of a motion graphic for the library. It is charged by its length now, and the queue gives
    the credits back if the render fails or is cancelled."""
    state = request.app.state
    seconds, cost = await _motion_price(state, user, body)   # refuses what can't be rendered
    project_id = await offload(_workspace()._project_id, request, user, body.get("project_id")) or None
    if "scenes" in body:   # a video made of scenes of words, as the agent plans them
        scenes = sequence.clean_scenes(body.get("scenes"))
        words = [scene["heading"] or scene["text"] for scene in scenes]
        name = (" ".join(str(body.get("name") or "").split()) or words[0])[:80]
        settings = {"workflow_title": "Motion graphics", "scenes": scenes,
                    "look": body.get("look") if body.get("look") in sequence.LOOKS else "dark",
                    "shape": body.get("shape") if body.get("shape") in motion.SHAPES else "landscape",
                    "prompt": " / ".join(words)[:600], "parent": None}
        summary = "Motion graphics · {}".format("1 scene" if len(scenes) == 1 else "{} scenes".format(len(scenes)))
    else:                  # one of the templates, on its own or over a video
        template = next(t for t in motion.templates() if t["id"] == body.get("template"))
        values = motion.clean(template, body.get("values") if isinstance(body.get("values"), dict) else {})
        row = await state.db.aone("SELECT id, name FROM generations WHERE id = ? AND user_id = ? AND kind = 'video'",
                           (body.get("source"), user["id"])) if template["needs"] == "video" else None
        name = (values.get("title") or template["title"])[:80]
        settings = {"workflow_title": "Motion graphics · " + template["title"], "template": template["id"], "values": values,
                    "prompt": " · ".join(str(values[key]) for key in ("title", "subtitle") if values.get(key)),
                    "parent": row["id"] if row else None}
        summary = template["title"] + (" over " + row["name"] if row else "")
    over = await offload(state.credits.cap_problem, user["id"], cost)
    if over:
        raise HTTPException(429, over)
    if not await offload(state.credits.charge, user["id"], cost, "generation", note="Motion graphics"):
        raise HTTPException(402, "This needs {} credits and you have {}. Ask an admin for more.".format(cost, await offload(state.credits.balance, user["id"])))
    job_id = await offload(state.jobs.add, user["id"], name, MOTION_WORKFLOW, settings, summary, None, cost, project_id, seconds)
    return {"job": job_id, "name": name, "credits": cost}


# The fields of the render_html and ffmpeg tools, as the film tool's html and ffmpeg ops take them (film.queue).
RENDER_FIELDS = ("html", "width", "height", "duration", "project", "fps", "format", "frames", "media", "review")
FFMPEG_FIELDS = ("argv", "inputs", "sidecars", "outputs", "timeout", "reason")

BUILD_GUIDES = 6             # guides the director may add to one page_build call
BUILD_GUIDE_CHARS = 25_000   # characters of each
BUILD_FILES_CHARS = 160_000  # characters of the project's files the page writer is shown
BUILD_BRIEF_CHARS = 30_000


def _hyperframes_guide(path):
    """One of HyperFrames' own guides, presets and examples ("@hyperframes/hyperframes/references/motion.md"): its text,
    the list of a folder's entries, or None when there is no such text file."""
    path = str(path or "").strip()
    if not path.startswith("@hyperframes"):
        return None
    inner = path[len("@hyperframes"):].strip("/")
    base = motion.SKILLS_DIR.resolve()
    target = (base / inner).resolve() if inner else base
    if base not in (target, *target.parents) or not target.exists():
        return None
    if target.is_dir():
        return sorted(p.relative_to(base).as_posix() + ("/" if p.is_dir() else "") for p in target.iterdir())
    if target.suffix.lower() not in (".md", ".html", ".css", ".js", ".json", ".txt"):
        return None
    return target.read_text(encoding="utf-8", errors="replace")


_guides = {}


def _builder_guides():
    """What the page writer always follows (its system prompt, the same in every call, so it is read from the cache):
    the studio's part of the hyperframes skill (the media and the contract), then HyperFrames' format.md and motion.md."""
    if "text" not in _guides:
        skill = (skills.find("hyperframes") or {}).get("text") or ""
        start, end = skill.find("Media in a project"), skill.find("## The work loop")
        parts = ["## The studio's rules\n\n" + skill[start:end].strip()] if 0 <= start < end else []
        if motion.sound_effects():   # the only names there are: a guessed one is not in the project
            parts.append("The sound effects, there by these names only: " + ", ".join("assets/sfx/" + n for n in motion.sound_effects()))
        for name in ("format.md", "motion.md"):
            words = _hyperframes_guide("@hyperframes/hyperframes/references/" + name)
            if isinstance(words, str):
                parts.append("## HyperFrames' {}\n\n{}".format(name, words))
        _guides["text"] = "\n\n".join(parts)
    return _guides["text"]


async def _named_videos(state, user, project, step):
    """The videos an editing or assemble step names by library id ("uses" in order, then "source"), of this project (or,
    out of any project, the user's own), as the selection gives them: {"id", "name", "seconds"}. [] when it names none:
    the selected videos are used then. So "join the takes you picked" works without selecting them on the canvas."""
    uses = step.get("uses") if isinstance(step.get("uses"), list) else []
    ids = [u.get("item") for u in uses if isinstance(u, dict)] + [step.get("source")]
    ids = list(dict.fromkeys(i for i in ids if isinstance(i, int) and not isinstance(i, bool) and i > 0))
    if not ids:
        return []
    marks = ", ".join("?" * len(ids))
    if project:
        with as_everyone():   # a shared project: what its members made too
            rows = await state.db.aall("SELECT id, user_id, name, filename, context FROM generations WHERE kind = 'video' AND project_id = ? AND id IN ("
                                + marks + ")", (project, *ids))
    else:
        rows = await state.db.aall("SELECT id, user_id, name, filename, context FROM generations WHERE kind = 'video' AND user_id = ? "
                            "AND project_id IS NULL AND id IN (" + marks + ")", (user["id"], *ids))
    found = {}
    for row in rows:   # measured, as an attached video is: what the editing tools cut by
        path = await offload(state.outputs.folder, row["user_id"]) / row["filename"]
        seconds = (await media.probe(path))["seconds"] if path.is_file() else 0
        if seconds:
            found[row["id"]] = {"id": row["id"], "name": row["name"], "seconds": round(seconds, 2)}
    return [found[i] for i in ids if i in found]


async def _finished(state, job_id, timeout=FILM_WAIT):
    """The job, once it is no longer waiting or running (or as it is when the time is up)."""
    deadline = time.monotonic() + timeout
    while True:
        job = await state.db.aone("SELECT id, status, error FROM jobs WHERE id = ?", (job_id,))
        if job["status"] not in ("queued", "running") or time.monotonic() > deadline:
            return job
        await asyncio.sleep(0.4)
