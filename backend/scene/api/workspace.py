"""The canvas and the agent: arranging finished work, queueing edits and motion graphics, and planning new work."""

import asyncio
import contextlib
import json
import math
import random
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import aftercare, agent, camera, guardrails, claude, conversations, content_check, core, craft_library, credits, edits, internals, kit, media, memory, motion, phonetic, preferences, presets, recall, review, \
    pages, runs, placement, sessions, sharing, skills, traces, web
from ..db import as_everyone, offload
from ..comfy import workflows
from ..security import LIMITS
from .agent_threads import (  # noqa: F401 (the names are workspace's too: tests and plans.py use them here)
    THREAD_NOT_KEPT, _hosted_claude, _keep_thread, _missed_text, _said, _session_of, _skill_sending, _skill_sent, _thread,
    _thread_run, compact, forget_sessions, row_model)
from .film_ops import (  # noqa: F401 (the names are workspace's too: plans.py and the tests use them here)
    BUILD_BRIEF_CHARS, BUILD_FILES_CHARS, BUILD_GUIDE_CHARS, BUILD_GUIDES, FFMPEG_FIELDS, FILM_WAIT, MAX_CLIPS, MOTION_WORKFLOW,
    RENDER_FIELDS, _builder_guides, _finished, _hyperframes_guide, _motion_price, _motion_seconds, _named_videos, add_sound,
    assemble, export_timeline, motion_estimate, motion_render, motion_scenes, motion_templates)
from .deps import allowed as within_limit, costly, current_user, project_ref
from .studio import fit_resolution, price, unreachable

router = APIRouter(prefix="/api", tags=["workspace"])

# canvas: where frames sit. agent: its tabs. cast: the project's pinned references.
KINDS = ("canvas", "agent", "cast")
SHOT_LENGTHS = list(range(4, 16))
# agent-<id>: the conversation of one agent tab. The "agent" board lists the tabs: their names, ids and credits.
AGENT_TAB = re.compile(r"^agent-[a-z0-9]{1,16}$")


def _board_kind(kind):
    if kind not in KINDS and not AGENT_TAB.match(kind):
        raise HTTPException(404, "No such board.")   # the lengths a shot can be given on an approval card, in seconds
MAX_BOARD_BYTES = 2_000_000   # an agent tab keeps its whole conversation
CHECKED_SKILL = 4_000        # a skill longer than this, or one the user named with /command, is checked before the agent plans
STATE_PAGE = 25          # leaves of a run's state the agent is given at a time
LIVE_EVERY = 1.0         # seconds between looks at what the agent's tools did while it works
# A proxy in front of the studio (the Cloudflare tunnel) closes a request that sends nothing for 100 seconds, and a
# Claude can be quiet longer than that (reading a long skill, many tool calls in one turn). So a slow answer
# sends a sign of life every KEEP_ALIVE seconds; one that comes within PATIENT seconds is sent as it is.
RUN_STOPPED = "I stopped before I planned the next step (what I was thinking is above). Say “go” and I will carry on from there."
KEEP_ALIVE = 15
PATIENT = 20
SLASH = re.compile(r"(?:^|(?<=\s))/([a-z0-9][a-z0-9-]*)(?=\s|$)")   # a /skill-id standing on its own, anywhere in a message
RUN_ITEMS = 5000         # library items a long run's steps may name by id
MAX_SELECTION = 24       # attached items read with one message (a long skill takes a cast, props and places at once)
TEXT_OPENING = 400       # characters of an attached text shown with it, so it can be told for what it is
TEXT_PAGE = 6000         # characters of a document the agent reads at a time
# What the studio can do beside its workflows, for the check of a skill before it starts.
STUDIO_ABILITY = (
    "Editing: trim, split, join, sound on a video, the finished cut (assemble). Motion graphics and titles drawn in the studio. "
    "Frame-exact film operations on this machine, free, as the agent's \"film\" tool: a reference image at 1500 px, a slice of an "
    "audio by frames, a timing track video of blocks, a clip trimmed or stretched to an exact frame count, a clip retimed so lips meet "
    "the master's words, proof sheets, subtitles burned in (house style), clips joined on the master audio, and the spans where speech "
    "is heard in a voice track. A run state store (state_read, state_write, state_check) kept per conversation, written a leaf or a "
    "whole folder at a time. Reading a transcript (a transcription workflow's JSON, or an .srt the user uploads) into the state with "
    "its times exact, and working out every shot's frames from it (transcript, timing). Bringing pictures, clips and sounds in from "
    "links on other sites (import_url). Reading a script or document the user attached (read_text; Word files arrive as "
    "their text). Questions to the user with two to four buttons; tables of pictures in a reply. A run goes on "
    "by itself when its steps are made. A permission under the Agent box lets plans run "
    "without waiting for Approve. Looking at pictures and "
    "clips, reviewing results, remembering assets. HyperFrames: motion graphics pages the agent designs itself (the render_html "
    "tool: titles, kinetic type, explainers, captions, stat and chart cards, lower thirds, end cards, layouts over "
    "pictures and clips, see-through overlays), drawn to video on this machine, free, a whole motion graphics video with no "
    "script needed. ffmpeg commands the agent writes itself (the ffmpeg tool: any cut, join, transition, grade, "
    "speed, punch-in, overlay, mix, duck, caption or measurement). An asset sheet (CSV of names and image links) attached is "
    "brought into NeuralCore by itself. Not here: other programs or scripts than these, other models than the workflows listed.")


def _project_id(request, user, project, need="creator"):
    """0 stands for "no project"; any other id must be a project of the user's, or one shared with them where their
    role allows `need` (most of what is done here makes something: a creator)."""
    project = project_ref(project)
    if not project:
        return 0
    return sharing.require(request.app.state.db, user, project, need)["id"]


def _board_owner(request, user, project, kind, need):
    """(project id, whose board it is). A project's canvas and cast are its owner's, which everyone in a shared
    project opens; an agent tab is the user's own."""
    project_id = _project_id(request, user, project, need)
    if not project_id or AGENT_TAB.match(kind) or kind == "agent":
        return project_id, user["id"]
    return project_id, sharing.require(request.app.state.db, user, project_id, need)["owner_id"]


@router.get("/boards/{kind}")
async def get_board(kind: str, request: Request, project: int = 0, user: dict = Depends(current_user)):
    """The saved canvas layout of one project (or of the items in no project)."""
    _board_kind(kind)
    project_id, owner = await offload(_board_owner, request, user, project, kind, "viewer")
    if AGENT_TAB.match(kind):   # an agent tab's conversation, kept in rows of its own (conversations.py)
        return {"data": await offload(conversations.read, request.app.state.db, owner, project_id, kind[len("agent-"):]) or {}}
    with as_everyone():   # the owner's board of a shared project, now that the user is found to be in it
        row = await request.app.state.db.aone("SELECT data FROM boards WHERE user_id = ? AND project_id IS NOT DISTINCT FROM NULLIF(?, 0) AND kind = ?", (owner, project_id, kind))
    return {"data": json.loads(row["data"]) if row else {}}


@router.put("/boards/{kind}")
async def save_board(kind: str, body: dict, request: Request, user: dict = Depends(current_user)):
    _board_kind(kind)
    data = json.dumps(body.get("data") or {})
    if len(data) > MAX_BOARD_BYTES:
        raise HTTPException(400, "This is too large to save.")
    project_id, owner = await offload(_board_owner, request, user, body.get("project"), kind, "creator")
    if AGENT_TAB.match(kind):
        await offload(conversations.write, request.app.state.db, owner, project_id, kind[len("agent-"):], body.get("data") or {})
        return {"ok": True}
    with as_everyone():
        await request.app.state.db.arun(
            "INSERT INTO boards (user_id, project_id, kind, data, updated) VALUES (?, NULLIF(?, 0), ?, ?, ?) "
            "ON CONFLICT(user_id, project_id, kind) DO UPDATE SET data = excluded.data, updated = excluded.updated",
            (owner, project_id, kind, data, time.time()))
    return {"ok": True}


@router.delete("/boards/{kind}")
async def delete_board(kind: str, request: Request, project: int = 0, user: dict = Depends(current_user)):
    """Forget the conversation of an agent tab the user deleted, and its Claude sessions. Other boards are not deleted
    this way."""
    if not AGENT_TAB.match(kind):
        raise HTTPException(404, "No such board.")
    state = request.app.state
    await offload(conversations.delete, state.db, user["id"], await offload(_project_id, request, user, project, "viewer"),
                  kind[len("agent-"):])
    await forget_sessions(state, user, kind[len("agent-"):])   # its Claude sessions (agent_threads.py)
    return {"ok": True}


@router.post("/agent/session/compact", dependencies=[costly("agent")])
async def compact_session(body: dict, request: Request, user: dict = Depends(current_user)):
    """Compact an agent tab's Claude session now (the user's "Compact now"): Claude Code sums up the conversation so far
    and goes on from that, in the same session. Body: {"run", "project_id"}. Returns {"context"} as a plan gives it."""
    return await _patient(_compact_session(body, request, user))


async def _compact_session(body, request, user):
    project = await offload(_project_id, request, user, body.get("project_id"))
    return await compact(request.app.state, user, body, project)


# ---------------------------------------------------------------- the cast of a project

@router.get("/cast")
async def get_cast(request: Request, project: int = 0, workflow: str = "", user: dict = Depends(current_user)):
    """The always-on entries of a project's kit (what the cast was), and, for a workflow, which of its reference slots
    they fill: [{"asset", "name", "slot", "label", "kind", "role", "item_kind", "said_as"}]."""
    state = request.app.state
    on = await offload(kit.always, state.db, user["id"], await offload(_project_id, request, user, project) or None)
    found = {"always": [memory.kit_row(e) for e in on], "fills": []}
    if workflow and on:
        found["fills"] = kit.fills(workflows.describe(await state.catalog.load(workflow)), on)
    return found


# ---------------------------------------------------------------- motion graphics


# ---------------------------------------------------------------- agent

@router.get("/agent/status")
async def agent_status(request: Request, user: dict = Depends(current_user)):
    try:
        # "model" is the one used when the user has not picked another; "models" is what they can pick from.
        brain = request.app.state.agent
        models = await brain.models()
        credits = request.app.state.credits
        prices = await offload(credits.llm_prices)
        return {"online": True, "model": await brain.pick_model(), "models": models, "hosted": [{"id": s["id"], "name": s["name"]} for s in brain.services.values()],
                "prices": {m: prices[m] for m in models if m in prices},   # credits per message; a model not listed is free
                "by_tokens": [m for m in models if m not in prices and credits.token_prices(m)],   # charged by the tokens they use
                # the effort levels each Claude model takes, and the one it uses when none is picked
                "efforts": {m: dict(zip(("levels", "default"), claude.efforts(m))) for m in models if m.startswith("claude/")}}
    except agent.AgentError as error:
        return {"online": False, "detail": str(error)}


def _model(body):
    """The model the user picked in the agent panel, as a keyword for the agent's calls; nothing when they picked none."""
    picked = body.get("model")
    return {"model": picked[:120]} if isinstance(picked, str) and picked.strip() else {}


def _structured(value, empty="{}"):
    """A tool's field of structured data (an object or a list): as the model gives it now, or as JSON text, which the
    tools took before they had typed schemas (a session begun then still sends it). Raises ValueError."""
    return value if isinstance(value, (dict, list)) else json.loads(value or empty)


def _project_name(state, project):
    """"Film › Episode 1" for a module, "Film" for a project, "" for all work."""
    if not project:
        return ""
    with as_everyone():
        row = state.db.one("SELECT p.name, pp.name AS parent FROM projects p LEFT JOIN projects pp ON pp.id = p.parent_id WHERE p.id = ?",
                           (project,))
    return "" if row is None else "{} › {}".format(row["parent"], row["name"]) if row["parent"] else row["name"]


def _soon(work):
    """Run `work` (a coroutine) beside the request; a failure is printed, never raised."""
    async def run():
        try:
            await work
        except Exception as error:
            print("Not done beside the request: {}".format(error))
    asyncio.get_running_loop().create_task(run())


def _looks(state, body):
    """The models that look at pictures for a message: {"describe", "review"}. The Claude model the user picked looks
    itself, its quick one describing; with none picked, the agent's usual ones do."""
    picked = _model(body).get("model")
    if not picked:
        return {"describe": None, "review": None}
    return {"describe": state.agent.helper(picked), "review": picked}


# ---------------------------------------------------------------- shared memory

@router.get("/memory")
async def get_memory(request: Request, project: int = 0, user: dict = Depends(current_user)):
    """A project's kit, as the panel of before read it ({"assets": the kit's entries, "uploads": []}); the kit's own
    endpoints are /api/kit. The agent's model first looks at a few pictures it has not described."""
    state = request.app.state
    project = await offload(_project_id, request, user, project)
    await memory.describe_missing(state, user["id"], await offload(memory.book, state.db, user["id"], project or None), limit=6)
    found = await offload(memory.panel, state.db, user["id"], project or None)
    found["skills"] = [{"id": s["id"], "title": s["title"], "version": s["version"]} for s in skills.load()]
    return found


@router.get("/skills")
async def list_skills(user: dict = Depends(current_user)):
    """Every skill the agent can use, with its recipe, for the Skills section. Read-only: skills are files on the server.

    A skill is triggered on its own when the message matches it, or by the user with /<id> at the start of a message."""
    return {"skills": [{"id": s["id"], "title": s["title"], "version": s["version"], "desc": s["desc"],
                        "text": s["text"], "words": s["words"].pattern, "next": s["next"], "craft": s["craft"]} for s in skills.load()]}


ENTRY_FIELDS = ("look_of", "variant", "from_scene", "palette", "relations")   # book_save's JSON fields of an entry (kit.update)
SCRIPT_CHARS = 200_000   # the most of a script book_save keeps from text, as one typed into NeuralCore (api/kit.SCRIPT_CHARS)


def _is_admin(user):
    return str(user.get("role") or "") == "admin" and not user.get("viewing")


@router.get("/skills/drafts")
async def list_skill_drafts(user: dict = Depends(current_user)):
    """The skills drafted in chats that wait for an admin: an admin sees every one, anyone else their own. They are
    published in the admin console (POST /api/admin/skills/drafts/{id}/publish), never here."""
    found = skills.drafts()
    return {"drafts": found if _is_admin(user) else [d for d in found if d["by"] == user["id"]], "can_publish": False}


@router.post("/skills/drafts/{draft_id}/publish")
async def publish_skill_draft(draft_id: str, user: dict = Depends(current_user)):
    """Refused on the studio's site: a published skill changes what the agent does for everyone, so it is an admin's
    change, made in the admin console, which asks for its own sign-in (and two-step sign-in, when the studio asks it of
    admins) and writes it in the audit log."""
    raise HTTPException(403, "Skills are published in the admin console (Skills, Drafts)." if _is_admin(user)
                        else "Only an admin can publish a skill.")


@router.delete("/skills/drafts/{draft_id}")
async def discard_skill_draft(draft_id: str, user: dict = Depends(current_user)):
    """Throw a draft away: an admin, or whoever drafted it."""
    draft = next((d for d in skills.drafts() if d["id"] == draft_id), None)
    if draft is None:
        raise HTTPException(404, "No such draft.")
    if not _is_admin(user) and draft["by"] != user["id"]:
        raise HTTPException(403, "Only an admin or whoever drafted it can throw it away.")
    skills.discard(draft_id)
    return {"ok": True}


@router.get("/agent/preferences")
async def agent_preferences(request: Request, user: dict = Depends(current_user)):
    """The user's own settings of the agent: {"retry_once": a failed shot is made again once by itself (off by default),
    "model" (null: the studio's default), "effort": {model: level}, "permission": "all", "videos" or "always" (whether
    a plan runs without Approve; the server holds an automatic approval to it), "explain": {conversation: bool}}."""
    db = request.app.state.db
    return {"retry_once": await offload(aftercare.retry_on, db, user["id"]), **await offload(preferences.agent, db, user["id"])}


@router.put("/agent/preferences")
async def save_agent_preferences(body: dict, request: Request, user: dict = Depends(current_user)):
    """Any of the fields GET gives; the others stay as they are."""
    db = request.app.state.db
    if isinstance(body.get("retry_once"), bool):
        await offload(aftercare.set_retry, db, user["id"], body["retry_once"])
    try:
        kept = await offload(preferences.set_agent, db, user["id"], body) if set(body) - {"retry_once"} else await offload(preferences.agent, db, user["id"])
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {"retry_once": await offload(aftercare.retry_on, db, user["id"]), **kept}


@router.get("/preferences")
async def studio_preferences(request: Request, user: dict = Depends(current_user)):
    """The user's choices in the studio's pages: {"workflows": {kind: workflow id used last}, "kind": the kind Create
    showed last, "project": the project Create used last (null: none), "skills": the skills used lately, newest first,
    "seen": the one-time tips already shown, such as the canvas's first tip}."""
    return await offload(preferences.studio, request.app.state.db, user["id"])


@router.put("/preferences")
async def save_studio_preferences(body: dict, request: Request, user: dict = Depends(current_user)):
    """Any of the fields GET gives; a workflow per kind is added to those kept."""
    try:
        return await offload(preferences.set_studio, request.app.state.db, user["id"], body)
    except ValueError as error:
        raise HTTPException(400, str(error))


# ---------------------------------------------------------------- review

@router.post("/agent/review", dependencies=[costly("agent")])
async def agent_review(body: dict, request: Request, user: dict = Depends(current_user)):
    return await _patient(_agent_review(body, request, user))


async def _agent_review(body, request, user):
    """Have the agent look at a picture or clip it made and check it against its prompt, its reference pictures and
    the shot before. Body: {"item", "prompt"?, "uses"?: [{"id"} or {"asset"}], "previous"?: item id, "retake"?: bool}.
    Returns {"verdict", "retake"}: a failed result comes with a retake, priced but not queued, unless "retake" is false.
    Nothing is charged: a retake is queued only when the user approves it."""
    state = request.app.state
    item = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ?", (body.get("item"), user["id"])) \
        if isinstance(body.get("item"), int) else None
    if item is None:
        raise HTTPException(404, "No such item.")
    module = item["project_id"] or 0   # what it is checked against is of its own module, never another's

    async def own(item_id):
        return await offload(kit.item_in_module, state.db, user["id"], module, item_id)
    references = []
    for use in (body.get("uses") or [])[:review.MAX_REFERENCES * 2] if isinstance(body.get("uses"), list) else []:
        if not isinstance(use, dict):
            continue
        if isinstance(use.get("asset"), int) and use["asset"]:
            row = await offload(kit.entry_in_module, state.db, user["id"], module, use["asset"])
            path = row and state.assets_dir / str(row["user_id"]) / row["filename"]
        else:
            row = await own(use.get("id"))
            path = row and await offload(state.outputs.folder, row["user_id"]) / row["filename"]
        if row and row["kind"] in ("image", "video"):
            references.append((row["name"], path))
    if not references and item["project_id"]:   # checked on its own: the project's always-on kit is what it should look like
        for e in await offload(kit.always, state.db, user["id"], item["project_id"]):
            path = state.assets_dir / str(user["id"]) / e["filename"]
            if e["kind"] in ("image", "video") and e["made_from"] != item["id"] and path.is_file():
                references.append((e["name"], path))
    before = await own(body.get("previous"))
    previous = (await offload(state.outputs.folder, before["user_id"]) / before["filename"], before["kind"]) if before and before["kind"] in ("image", "video") else None
    kept = review.load(item)
    if kept and kept.get("by") == "auto":   # checked in the background once it was made (aftercare.py): not again
        verdict = kept
    else:
        try:
            verdict = await aftercare.once(item["id"], review.review_item(state, user["id"], item, str(body.get("prompt") or "")[:4000],
                                                                          references, previous))
        except (review.ReviewError, agent.AgentError) as error:
            raise HTTPException(400, str(error))
    if verdict.get("retake_job"):   # the background made the retake already, as the user allows
        return {"verdict": verdict, "retake": None, "retaken": {"job": verdict["retake_job"], "credits": verdict.get("retake_credits") or 0}}
    retake = await _retake(state, user, item, verdict, before) if body.get("retake", True) and not verdict["passed"] else None
    return {"verdict": verdict, "retake": retake}


async def _retake(state, user, item, verdict, previous):
    """The job settings of a retake of a failed item: the same workflow and settings with the fixed prompt and a new
    seed, priced. None when the item was not made by a workflow with a prompt, or the review gave no new prompt."""
    fix = verdict.get("fix") or {}
    if not fix.get("prompt"):
        return None
    try:
        wf = await state.catalog.load(item["workflow"])
        schema = workflows.describe(wf)
    except (workflows.WorkflowError, HTTPException):
        return None
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    if "prompt" not in roles:
        return None
    settings = json.loads(item["settings"] or "{}")
    settings["values"] = dict(settings.get("values") or {}, **{roles["prompt"]["id"]: fix["prompt"]})
    settings.update(workflow=schema["id"], seed_mode="random", parent=item["id"], project_id=item["project_id"],
                    name=(item["name"].removesuffix(" · retake") + " · retake")[:80])   # a retake of a retake is not named twice
    shot = settings.get("shot")
    if isinstance(shot, dict) and shot.get("id"):
        settings["shot"] = {"id": shot["id"], "take": int(shot.get("take") or 1) + 1}
    start = None
    first_frame = (schema.get("slots") or {}).get("first_frame")
    if fix.get("start_from_previous") and previous and first_frame:
        start = {"id": previous["id"], "name": previous["name"], "slot": first_frame}   # the browser fills the slot on Approve
    try:
        quote = await price(state, wf, settings, user["id"])
    except (workflows.WorkflowError, HTTPException, ValueError, KeyError):
        return None
    return {"settings": settings, "credits": quote["credits"], "time": quote["text"], "prompt": fix["prompt"],
            "why": fix.get("why") or "", "start": start,
            "workflow_title": schema["title"]}


@router.post("/agent/compact", dependencies=[costly("agent")])
async def agent_compact(body: dict, request: Request, user: dict = Depends(current_user)):
    return await _patient(_agent_compact(body, request, user))


async def _agent_compact(body, request, user):
    """Fold a conversation into the Direction, the durable notes the agent reads in place of old turns.
    Body: {"history": [...as for plan], "direction"?: the notes so far}. Returns {"direction"}. Nothing is queued."""
    turns = agent.past_turns(body.get("history"))
    if not turns and not body.get("direction"):
        raise HTTPException(400, "There is nothing to fold yet.")
    try:
        text = await request.app.state.agent.compact(turns, str(body.get("direction") or ""), **_model(body))
    except agent.AgentError as e:
        raise HTTPException(502, str(e))
    return {"direction": text}


STILL_WORKFLOWS = ("flux2_klein_9b", "krea2_turbo")   # cheap picture workflows, in the order the storyboard prefers them


async def _still_workflow(state, user):
    """The workflow that draws a storyboard still: a cheap picture workflow that is switched on. None when there is none."""
    every = await state.catalog.listing()
    on = await offload(state.credits.enabled_of, [w["id"] for w in every], user)
    found = [w for w in every if w["kind"] == "image" and not w.get("error") and w["id"] in on]
    for word in STILL_WORKFLOWS:
        for w in found:
            if word in w["id"]:
                return w["id"]
    return found[0]["id"] if found else None


def _proposals(shots):
    """The shots of a staged plan as sent by the browser: [(shot id, the model's proposal for it, the shot)], the usable ones."""
    out = []
    for shot in (shots if isinstance(shots, list) else [])[:agent.MAX_STEPS]:
        proposal = shot.get("proposal") if isinstance(shot, dict) else None
        ident = memory.clean_shot({"id": shot.get("shot_id")}) if isinstance(shot, dict) else None
        if isinstance(proposal, dict) and ident and proposal.get("tool", "generate") == "generate" \
                and str(proposal.get("workflow") or "").startswith("video/"):
            out.append((ident["id"], proposal, shot))
    return out


def _as_shot(step, shot_id):
    step["shot_id"] = shot_id
    step["settings"]["shot"] = {"id": shot_id, "take": 1}
    return step


@router.post("/agent/storyboard", dependencies=[costly("agent")])
async def agent_storyboard(body: dict, request: Request, user: dict = Depends(current_user)):
    """Stage one of a long film: a cheap still for each planned video shot, to look at before any clip is made.
    Body: {"shots": [{"shot_id", "proposal"}], "project_id"?}. Returns {"steps": [...], "dropped": [...], "total"};
    nothing is queued or charged: the browser queues the stills on Approve, as for any plan."""
    state = request.app.state
    project = await offload(_project_id, request, user, body.get("project_id"))
    wanted = _proposals(body.get("shots"))
    if not wanted:
        raise HTTPException(400, "There are no video shots to draw first.")
    still = await _still_workflow(state, user)
    if not still:
        raise HTTPException(400, "No picture workflow is switched on to draw the stills with.")
    schemas = {still: workflows.describe(await state.catalog.load(still))}
    pinned, menu = await offload(kit.always, state.db, user["id"], project or None), await _menu(state, user)
    steps, dropped = [], []
    for shot_id, proposal, _ in wanted:
        card = {key: proposal.get(key) for key in ("prompt", "orientation", "shot_size", "angle", "end_state", "shot_number")}
        card.update(tool="generate", workflow=still, name="Still · " + str(proposal.get("name") or "shot")[:70])
        before = len(steps)
        reason = await _plan_step(state, card, "", steps, {}, schemas, {}, {}, [], pinned, project or None, {}, [], menu,
                                  core.Core(state.db, user["id"], "", project))
        if len(steps) == before:
            dropped.append((proposal.get("name") or "a shot", reason or "it could not be drawn"))
            continue
        _as_shot(steps[-1], shot_id)
        steps[-1].update(stage="still", proposal=proposal)   # the video proposal travels with the still, to animate it later
    return {"steps": steps, "dropped": dropped, "total": sum(s["credits"] for s in steps)}


@router.post("/agent/animate", dependencies=[costly("agent")])
async def agent_animate(body: dict, request: Request, user: dict = Depends(current_user)):
    """Stage two: each approved still becomes the first frame of its clip. Body: {"shots": [{"shot_id", "item", "proposal"}],
    "project_id"?}, item being the library id of the still. Returns {"steps", "dropped", "total"}, not queued."""
    state = request.app.state
    project = await offload(_project_id, request, user, body.get("project_id"))
    steps, dropped, names, kinds, shapes, schemas, wanted = [], [], {}, {}, {}, {}, []
    for shot_id, proposal, shot in _proposals(body.get("shots")):
        row = await offload(kit.item_in_module, state.db, user["id"], project, shot.get("item"), "image")
        if row is None:
            dropped.append((proposal.get("name") or "a shot", "its still is not there"))
            continue
        made = json.loads(row["context"] or "{}")
        names[row["id"]], kinds[row["id"]] = row["name"], {"name": row["name"], "kind": "image"}
        if made.get("width") and made.get("height"):
            shapes[row["id"]] = [made["width"], made["height"]]
        wanted.append((shot_id, proposal, row["id"]))
        # Langfuse: the still was approved (a still made again instead is "approved" 0, see agent_reroll)
        await offload(state.traces.langfuse.item_score, row["id"], "approved", 1, "approved-{}".format(row["id"]))
        if proposal["workflow"] not in schemas:
            try:
                schemas[proposal["workflow"]] = workflows.describe(await state.catalog.load(proposal["workflow"]))
            except (workflows.WorkflowError, HTTPException):
                pass
    pinned, menu = await offload(kit.always, state.db, user["id"], project or None), await _menu(state, user)
    for shot_id, proposal, item in wanted:
        before = len(steps)
        reason = await _plan_step(state, dict(proposal, start_from=item, after=0, uses=[]), "", steps, {}, schemas, names, kinds, [],
                                  pinned, project or None, shapes, [], menu, core.Core(state.db, user["id"], "", project))
        if len(steps) == before:
            dropped.append((proposal.get("name") or "a shot", reason or "it could not be planned"))
            continue
        _as_shot(steps[-1], shot_id)
    return {"steps": steps, "dropped": dropped, "total": sum(s["credits"] for s in steps)}


@router.post("/agent/reroll", dependencies=[costly("agent")])
async def agent_reroll(body: dict, request: Request, user: dict = Depends(current_user)):
    """Another take of a finished shot: the same prompt and settings with a new seed, priced and not queued.
    Body: {"item", "prompt"?}. Returns {"retake"}, as the review does for a failed shot."""
    state = request.app.state
    item = await state.db.aone("SELECT * FROM generations WHERE id = ? AND user_id = ?", (body.get("item"), user["id"])) \
        if isinstance(body.get("item"), int) else None
    if item is None:
        raise HTTPException(404, "No such item.")
    try:
        schema = workflows.describe(await state.catalog.load(item["workflow"]))
    except (workflows.WorkflowError, HTTPException):
        raise HTTPException(400, "The workflow that made this is gone.")
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    made_with = (json.loads(item["settings"] or "{}").get("values") or {}).get((roles.get("prompt") or {}).get("id"))
    prompt = str(body.get("prompt") or "").strip() or str(made_with or "")
    retake = await _retake(state, user, item, {"fix": {"prompt": prompt, "why": "Another take of the same shot."}}, None) if prompt else None
    if retake is None:
        raise HTTPException(400, "This one cannot be made again.")
    await offload(state.traces.langfuse.item_score, item["id"], "approved", 0, "approved-{}".format(item["id"]))   # Langfuse: asked to redo it
    return {"retake": retake}


async def _menu(state, user):
    """The workflows an approval card can switch a step to: every readable one that is switched on."""
    every = await state.catalog.listing()
    on = await offload(state.credits.enabled_of, [w["id"] for w in every], user)
    return [{"id": w["id"], "title": w["title"], "kind": w["kind"]} for w in every
            if w["kind"] in ("video", "image", "audio") and not w.get("error") and w["id"] in on]


@router.post("/agent/step", dependencies=[costly("agent")])
async def agent_step(body: dict, request: Request, user: dict = Depends(current_user)):
    """Change one step of a plan on its approval card: the workflow, the shape, the size, the length or the prompt.
    The step is built again with the same checks as a planned one and priced. Nothing is queued or charged."""
    state = request.app.state
    step, change = body.get("step") or {}, body.get("change") or {}
    old = step.get("settings") if isinstance(step, dict) else None
    if not isinstance(old, dict) or not old.get("workflow") or not isinstance(change, dict):
        raise HTTPException(400, "Only a generation can be changed here.")
    project = await offload(_project_id, request, user, old.get("project_id"))
    try:
        old_schema = workflows.describe(await state.catalog.load(str(old["workflow"])))
        schema = workflows.describe(await state.catalog.load(str(change.get("workflow") or old["workflow"])))
    except workflows.WorkflowError as e:
        raise HTTPException(400, str(e))
    if schema["id"].split("/", 1)[0] != old_schema["id"].split("/", 1)[0]:
        raise HTTPException(400, "A step can only change to a workflow that makes the same kind of thing.")
    if not await offload(state.credits.enabled, schema["id"], user):
        raise HTTPException(400, "This workflow is switched off for now.")
    try:
        ctx = workflows.context(old_schema, old)
    except workflows.WorkflowError as e:
        raise HTTPException(400, str(e))
    roles = {c["role"]: c for c in old_schema["controls"] if c["role"]}
    if isinstance(change.get("prompt"), str):
        prompt = change["prompt"]
    else:   # a workflow with no prompt (a transcription, a voice separation) has none to keep
        prompt = (old.get("values") or {}).get(roles["prompt"]["id"], "") if "prompt" in roles else ""
    # The step as the model would have proposed it, with the change made: settings_for keeps what the workflow takes.
    proposed = {"prompt": str(prompt).strip(), "name": old.get("name"), "clips": old.get("clips", 1),
                "duration": float(change.get("duration") or ctx.get("duration") or 0),   # a clip timed to its frames keeps its decimals
                "resolution": _resolution_of(change.get("resolution") or ctx.get("resolution")),
                "orientation": change.get("orientation") or _orientation(old_schema, old, ctx)}
    if not proposed["prompt"]:
        raise HTTPException(400, "The prompt is empty.")
    same = schema["id"] == old_schema["id"]
    first_frame = (schema.get("slots") or {}).get("first_frame")
    start, after = step.get("start"), step.get("after")
    if (start or after) and not first_frame:
        raise HTTPException(400, "{} can't start on a picture, and this shot starts on one.".format(schema["title"]))
    slots = {r["id"] for r in schema["refs"]}
    uses = [u for u in step.get("uses") or [] if isinstance(u, dict) and u.get("slot") in slots and not u.get("cast")]
    if start:
        proposed["start_from"] = start.get("id")
    built = agent.settings_for(schema, proposed, {start.get("id")} if start else set(), project or None,
                               {u["slot"] for u in uses}, {u["id"] for u in uses if u.get("id")}, bool(after))
    if not built:
        raise HTTPException(400, "{} needs reference files this step doesn't have.".format(schema["title"]))
    settings, started = built
    keep = memory.clean_keep(old.get("keep"), schema["id"].split("/", 1)[0])
    if keep:   # a step changed on its card is still kept in shared memory
        settings["keep"] = keep
    if isinstance(old.get("save_to_state"), dict):   # and where its result goes in the state (checked when it is made)
        settings["save_to_state"] = old["save_to_state"]
    if isinstance(old.get("check"), str):
        settings["check"] = old["check"][:400]
    if isinstance(old.get("turn"), dict):   # and the turn it was planned in (Langfuse)
        settings["turn"] = old["turn"]
    for key in PLANNED_KEYS:   # and its shot number, its board, the references its review compares with
        if key in old:
            settings[key] = old[key]
    try:
        stepped = await offload(fit_resolution, state, schema, settings)   # a resolution switched off: the next one allowed, said on the card
    except HTTPException:
        raise
    if stepped:
        step = dict(step, why=" ".join(filter(None, [step.get("why"), stepped])))
    if same:   # the workflow's own choices (mode, speed, quality) and other settings stay as they were
        known = {o["id"]: [c["id"] for c in o["choices"]] for o in schema["options"]}
        asked_now = {schema["resolution_option"]["id"]} if change.get("resolution") and schema.get("resolution_option") else set()
        settings["options"].update({k: v for k, v in (old.get("options") or {}).items() if v in known.get(k, []) and k not in asked_now})
        kept = {c["id"] for c in schema["controls"] if not c["role"]}
        settings["values"].update({k: v for k, v in (old.get("values") or {}).items() if k in kept})
    if not change.get("orientation") and step.get("shape") and (start or after):
        agent.shape_like(schema, settings, step["shape"])   # a shot that starts on a picture keeps that picture's shape
    elif change.get("orientation") and not schema.get("size"):
        agent.shape_like(schema, settings, {"landscape": (16, 9), "portrait": (9, 16), "square": (1, 1)}.get(change["orientation"]))
    pinned = await offload(kit.always, state.db, user["id"], project or None)
    uses = uses + [dict(fill, cast=True) for fill in kit.fills(
        schema, pinned, {u["slot"] for u in uses}, {u["asset"] for u in uses if u.get("asset")}, step.get("leave_out") or (),
        {u["id"] for u in uses if u.get("id")} | ({started} if started else set()))]
    try:
        return await _shown_step(state, schema, settings, await _menu(state, user), uses,
                                 dict(start, slot=first_frame) if start else None,
                                 dict(after, slot=first_frame) if after else None, step.get("why") or "")
    except workflows.WorkflowError as e:
        raise HTTPException(400, str(e))


@router.post("/agent/plan", dependencies=[costly("agent")])
async def agent_plan(body: dict, request: Request, user: dict = Depends(current_user)):
    """Ask the agent for a plan. Each step comes back as checked, priced job settings; nothing is queued or charged.

    Asked with "Accept: application/x-ndjson", it answers as it works: one JSON line per thing it does ("status" while
    it is busy, "activity" and "thought" for its log), then the plan ({"type": "plan", ...}) or {"type": "error"}.
    Otherwise it answers once, with the plan and its log."""
    instruction = str(body.get("instruction") or "").strip()[:2000]
    if not instruction:
        raise HTTPException(400, "Write a message for the agent.")
    await offload(guardrails.turn_check, request.app.state.db)   # the studio's stop; the agent's limits read again
    project = await offload(_project_id, request, user, body.get("project_id"))
    # What the agent's work says of how the studio is built (skills, NeuralCore, its session, tokens) is put in plain
    # words for someone who may not see it (internals.py).
    events = internals.for_user(_kept_alive(_planning(request, user, body, instruction, project)), user)
    if "application/x-ndjson" in request.headers.get("accept", ""):
        async def lines():
            try:
                async for event in events:
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as error:   # the stream has started: the error goes in it, not in the status code
                detail = getattr(error, "detail", None) or str(error) or "The agent stopped. Try again."
                yield json.dumps({"type": "error", "message": str(detail)}, ensure_ascii=False) + "\n"
        return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    plan = None
    async for event in events:
        if event["type"] == "plan":
            plan = event
    return {k: v for k, v in plan.items() if k != "type"}


async def _patient(work):
    """The answer of `work` (a coroutine that gives a dict). One that comes within PATIENT seconds is sent as it is,
    errors with their status. A slower one is sent as a space every KEEP_ALIVE seconds and then the answer (JSON allows
    spaces before it); the status is sent by then, so an error comes as {"detail", "failed": its status}."""
    task = asyncio.ensure_future(work)
    done, _ = await asyncio.wait([task], timeout=PATIENT)
    if done:
        return task.result()

    async def slowly():
        try:
            while not task.done():
                done, _ = await asyncio.wait([task], timeout=KEEP_ALIVE)
                if not done:
                    yield b" "
            try:
                answer = task.result()
            except HTTPException as error:
                answer = {"detail": error.detail, "failed": error.status_code}
            except Exception as error:   # the status is sent already: the error goes in the answer
                answer = {"detail": str(error) or type(error).__name__, "failed": 500}
            yield json.dumps(answer, ensure_ascii=False).encode("utf-8")
        finally:
            if not task.done():
                task.cancel()
    return StreamingResponse(slowly(), media_type="application/json", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


async def _kept_alive(events):
    """The events of a plan, with signs of life ({"type": "ping"}) while nothing happens for KEEP_ALIVE seconds (a long
    call). The plan runs in a task of its own; this generator passes on what it does."""
    queue, end = asyncio.Queue(), object()

    async def work():
        try:
            async for event in events:
                await queue.put(event)
            await queue.put(end)
        except Exception as error:
            await queue.put(error)

    task = asyncio.ensure_future(work())
    getter = None
    try:
        while True:
            getter = getter or asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait([getter], timeout=KEEP_ALIVE)
            if not done:
                yield {"type": "ping"}
                continue
            event, getter = getter.result(), None
            if event is end:
                return
            if isinstance(event, Exception):
                raise event
            yield event
    finally:
        for waiting in (getter, task):
            if waiting is not None and not waiting.done():
                waiting.cancel()


async def _planning(request, user, body, instruction, project):
    """The work behind a plan, as events: what the agent does, as it does it, and at the end the plan."""
    state = request.app.state
    started = time.monotonic()
    log = []   # what the user sees of the work afterwards: {"type": "activity" | "thought", ...}
    # How hard Claude thinks over this message, as the user picked it for the model (claude.EFFORT); the model's own
    # default when it was not picked or the model does not take it.
    claude.EFFORT.set(claude.chosen_effort(body.get("model") or state.agent.model or "", body.get("effort")))

    def logged(event):
        event["at"] = round(time.monotonic() - started, 1)
        log.append(event)
        return event

    def activity(icon, text):
        return logged({"type": "activity", "icon": icon, "text": text})

    def status(text):   # what it is doing right now; shown while it works, not kept
        return {"type": "status", "text": text}

    selection, shapes = [], {}   # shapes: item id -> [width, height], for shots that start on an item
    chosen = (body.get("selection") or [])[:MAX_SELECTION] if agent.points_at_selection(instruction) else []
    # A run that follows a long skill keeps every file attached to it: "go", and every message after the one the files
    # came with, still has them, whether or not the model saved them itself. The files of this message come first, so
    # the @1, @2 the user wrote are theirs; the earlier ones follow, in the order they were attached.
    run_id = body.get("run") if isinstance(body.get("run"), str) and runs.RUN.match(body["run"]) else ""
    tagged = len(chosen)   # the files the message's own @1, @2 … stand for
    if run_id and await offload(runs.kept_skill, state.db, user["id"], run_id, project):
        earlier = await offload(runs.kept_attached, state.db, user["id"], run_id, project)
        given = [i for i in body.get("selection") or [] if isinstance(i, int)]
        chosen = (given + [i for i in earlier if i not in given])[:MAX_SELECTION]
        tagged = len(given)
    elsewhere = []   # attached here but of another module or project: never read, and the user is told
    for item_id in chosen:
        row = await offload(kit.item_in_module, state.db, user["id"], project, item_id)
        if row is None and await offload(kit.refusal, state.db, user["id"], item_id, ""):
            elsewhere.append(item_id)
        if row:
            # The tag is what the user calls the item in the instruction: the first one attached is @1.
            selection.append({"tag": "@{}".format(len(selection) + 1), "id": row["id"], "kind": row["kind"], "name": row["name"],
                              "prompt": str(json.loads(row["settings"]).get("prompt") or "")[:300]})
            if row["about"]:   # what the agent's model saw in it, when it has looked
                selection[-1]["shows"] = row["about"]
            made = json.loads(row["context"] or "{}")
            if made.get("width") and made.get("height"):
                shapes[row["id"]] = [made["width"], made["height"]]
            path = await offload(state.outputs.folder, row["user_id"]) / row["filename"]
            if row["kind"] in ("video", "audio") and path.is_file():   # the length is what the editing tools cut by
                selection[-1]["seconds"] = round((await media.probe(path))["seconds"], 2)
            elif row["kind"] == "text" and path.is_file():   # a script or a document: how long it is, and how it begins
                words = path.read_text(encoding="utf-8-sig", errors="replace")
                selection[-1]["characters"] = len(words)
                selection[-1]["begins"] = " ".join(words[:TEXT_OPENING].split())
    if selection:
        yield activity("attach", "Read what you attached: " + ", ".join(s["name"] for s in selection))
    if elsewhere:
        yield activity("skip", "{} ({} attached)".format(kit.ELSEWHERE, len(elsewhere)))
    # An asset sheet attached (a CSV of type, name, image link and notes a row) is this module's references: its rows
    # come into the module's NeuralCore before anything is planned, whatever the message says, and the agent is told so.
    for found in await _bring_in_sheets(state, user, project, body.get("selection") or [], selection):
        yield activity("book", found)

    # What was made lately here, so "the music you just made" can be put on "this video" without attaching either.
    # The whole films come first, those a long run made too (its other working files are left out).
    scope, args = ("project_id = ?", (project,)) if project else ("project_id IS NULL", ())
    films = await state.db.aall("SELECT id, kind, name FROM generations WHERE user_id = ? AND " + scope + " AND workflow IN ("
                         + ", ".join("?" * len(placement.FINISHED)) + ") ORDER BY created DESC LIMIT 3", (user["id"], *args, *placement.FINISHED))
    lately = await state.db.aall("SELECT id, kind, name FROM generations WHERE user_id = ? AND run = '' AND " + scope
                          + " ORDER BY created DESC LIMIT 8", (user["id"], *args))
    recent = [{"id": r["id"], "kind": r["kind"], "name": r["name"]}
              for r in films + [r for r in lately if r["id"] not in {f["id"] for f in films}]]
    known = {s["id"]: {"name": s["name"], "kind": s["kind"]} for s in selection}
    known.update({r["id"]: {"name": r["name"], "kind": r["kind"]} for r in recent if r["id"] not in known})

    # The user can name a skill with /<id> anywhere in the message (at its start, after the files they attached, at its
    # end), or the panel can pass skill ids; those are always used. The rest are picked by what the message says.
    forced = list(body.get("skills") or [])
    instruction = re.sub(r"(@\d+)(?=/)", lambda m: m.group(1) + " ", instruction)   # a command typed straight after an attached file (@1/skill)
    for match in reversed(list(SLASH.finditer(instruction))):
        if skills.find(match.group(1)):
            forced.insert(0, skills.find(match.group(1))["id"])   # /craft-director is director here
            # the /command is an instruction to the agent, not shot text
            instruction = (instruction[:match.start()] + " " + instruction[match.end():]).strip()
    instruction = re.sub(r"[ \t]{2,}", " ", instruction)
    # A long run follows the skill its first message named until another is named: "go" and every message after it
    # carry on with that skill, rather than skills picked afresh from their words.
    carried = await offload(runs.kept_skill, state.db, user["id"], run_id, project) if run_id else None   # the skill this run follows already
    if run_id and not any(skills.find(f) for f in forced):
        kept = carried
        if kept and skills.find(kept):
            forced.append(kept)
            yield activity("skill", "Carried on with “{}”, the skill of this run".format(skills.find(kept)["title"]))
    # No skill is picked by a message's words: only the user picks one. A message asking for a video with none picked
    # gets the default skill, as if the user had named it (it hands on to the craft skills it needs).
    if not any(skills.find(f) for f in forced) and skills.find(skills.DEFAULT) and skills.wants_video(
            instruction, body.get("history"), [s["kind"] for s in selection]):
        forced.append(skills.DEFAULT)
        yield activity("skill", "No skill picked: “{}”, the default for making a video".format(skills.find(skills.DEFAULT)["title"]))
    elif not any(skills.find(f) for f in forced) and skills.find(skills.MOTION_DEFAULT) and skills.wants_motion(instruction, body.get("history")):
        forced.append(skills.MOTION_DEFAULT)
        yield activity("skill", "No skill picked: “{}”, the default for a brand's motion graphics".format(
            skills.find(skills.MOTION_DEFAULT)["title"].split(" — ")[0]))
    picked = skills.pick(instruction, body.get("history"), force=forced)
    # A long skill the user named is the whole procedure: no other skill picked by the message's words goes beside it.
    if any(s["id"] in forced and len(s["text"]) > CHECKED_SKILL for s in picked):
        picked = [s for s in picked if s["id"] in forced]
    # A run keeps its long skill, named or picked by the message's words, and the files attached to it: the messages
    # that follow carry on with both. Without them a "continue" has no sound attached, and the workflows that work on
    # one (transcribe, separate a voice) are not offered.
    # The director, come on its own for multi-shot story work (skills.wants_directing), is a craft beside the work: never
    # the run's skill, never checked before it starts, and never what makes the message a long run.
    following = next((s["id"] for s in picked if len(s["text"]) > CHECKED_SKILL and not s.get("auto")), None)
    if run_id and following:
        await offload(runs.keep_skill, state.db, user["id"], run_id, project, following)
        await offload(runs.keep_attached, state.db, user["id"], run_id, project, [s["id"] for s in selection])
    for skill in picked:
        yield activity("skill", "Read the skill “{}”{}".format(skill["title"], " (multi-shot story work)" if skill.get("auto") else ""))
    # A long skill asks the user which models to use, so it is shown every one; and a model named anywhere in the
    # conversation (the message, its notes, the turns before) stays offered for the rest of it.
    long_skill = any(len(s["text"]) > CHECKED_SKILL and not s.get("auto") for s in picked)
    said = " ".join([instruction, str(body.get("direction") or "")] + [
        "{} {}".format(t.get("instruction") or "", t.get("reply") or "") for t in (body.get("history") or [])[-agent.MAX_HISTORY:]
        if isinstance(t, dict)]).lower()
    # What this turn is, for Langfuse (traces.TURN): every call made for it, and every render it queues, is in one trace
    # with this name, tagged with the skills it follows.
    with as_everyone():   # a project shared with this user is another's row
        where = await state.db.aone("SELECT ref FROM projects WHERE id = ?", (project,)) if project else None
    turn = {"name": "Film run" if run_id and long_skill else "Agent turn", "tags": [s["id"] for s in picked],
            "metadata": {"project": project or None, "project_ref": where["ref"] if where else None,
                         "skills": [s["id"] for s in picked], "film_run": bool(run_id and long_skill), "run": run_id or None}}
    traces.TURN.set(turn)

    schemas = {}
    default = state.catalog.current(state.settings.default_workflow)
    menu = await _menu(state, user)
    # The models the user pinned for this chat (the panel's choice, kept with the tab): of a kind they pinned (video,
    # image, audio, upscale), only those are offered, unless the message names another. (A pin of the generation
    # server's time, "<workflow id>#<model>", names no model now: it is left out.)
    pin_values = [w for w in body.get("workflows") or [] if isinstance(w, str)][:40] if isinstance(body.get("workflows"), list) else []
    chat_pins = list(dict.fromkeys(w for w in pin_values if "#" not in w))
    pinned_kinds = {w.split("/", 1)[0] for w in chat_pins if w.split("/", 1)[0] in PINNABLE}
    named_here = instruction.lower()
    every_workflow = await state.catalog.listing()
    usable_ids = await offload(state.credits.enabled_of, [w["id"] for w in every_workflow], user)   # one query, not one a workflow
    usable_ids -= set(await unreachable(state, every_workflow))   # a model no key in use could ever make now
    for listed in every_workflow:
        if listed.get("error") or listed["id"] not in usable_ids:
            continue
        if listed["kind"] in pinned_kinds and listed["id"] not in chat_pins and listed["title"].lower() not in named_here \
                and listed["id"].lower() not in named_here:
            continue
        # Video is made with the default workflow, which has the cast's slots and the quality choices; the other video
        # workflows are for the Create page, and the agent uses one only when the conversation names it (or a long skill
        # has the user choose).
        if listed["kind"] == "video" and default.startswith("video/") and listed["id"] != default and not long_skill \
                and listed["title"].lower() not in said and listed["id"].lower() not in said and listed["id"] not in chat_pins:
            continue
        schema = workflows.describe(await state.catalog.load(listed["id"]))
        if schema["resolutions"]:   # only the resolutions an admin left on are offered (credits.allowed_resolutions)
            allowed = await offload(state.credits.allowed_resolutions, schema["id"], schema["resolutions"])
            if not allowed:
                continue
            schema = dict(schema, resolutions=allowed)
        schemas[listed["id"]] = schema
    if chat_pins:
        yield activity("plan", "Uses the workflows chosen for this chat: {}".format(
            ", ".join(schemas[w]["title"] for w in chat_pins if w in schemas)
            or "none of them is switched on now"))
    # The pictures the user names in the message ("Maya - @3", "location - Bonfire Clearing - @10") are kept in the
    # project's kit under those names: every agent tab knows them from then on, by name and by id.
    folder, outputs = state.assets_dir / str(user["id"]), await offload(state.outputs.folder, user["id"])
    said_names = memory.named_in(instruction, selection[:tagged])
    named = await offload(memory.keep_named, state.db, folder, outputs, user["id"], said_names, project or None)
    if named:
        yield activity("book", "Kept in NeuralCore: " + ", ".join("{} ({})".format(n["name"], n["type"]) for n in named))
    # A long run that starts with pictures nobody named keeps them too, without a name: the agent asks who they are.
    if run_id and long_skill and not carried:
        said_items = {n["item"] for n in said_names}
        unnamed = await offload(memory.keep_unnamed, state.db, folder, outputs, user["id"], project or None,
                                      [s["id"] for s in selection[:tagged] if s["kind"] == "image" and s["id"] not in said_items])
        if unnamed:
            yield activity("book", "Kept {} picture{} without a name in NeuralCore".format(len(unnamed), "" if len(unnamed) == 1 else "s"))
    pinned = await offload(kit.always, state.db, user["id"], project or None)
    # NeuralCore: what the agent knows of the project by name. Pictures it has not looked at yet are described now.
    book = await offload(memory.book, state.db, user["id"], project, pinned)
    if book:
        yield activity("book", "Opened NeuralCore: {} {}".format(len(book), "entry" if len(book) == 1 else "entries"))
    yield status("Looking at new pictures…")
    looked = await memory.describe_missing(state, user["id"], book, model=_looks(state, body)["describe"])
    if looked:
        yield activity("look", "Looked at {} new {}".format(looked, "picture" if looked == 1 else "pictures"))
    book_items, book_assets = memory.lookup(book)
    # A workflow that must be given reference files can run when something is attached or the book has a picture.
    can_fill = bool(selection) or any(entry["kind"] in ("image", "video") for entry in book)
    offers = [o for o in (agent.offer(schema, can_fill) for schema in schemas.values()) if o]
    if not offers:
        raise HTTPException(400, "There is no workflow the agent can use yet.")
    hears = agent.takes_sound(offers)   # the workflows that work on a sound file (separate a voice, transcribe)
    # A message costs what the chosen model costs: the user must have it before the model is asked. A Claude model is
    # priced by the tokens it uses, known only once it has answered: the user must have some credits to ask it at all.
    chosen_model = body.get("model") or state.agent.model or ""
    try:
        chosen_model = await state.agent.pick_model(body.get("model"))
    except agent.AgentError:
        pass   # the model is asked below, and that says what is wrong
    price = await offload(state.credits.llm_cost, chosen_model)
    if price:
        if await offload(state.credits.balance, user["id"]) < price:
            raise HTTPException(400, "A message to {} costs {} cr, and you have {} cr.".format(chosen_model, price, await offload(state.credits.balance, user["id"])))
        problem = await offload(state.credits.cap_problem, user["id"], price)
        if problem:
            raise HTTPException(400, problem)
    elif state.credits.token_prices(chosen_model):
        if await offload(state.credits.balance, user["id"]) < 1:
            raise HTTPException(400, "Messages to {} are charged by the tokens they use, and you have no credits left.".format(chosen_model))
        problem = await offload(state.credits.cap_problem, user["id"], 1)
        if problem:
            raise HTTPException(400, problem)
    charged = {"credits": 0, "model": chosen_model}
    # A skill is given whole up to skills.MAX_CHARS; a longer one as its opening and a list of its parts, which the
    # model reads with read_skill as it comes to them. A skill is never cut, whatever its length.
    limit = skills.MAX_CHARS
    for skill in picked:
        if len(skill["text"]) > limit:
            yield activity("skill", "“{}” is long ({:,} characters): the model reads its opening, and each of its {} parts as it "
                                    "comes to them".format(skill["title"], len(skill["text"]), len(skills.parts(skill["text"])) - 1))
    guides = skills.guide(picked, limit)
    # A skill the user named, or a long one (they are written by people, and say what they need first), is checked before
    # anything is planned: what it requires that is not here, and what it names that this studio cannot do, is said at once.
    adaptation = ""
    for skill in picked:
        if not (skill["id"] in forced or len(skill["text"]) > CHECKED_SKILL) or skill.get("auto"):
            continue
        if skill["id"] == carried:
            continue   # checked when its run began: the run goes on, with what that message had
        yield status("Checking what the skill needs…")
        ability = "\n".join(["Workflows: " + "; ".join("{} ({})".format(o["id"], o.get("title") or o["id"]) for o in offers),
                             STUDIO_ABILITY])
        # What is attached, then what shared memory holds by name (characters, locations, props kept from any tab),
        # then how many other files the project has.
        kept = [e for e in book if "asset" in e]
        others = {}
        for e in book:
            if "asset" not in e:
                others[e["kind"]] = others.get(e["kind"], 0) + 1
        attached = "\n".join([attachment_line(s) for s in selection]
                             + ["in shared memory: {} ({} {})".format(e["name"], e.get("type") or "other", e["kind"]) for e in kept]
                             + ["in the project: {} {}".format(n, k) for k, n in sorted(others.items())]) if selection or book else ""
        try:
            verdict = await state.agent.preflight(skill, instruction, attached, ability, agent.past_turns(body.get("history")), **_model(body))
        except agent.AgentError:
            continue   # a check that cannot run is not a reason to refuse
        # What the check calls missing while the user attached a file of that kind (a sound for "the audio", a text for
        # "the script") is set aside: a model may doubt a file it cannot open, and a run blocked for nothing is worse than
        # one whose skill asks again at its first step.
        covered = [m for m in verdict["missing"] if attached_kind(m, selection)]
        if covered:
            verdict = dict(verdict, missing=[m for m in verdict["missing"] if m not in covered])
            yield activity("check", "Set aside what the check called missing but you attached: {}".format("; ".join(covered)))
            if not verdict["missing"] and not verdict["unsupported"]:
                verdict = dict(verdict, ready=True)
        if verdict["ready"]:
            adaptation = verdict["adaptation"] or adaptation
            continue
        written = verdict["message"] if not covered else ""   # its message was about the files: it no longer stands
        said = written or "Before I start “{}”, {}:\n{}".format(
            skill["title"], "I need" if verdict["missing"] else "this studio cannot do what it asks here",
            "\n".join("- " + m for m in verdict["missing"] or verdict["unsupported"]))
        yield activity("skip", "Checked “{}”: {}".format(skill["title"], "needs " + "; ".join(verdict["missing"]) if verdict["missing"]
                                                         else "cannot be run as written here"))
        yield {"type": "plan", "reply": said, "thought": "", "activity": log, "seconds": round(time.monotonic() - started, 1), "chips": {},
               "direction": body.get("direction") or "", "steps": [], "total": 0, "llm": charged,
               "balance": await offload(state.credits.balance, user["id"])}
        return
    if adaptation:
        guides = (guides + "\n\n" if guides else "") + "Agreed with the user about this skill: " + adaptation
    # every prompt follows the studio's one prompt structure
    guides = (guides + "\n\n" if guides else "") + agent.STRUCTURE_GUIDE.format(structure=agent.PROMPT_STRUCTURE)
    names = {s["id"]: s["name"] for s in selection}
    # The items a step may put in its reference slots: the attached ones, and the project's pictures in the book.
    # A long run keeps its state under the conversation's id (see runs.py).
    run = body.get("run") if isinstance(body.get("run"), str) and runs.RUN.match(body["run"]) else ""
    # NeuralCore's memory: the module's own (the module or project this tab is open in), its cast and its catalogue.
    shared = await offload(core.Core, state.db, user["id"], run, project)
    await offload(shared.adopt)   # a run a tab kept for itself before episodes shared theirs carries on in the episode
    kinds = {**book_items, **{s["id"]: {"name": s["name"], "kind": s["kind"]} for s in selection}}
    if run:   # a long run names its references by library id from its state: any of the project's items, or the run's own
        kinds = {**{r["id"]: {"name": r["name"], "kind": r["kind"]} for r in await state.db.aall(
            "SELECT id, name, kind FROM generations WHERE user_id = ? AND " + ("project_id = ?" if project else "project_id IS NULL")
            + " ORDER BY run = ? DESC, id DESC LIMIT ?", (user["id"], *([project] if project else []), run, RUN_ITEMS))}, **kinds}
    videos = [s for s in selection if s.get("seconds")]

    with_tools = body.get("tools", True) is not False
    # A long run (a long skill) keeps its state under the conversation's id and works in many more tool calls.
    rounds = agent.RUN_ROUNDS if run and long_skill else agent.TOOL_ROUNDS
    tool_events = []   # what the tools did, shown as the agent's work once the answer is in
    noted = lambda glyph, text: tool_events.append((glyph, text))
    saved_direction = []

    def entry_of(call):
        return next((e for e in book if (call.get("item") and e.get("item") == call["item"])
                     or (call.get("asset") and e.get("asset") == call["asset"])), None)

    async def find_assets(call):
        query = " ".join(str(call.get("query") or "").lower().split())
        words = query.split()
        hits = [e for e in memory.book_for_model(book) if all(w in json.dumps(e, ensure_ascii=False).lower() for w in words)][:8]
        noted("book", "Looked in NeuralCore for “{}”: {}".format(query, "{} found".format(len(hits)) if hits else "nothing"))
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in hits) or "Nothing in NeuralCore matches. Make it from words."

    async def look(call):
        entry = entry_of(call)
        if entry is None:
            return "That id is not in NeuralCore."
        if str(call.get("op") or "").strip().lower() == "deep":   # a close study, for an edit or shots that must keep it
            try:
                found = await memory.analyse(state, user["id"], entry, model=_looks(state, body)["describe"])
            except (agent.AgentError, OSError) as error:
                return "It could not be studied: {}".format(error)
            noted("look", "Studied “{}” closely".format(entry["name"]))
            return agent.fit_result(json.dumps(found, ensure_ascii=False), agent.TOOL_RESULT)
        if not entry["shows"]:
            await memory.describe_missing(state, user["id"], [entry], limit=1, model=_looks(state, body)["describe"])
        noted("look", "Looked at “{}”".format(entry["name"]))
        return entry["shows"] or "It could not be looked at (the model cannot see it, or the file is gone)."

    async def check_shots(call):
        built, left = await build(call.get("steps"))
        noted("plan", "Checked {} {}{}".format(len(built), "step" if len(built) == 1 else "steps", ", {} left out".format(len(left)) if left else ""))
        lines = ["Step {}: {} on {}, {} credits{}{}".format(n, s["name"], s["workflow_title"], s["credits"],
                                                           " (variation {n} of {of})".format(**s["variation"]) if s.get("variation") else "",
                                                           " ({})".format(s["resolution_note"]) if s.get("resolution_note") else "")
                 for n, s in enumerate(built, start=1)]
        lines += ["Left out “{}”: {}".format(name, reason) for name, reason in left]
        return "\n".join(lines + ["Total {} credits.".format(sum(s["credits"] for s in built))])

    async def review_it(call):
        row = await offload(kit.item_in_module, state.db, user["id"], project, call.get("item"))
        if row is None:
            return await offload(kit.refusal, state.db, user["id"], call.get("item"), "No such item.")
        try:
            verdict = await review.review_item(state, user["id"], row, memory._prompt(json.loads(row["settings"] or "{}")), [], None,
                                              model=_looks(state, body)["review"])
        except (review.ReviewError, agent.AgentError) as error:
            return "It could not be reviewed: {}".format(error)
        noted("look", "Checked “{}”".format(row["name"]))
        return review.summary(verdict)

    async def save_note(call):
        text = agent.clean_direction(call.get("text"))
        if text:
            saved_direction[:] = [text]
            noted("book", "Updated the direction")
        return "Saved." if text else "Nothing to save."

    async def book_save(call):
        name, said_type = kit.clean_name(call.get("text")), str(call.get("op") or "").strip().lower()
        if not project:
            return "There is no NeuralCore here: it belongs to a project, and this message is in no project. Say so to the user."
        if not name:
            return "Give the entry its name in text."
        how = "{" if isinstance(call.get("settings"), dict) else str(call.get("settings") or "").strip().lower()
        fields = {}   # "settings" may be an object of the entry's fields (look_of, variant, from_scene, palette, relations)
        if how.startswith("{"):
            try:
                given = _structured(call.get("settings"))
            except ValueError:
                return "settings must be the word always or a JSON object of the entry's fields."
            if not isinstance(given, dict):
                return "settings must be a JSON object of the entry's fields."
            how = "always" if given.get("always") is True else str(given.get("how") or "").strip().lower()
            fields = {k: given[k] for k in ENTRY_FIELDS if k in given}
        always_on = how == "always"
        about = str(call.get("value") or "").strip()
        folder = state.assets_dir / str(user["id"])
        if call.get("asset") and not any(e["id"] == call["asset"] for e in await offload(kit.entries, state.db, user["id"], project)):
            return "There is no NeuralCore entry {} in this module.".format(call["asset"])   # another module's is never this one's
        if call.get("asset"):
            changes = {"name": name, "type": said_type, **({"about": about} if about else {}), **({"always": True} if always_on else {})}
            found = await offload(kit.update, state.db, user["id"], call["asset"], changes)
            if not found:
                return "There is no NeuralCore entry {}.".format(call["asset"])
            asset = found["id"]
        elif call.get("item"):
            if await offload(kit.item_in_module, state.db, user["id"], project, call["item"]) is None:
                return await offload(kit.refusal, state.db, user["id"], call["item"], "There is no library item {}.".format(call["item"]))
            asset = await offload(kit.add_item, state.db, folder, state.outputs.folder(user["id"]), user["id"], project or None, call["item"],
                                 name, kit.tag_of(said_type), always_on, True, about)
            if not asset:
                return "There is no library item {}.".format(call["item"])
            await offload(kit.update, state.db, user["id"], asset, {"name": name, "type": said_type, **({"about": about} if about else {})})
        elif kit.tag_of(said_type) == "script" and about:
            # A script written here (a story a skill wrote): "value" is its text, or "$state:/path" for the text kept there.
            try:
                words = await offload(shared.fill_text, about) if about.startswith("$state:") else about
            except runs.RunError as error:
                return str(error)
            asset = await offload(kit.add, state.db, folder, user["id"], project or None, words.strip()[:SCRIPT_CHARS].encode("utf-8"), name + ".txt",
                            "text", name, "script", always_on)
            if not asset:
                return "There is no NeuralCore here: it belongs to a project."
            noted("book", "Kept the script “{}” in NeuralCore".format(name))
            return json.dumps({"asset": asset, "name": name, "type": "script", "characters": len(words.strip())})
        else:
            return "Give the library id of what to keep in item, or NeuralCore entry to change in asset."
        if fields:
            try:
                await offload(kit.update, state.db, user["id"], asset, fields)
            except ValueError as error:   # a value kit cannot take: the model is told why, in words
                return str(error)
        noted("book", "Kept “{}” ({}) in NeuralCore".format(name, kit.TYPES.get(kit.tag_of(said_type), "other")))
        return json.dumps({"asset": asset, "name": name, "type": kit.TYPES.get(kit.tag_of(said_type), "other"), "always": always_on})

    reminded = []   # the run was reminded once to save its work
    stalled = []    # the model was told once that it announced work it did not do
    since = time.time()   # what the run saved during this message is newer than this

    async def finishing(answer):
        """A hint when the steps it finishes with cannot all run, so the model puts them right; nothing when they can.
        A long skill's run that would finish with nothing saved is reminded once: the next message only knows what
        the run state holds."""
        built, left = await build(answer.get("steps"))
        if not left and run and long_skill and not reminded and not await offload(shared.saved_any):
            reminded.append(True)
            noted("retry", "Nothing of the run was saved yet, so the model was asked to save its work first")
            return agent.SAVE_FIRST
        reply = str(answer.get("reply") or "")
        if not left and run and long_skill and not stalled and not answer.get("steps") and not agent.clean_question(answer.get("question")) \
                and agent.ABOUT_TO.search(reply) and not await offload(shared.saved_since, since):
            # A long run's turn that only says what it will do (no steps, no question, nothing saved) does nothing.
            stalled.append(True)
            noted("retry", "The model said what it would do but did not do it, so it was asked to")
            return agent.SAID_NOT_DONE.format(" ".join(reply.split())[:300])
        if not left:
            return await creative(answer, built)
        noted("retry", "A step could not run, so the model was asked to fix it: {}".format("; ".join(r for _, r in left)[:160]))
        return "These steps cannot run: {}. Fix them or leave them out, and finish again.".format(
            "; ".join("“{}”: {}".format(name, reason) for name, reason in left))

    hinted = set()   # the creative hints given in this message, each once: "brief", "notes"
    opinions = []    # the automatic second opinion: asked at most once a message
    big_limit = await offload(guardrails.limit, state.db, "creative_big_job_credits")

    async def kept(path):
        """What the memory keeps at a path, or None: nothing there, or a conversation that keeps no memory."""
        if not shared.keeps_state:
            return None
        try:
            found = await offload(shared.read, path)
        except runs.RunError:
            return None
        return None if found.get("missing") else found.get("value", found)

    async def creative(answer, built):
        """The creative process's hints for a plan whose steps can all run (docs/creative-director.md), each given once
        a message, never a block. A big job (agent.big_job) with no brief is sent back to ask one first. Then, once, the
        studio's notes in one hint: the concept a big job lacks, its stills first, the quality gates of any plan
        (guardrails.quality_hints), and a senior creative director's review (the automatic second opinion). A long
        skill's run goes through in_run: the skill keeps its own stages and questions, and the process fits into them."""
        if long_skill:
            return await in_run(answer, built)
        if not built:
            return None
        big = agent.big_job(built, instruction, body.get("history"), big_limit)
        if big and "brief" not in hinted:
            if shared.keeps_state:
                briefed = await kept("/brief") is not None
            else:   # no memory: the brief is a "Brief:" line of the direction
                briefed = "brief:" in "{} {}".format(answer.get("direction") or "", body.get("direction") or "").lower()
            if not briefed:
                hinted.add("brief")
                shots, total = len(agent.generated(built)), sum(s.get("credits") or 0 for s in built)
                noted("question", "A big job ({} shots, {} credits) with no brief yet, so the model was asked to ask for one first".format(shots, total))
                return agent.BRIEF_FIRST.format(why="{} generate steps, {} credits".format(shots, total), most=agent.MAX_QUESTIONS)
        if "notes" in hinted:
            return None
        hinted.add("notes")
        notes = []
        if big and not agent.clean_concept(answer.get("concept")):
            notes.append(agent.CONCEPT_MISSING)
        if big and agent.stills_wanted(built, book, instruction, body.get("history")):
            notes.append(agent.STILLS_FIRST)
        notes += guardrails.quality_hints(answer.get("steps"), instruction, book)   # every plan, small or big
        if big:
            critique = await auto_opinion(answer)
            if critique:
                notes.append(agent.OPINION_HINT.format(critique=critique))
        if not notes:
            return None
        noted("retry", "The studio gave the model its notes on the plan, once: {}".format(
            ", ".join(n.split(":")[0].split(".")[0][:40] for n in notes)))
        return agent.CREATIVE_NOTES.format(notes="\n".join("- " + n for n in notes))

    async def run_marked(name):
        """What the studio marked once in this run (runs.marked), or, in a conversation that keeps no run, this message."""
        if run:
            try:
                return await offload(runs.marked, state.db, user["id"], run, project, name)
            except runs.RunError:
                return None
        return True if name in hinted else None

    async def mark_run(name, value=True):
        hinted.add(name)
        if run:
            try:
                await offload(runs.mark, state.db, user["id"], run, project, name, value)
            except runs.RunError:
                pass

    async def in_run(answer, built):
        """The creative process inside a long skill's run, fitted to the skill's own stages, each hint once a run:
        - the brief: while /brief is empty, the skill's setup card asks the brief's fields too (folded into that card,
          never a second one), and once the user answered, the answers go to /brief;
        - the concept: asked before the shot plan is first written (state_write), and before a plan of shots is offered;
        - the review: the automatic second opinion of the skill's shot plan, once the run has one (once a run);
        - stills first only for a big job whose skills make no anchors or key stills themselves;
        - and the quality gates, as outside a run. The notes go as one hint, once a message."""
        asked = agent.clean_questions(answer.get("questions")) or [q for q in [agent.clean_question(answer.get("question"))] if q]
        briefed = await kept("/brief") is not None
        # Only a run's setup card takes the brief: a card of the message that starts the skill, or of a run that has
        # saved nothing yet. A question further on ("Which take?") is the skill's own, left alone.
        setup = bool(asked) and (not carried or not await offload(shared.saved_any))
        if not briefed and setup:
            missing = agent.brief_missing(asked)
            if len(missing) <= 1:
                await mark_run("brief_asked")
            elif not await run_marked("brief_folded"):
                await mark_run("brief_folded")
                noted("question", "The run has no brief yet, so the model was asked to fold its fields into the setup card")
                return agent.BRIEF_IN_SETUP.format(missing=", ".join(missing), most=agent.MAX_QUESTIONS)
            else:
                await mark_run("brief_asked")   # it kept its card as it was: the user answers what it asks
        elif not briefed and await run_marked("brief_asked") and not await run_marked("brief_saved"):
            await mark_run("brief_saved")
            noted("book", "The setup card was answered and /brief is empty, so the model was asked to save the brief")
            return agent.BRIEF_SAVE
        if "notes" in hinted:
            return None
        notes = []
        shots = [s for s in agent.generated(built) if s.get("kind") == "video"]   # the shots, not a skill's sheets
        if shots and await kept("/concept") is None and not await run_marked("concept"):
            await mark_run("concept")
            notes.append(agent.CONCEPT_MISSING)
        if built and agent.big_job(built, instruction, body.get("history"), big_limit) and not agent.makes_stills(picked) \
                and agent.stills_wanted(built, book, instruction, body.get("history")):
            notes.append(agent.STILLS_FIRST)
        notes += guardrails.quality_hints(answer.get("steps"), instruction, book)
        plan_path = await run_marked("shot_plan")
        if plan_path and not await run_marked("auto_opinion"):
            critique = await auto_opinion(answer, plan_path)
            if critique:
                notes.append(agent.OPINION_HINT.format(critique=critique))
        if not notes:
            return None
        hinted.add("notes")
        noted("retry", "The studio gave the model its notes on the run's plan, once: {}".format(
            ", ".join(n.split(":")[0].split(".")[0][:40] for n in notes)))
        return agent.CREATIVE_NOTES.format(notes="\n".join("- " + n for n in notes))

    async def auto_opinion(answer, plan_path=None):
        """The second opinion the studio asks for itself, at most once a message: on a big job's plan, or (plan_path) on
        a long skill's shot plan, once a run (marked "auto_opinion" with its model, so it never runs twice). The same
        call as the tool's, written down as agent.AUTO_OPINION, with the run, and in the session's story. None when it
        could not be had."""
        if opinions:
            return None
        opinions.append(True)
        if await offload(guardrails.choice, state.db, "creative_auto_review") == "off":
            noted("skip", "The automatic review is switched off (Guardrails)")
            return None
        shot_plan = None
        if plan_path:
            try:
                found = await offload(shared.read, plan_path)
                shot_plan = {leaf["path"]: leaf["value"] for leaf in found["leaves"]} if found.get("folder") else found.get("value")
            except runs.RunError:
                shot_plan = None
        about = agent.plan_outline(answer.get("steps"), agent.clean_concept(answer.get("concept")) or await kept("/concept") or "",
                                   await kept("/brief"), shot_plan)
        try:
            found = await ask_opinion(about, None, agent.AUTO_OPINION)
        except agent.AgentError as error:
            noted("skip", "No automatic second opinion this time: {}".format(str(error)[:120]))
            return None
        if plan_path:
            await mark_run("auto_opinion", {"model": found["model"], "at": time.time()})
        noted("bulb", "A senior creative director ({}) reviewed the {}".format(str(found["model"] or "a stronger model").split("/")[-1],
                                                                               "run's shot plan" if plan_path else "plan"))
        if threaded and threaded[0].get("record"):
            await offload(threaded[0]["record"], "note", "Second opinion (auto): " + found["critique"],
                          {"model": found["model"], "auto": True, "run": run or None})
        return found["critique"]

    def no_run():
        return "This conversation keeps no state: open a project, or start the skill again from the Agent tab."

    def value_of(call):
        """The value to keep: any JSON as the model gives it. Text is read as JSON when it is JSON (what the tool took
        before it had a typed schema: '"the chase"', '{"a": 1}'), else kept as the words it is."""
        value = call.get("value")
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value or "null")
        except ValueError:
            return value

    async def state_read(call):
        if not shared.keeps_state and not str(call.get("path") or "").startswith(core.CATALOGUE):
            return no_run()
        try:
            found = await offload(shared.read, call.get("path"), call.get("offset") or 0, STATE_PAGE)
        except runs.RunError as error:
            return str(error)
        noted("book", "Read {} of the {}".format(found["path"], found.get("scope") or "run"))
        if found.get("folder"):
            shown = found["offset"] + len(found["leaves"])
            more = "" if shown >= found["total"] else "\n({} of {} shown: call again with offset {}.)".format(shown, found["total"], shown)
            return guardrails.framed_state(found, agent.external, more)
        return guardrails.framed_state(found, agent.external)   # a transcript or a file kept here: framed as outside text

    async def state_write(call):
        path = str(call.get("path") or "")
        if not shared.keeps_state and not path.startswith(core.CATALOGUE):
            return no_run()
        bare = (path[:-2] if path.endswith("/*") else path).strip().lower()
        plan_path = bare if agent.SHOT_PLAN.match(bare) and runs.PATH.match(bare) else None
        if plan_path and long_skill and not await run_marked("shot_plan"):
            # A skill's first shot plan: the concept comes first (sent back once a run), and the run now has a plan to review
            if await kept("/concept") is None and not await run_marked("concept_first"):
                await mark_run("concept_first")
                noted("retry", "The shot plan came before the concept, so the model was asked to write /concept first")
                return agent.CONCEPT_FIRST.format(path=plan_path)
        try:
            if path.endswith("/*"):   # every leaf of a folder at once
                written = await offload(shared.write_many, path[:-2], value_of(call), "agent")
                noted("book", "Wrote {} leaves under {}".format(written["written"], written["path"]))
                return "Written: {} leaves under {}".format(written["written"], written["path"])
            written = await offload(shared.write, path, value_of(call), "agent")
        except (runs.RunError, ValueError) as error:
            return "Not written: {}".format(error)
        noted("book", "Wrote {} of the {}".format(written["path"], written.get("scope") or "run"))
        if plan_path and long_skill and not await run_marked("shot_plan"):
            await mark_run("shot_plan", "/" + plan_path.split("/")[1])   # its folder: the whole plan is reviewed
        return "Written: {}".format(written["path"])

    async def craft_search(call):
        query = " ".join(str(call.get("query") or "").split())
        tags = [str(t) for t in call.get("tags") or [] if isinstance(t, str)][:8] if isinstance(call.get("tags"), list) else []
        found = craft_library.search(query, tags)
        noted("bulb", "Read the craft notes for “{}”: {}".format(query[:60], ", ".join(n["title"] for n in found) or "none fits"))
        return agent.fit_result(craft_library.for_tool(query, tags), agent.TOOL_RESULT, "craft_search")

    async def voices_tool(call):
        found, words = await state.router.voices(call.get("query"), call.get("language"))
        query = " ".join(str(call.get("query") or "").split())
        noted("bulb", "Looked up voices{}: {}".format(" for “{}”".format(query[:60]) if query else "", len(found) if found else "none"))
        if not found:
            return words or "No voice fits: try other words, or none."
        return agent.fit_result(json.dumps(found, ensure_ascii=False), agent.TOOL_RESULT, "voices")

    async def preset_search(call):
        query = " ".join(str(call.get("query") or "").split())
        noted("bulb", "Looked up presets for “{}”".format(query))
        return presets.for_tool(query, call.get("op"))

    async def memory_tool(call):
        op = str(call.get("op") or "").strip().lower()
        if not project:   # memory belongs to a module: a conversation in none keeps none, and reads none
            return recall.NO_MODULE
        try:
            if op == "remember":
                kept = await offload(recall.remember, state.db, user["id"], project, call.get("path"), call.get("value"))
                noted("book", "Saved to memory: {}".format(kept["key"]))
                return "Remembered {}: {}".format(kept["key"], kept["value"])
            if op == "forget":
                gone = await offload(recall.forget, state.db, user["id"], project, call.get("path"))
                noted("book", "Forgot {}".format(call.get("path")))
                return "Forgotten." if gone else "There was nothing at {}.".format(call.get("path"))
            if op == "recall":
                found = await offload(recall.recall, state.db, user["id"], project, call.get("value") or call.get("path"))
                return "\n".join("{}: {}".format(e["key"], e["value"]) for e in found) or "Nothing remembered like that."
        except recall.RecallError as error:
            return str(error)
        return "op is remember, recall or forget."

    # A skill is sent once. The model has those given whole with the message (in the system prompt while a long skill
    # runs), the ones read_skill gave it in this message, and, in its Claude session, those it gave it in the earlier
    # ones (_skill_sent).
    prompted = {s["id"] for s in picked if len(s["text"]) <= skills.MAX_CHARS} if long_skill else set()
    sent_now = set()

    def loaded(skill):
        """What the model is told when it asks for a skill it has: where that skill is, not the skill again."""
        noted("skill", "“{}” is loaded already in this conversation: not sent again".format(skill["title"]))
        if skill["id"] in prompted:
            return "“{}” is given to you whole, with the messages of this conversation: there is nothing more of it to read. " \
                   "Follow it as given.".format(skill["title"])
        if len(skill["text"]) <= skills.READ_WHOLE:
            return "“{}” is loaded already: read_skill gave it to you whole earlier in this conversation, and it is still " \
                   "there. Follow that copy; a skill is sent once.".format(skill["title"])
        return "“{}” is loaded already: its opening and the list of its parts are earlier in this conversation. Read a " \
               "part you have not read with its number in \"query\".".format(skill["title"])

    async def read_skill(call):
        named = str(call.get("op") or "").strip()
        whole = " ".join(str(call.get("query") or "").split()) in ("", "0")   # the skill, not one of its parts
        thread = threaded[0] if threaded else None
        skill = next((s for s in picked if s["id"] in (named, skills.canonical(named))), None)
        if skill is None and named and skills.find(named) and skills.find(named)["guide"]:
            # a tool's guide (how to write an ffmpeg command, a HyperFrames project): read whenever the work needs it,
            # beside whatever skill is in use, and never the run's own
            skill = skills.find(named)
            picked.append(skill)
            noted("skill", "Read the guide “{}”".format(skill["title"].split(" — ")[0]))
            whole = whole or len(skill["text"]) <= skills.READ_WHOLE
        elif skill is None and named and skills.find(named):   # a skill of the catalogue, loaded now: it is followed from here
            skill = skills.find(named)
            # A skill mid-way is not left for another unless the user asks for it, or it hands on to it or calls on a craft.
            under_way = skills.find(carried) if carried else next((s for s in picked if s["id"] in forced and len(s["text"]) > CHECKED_SKILL), None)
            handed = bool(under_way) and skill["id"] in under_way["next"]
            # Only the user picks a skill. Another is loaded when the user names it, or a skill in use hands on to it or
            # calls for it (a craft skill).
            called = any(skill["id"] in s["next"] for s in picked) or (skill["craft"] and bool(picked))
            if not picked and not asked_for(skill):
                noted("skip", "Did not load “{}”: the user picked no skill".format(skill["title"]))
                return ("The user has not picked a skill, and a skill is used only when the user picks it. Do the work without "
                        "one, or ask the user whether to use “{}”.".format(skill["title"]))
            if not handed and not called and not asked_for(skill):
                in_use = under_way or picked[0]
                noted("skip", "Did not load “{}”: “{}” is under way".format(skill["title"], in_use["title"]))
                return ("“{}” is in use. Do not load another skill in the middle of it unless the user asks for it or it calls "
                        "for it: finish its steps first, or ask the user whether to switch to “{}”.".format(in_use["title"], skill["title"]))
            # the run carries on with the skill it was handed to; a craft skill is a part of the one in use, which stays the run's
            if handed and run and len(skill["text"]) > CHECKED_SKILL and not skill["craft"]:
                await offload(runs.keep_skill, state.db, user["id"], run, project, skill["id"])
                noted("skill", "Handed on from “{}” to “{}”".format(under_way["title"], skill["title"]))
            picked.append(skill)
            turn["tags"].append(skill["id"])   # Langfuse's trace says it too, from the next call on
            whole = whole or len(skill["text"]) <= skills.READ_WHOLE
            if whole and _skill_sent(thread, skill["id"]):   # sent in an earlier message of this session: not again
                sent_now.add(skill["id"])
                return loaded(skill)
            noted("skill", "Loaded the skill “{}”".format(skill["title"]))
            if whole:
                # whole when it fits in one result, else its opening and its parts, each read when its step comes
                sent_now.add(skill["id"])
                _skill_sending(thread, skill["id"])
                return skills.guide([skill], skills.READ_WHOLE)
            # a part of a long skill loaded in an earlier message: that part, now that the skill is loaded again
        skill = skill or (picked[0] if len(picked) == 1 else None)
        if skill is None:
            return "Name the skill in op: {}.".format(", ".join(s["id"] for s in picked) or "no skill is in use")
        if skill["id"] in prompted or (skill["id"] in sent_now and (whole or len(skill["text"]) <= skills.READ_WHOLE)):
            return loaded(skill)
        text, problem = skills.read_part(skill, call.get("query"), call.get("offset") or 0)
        if problem:
            return problem
        noted("skill", "Read “{}” of “{}”".format(" ".join(str(call.get("query") or "").split())[:40], skill["title"]))
        return text

    def asked_for(skill):
        """Whether the user's message names this skill: by its id or its title. Its trigger words are not enough: a
        message that only fits a skill has not picked it."""
        said = " ".join(instruction.lower().replace("-", " ").split())
        short = skill["title"].split(" — ")[0].lower()   # "Brand motion — logo reveals, ..." is asked for as "brand motion"
        return skill["id"].replace("-", " ") in said or short in said or skill["title"].lower() in said

    def pages_here():
        return pages.root(state.assets_dir.parent, user["id"], project or 0)

    async def page_write(call):
        """A file of a motion project (pages.py), written whole as it is given."""
        try:
            done = pages.write(pages_here(), call.get("path"), call.get("value") if isinstance(call.get("value"), str) else "")
        except pages.PageError as error:
            return "Not written: {}".format(error)
        noted("code", "Wrote {}/{}".format(done["project"], done["path"]))
        return json.dumps(done)

    async def page_build(call):
        """A motion project's files written by the page writer (agent.build_pages) from the director's brief, in a call
        of its own: only what it wrote, the quick check and its notes come back here."""
        if not await within_limit(state, "page_build", user["id"]):
            return ("Not built: the page writer's limit ({} an hour) is reached; go on without it or wait."
                    .format(LIMITS["page_build"][0]))
        try:
            name, _ = pages.split(call.get("path"))
        except pages.PageError as error:
            return "Not built: {}".format(error)
        brief = str(call.get("text") or "").strip()
        if not brief:
            return "Not built: write the brief in text (the files, the scenes and their times, the look, the words, the assets)."
        base = pages_here()
        folder = base / name
        extra, missing = [], []
        for path in [p.strip() for p in re.split(r"[,\n]", str(call.get("query") or "")) if p.strip()][:BUILD_GUIDES]:
            words = await offload(_hyperframes_guide, path)
            if isinstance(words, str):
                extra.append("## {}\n\n{}".format(path, words[:BUILD_GUIDE_CHARS]))
            else:
                missing.append(path)
        have, room, listed = [], BUILD_FILES_CHARS, []
        for inner in await offload(pages.files, base, name):
            text = await offload((folder / inner).read_text, encoding="utf-8", errors="replace")
            if len(text) <= room:
                have.append("=== {} ===\n{}".format(inner, text))
                room -= len(text)
            else:
                listed.append(inner)
        message = "The project: {}\n\nThe brief:\n{}\n\n{}{}{}".format(
            name, brief[:BUILD_BRIEF_CHARS], "Its files now:\n\n" + "\n\n".join(have) if have else "It has no files yet.",
            "\n\nIts other files, too long to show here (leave them as they are unless the brief names them): " + ", ".join(listed)
            if listed else "", "\n\nMore guides to follow:\n\n" + "\n\n".join(extra) if extra else "")
        try:
            found = await state.agent.build_pages(await offload(_builder_guides), message, **_model(body))
        except agent.AgentError as error:
            return "Not built: {}".format(error)
        # Written on the user's behalf in their turn: charged as a message to that model is, by its tokens.
        cost = await offload(state.credits.message_cost, found["model"], found["tokens"])
        if cost:
            charged["credits"] += await offload(state.credits.charge_up_to, user["id"], cost, "agent", note="{} · pages".format(found["model"]),
                                                project_id=project or None)
        agent.add_tokens(tokens, found["tokens"])
        wrote, refused, removed = [], [], []
        for f in found["files"]:
            try:
                done = await offload(pages.write, base, "{}/{}".format(name, f["path"].strip("/")), f["text"])
                wrote.append({"path": done["path"], "characters": done["characters"]})
            except pages.PageError as error:
                refused.append("{}: {}".format(f["path"][:80], error))
        for path in found["remove"]:
            try:
                inner = pages.split("{}/{}".format(name, path.strip("/")))[1]
                if inner:
                    await offload(pages.remove, base, "{}/{}".format(name, inner))
                    removed.append(inner)
            except pages.PageError as error:
                refused.append("{}: {}".format(path[:80], error))
        try:
            width, height, seconds, needed = await offload(motion.quick_check, folder)
            checked = "passed: {}x{}, {:g} s{} (HyperFrames' whole check runs at the render)".format(
                width, height, seconds, "; give these as the render's media: " + ", ".join(needed) if needed else "")
        except motion.MotionError as error:
            checked = str(error)
        noted("code", "{} wrote {} file{} of {}".format(str(found["model"] or "the page writer").split("/")[-1].capitalize(),
                                                     len(wrote), "" if len(wrote) == 1 else "s", name))
        return json.dumps({"project": name, "wrote": wrote, "removed": removed, "not_written": refused, "check": checked,
                           "notes": found["notes"], "guides_not_found": missing}, ensure_ascii=False)

    async def page_read(call):
        """A file of a motion project, a project's files, or (under @hyperframes/) one of HyperFrames' own guides,
        presets and examples, read only."""
        path, offset = str(call.get("path") or "").strip(), max(0, int(call.get("offset") or 0))
        if path.startswith("@hyperframes"):
            words = await offload(_hyperframes_guide, path)
            if words is None:
                return "There is no {} among HyperFrames' guides, or it is not text.".format(path)
            if isinstance(words, list):
                return json.dumps(words)
        else:
            try:
                what, found = pages.read(pages_here(), path)
            except pages.PageError as error:
                return str(error)
            if what == "project":
                return json.dumps({"project": path.strip("/"), "files": found})
            words = found
        part = words[offset:offset + TEXT_PAGE]
        more = "" if offset + len(part) >= len(words) else "\n[{:,} of {:,} characters shown: call again with offset {}.]".format(
            offset + len(part), len(words), offset + len(part))
        return part + more

    async def book_import(call):
        """An asset sheet (sheet.py) brought into this module's NeuralCore: each row's picture fetched from its link."""
        from .. import sheet
        if not project:
            return "There is no NeuralCore here: it belongs to a project, and this message is in no project. Say so to the user."
        if isinstance(call.get("item"), int) and call["item"]:
            row = await offload(kit.item_in_module, state.db, user["id"], project, call["item"], "text")
            path = await offload(state.outputs.folder, row["user_id"]) / row["filename"] if row else None
            if not path or not path.is_file():
                return await offload(kit.refusal, state.db, user["id"], call["item"], "That is not a sheet in the library: give the id "
                                     "of the CSV the user attached, or the sheet's text in value.")
            text, called = path.read_text(encoding="utf-8-sig", errors="replace"), row["name"]
        else:
            text, called = str(call.get("value") or ""), "the sheet"
        try:
            rows, left = sheet.parse(text)
        except sheet.SheetError as error:
            return "Not brought in: {}".format(error)
        keeper = await offload(kit.keeper_of, state.db, user["id"], project)
        with core.as_everyone() if keeper != user["id"] else contextlib.nullcontext():
            done = await sheet.bring_in(state.db, state.assets_dir / str(keeper), keeper, project, rows)
        new = sum(1 for a in done["added"] if a["new"])
        noted("book", "Brought {} entr{} into NeuralCore from {}{}".format(new, "y" if new == 1 else "ies", called,
                                                                          ", {} failed".format(len(done["failed"])) if done["failed"] else ""))
        return json.dumps({"added": [{k: a[k] for k in ("asset", "name", "type")} for a in done["added"] if a["new"]],
                           "there_already": [{k: a[k] for k in ("asset", "name")} for a in done["added"] if not a["new"]],
                           "looks_linked": done["looks"], "failed": done["failed"], "rows_left_out": left}, ensure_ascii=False)

    async def read_text(call):
        from_core = isinstance(call.get("asset"), int) and bool(call["asset"])
        if from_core:   # a script kept in this module's kit
            row = await offload(kit.entry_in_module, state.db, user["id"], project, call["asset"], "text")
            path = state.assets_dir / str(row["user_id"]) / row["filename"] if row else None
        else:
            row = await offload(kit.item_in_module, state.db, user["id"], project, call.get("item"), "text")
            path = await offload(state.outputs.folder, row["user_id"]) / row["filename"] if row else None
        if not path or not path.is_file():
            return "That is not a text in this module's library or NeuralCore." if from_core else await offload(
                kit.refusal, state.db, user["id"], call.get("item"), "That is not a text in the library or NeuralCore.")
        words = path.read_text(encoding="utf-8-sig", errors="replace")
        if call.get("path"):
            try:
                await offload(shared.write, call["path"], words, "read_text")
            except runs.RunError as error:
                return "Not kept: {}".format(error)
            noted("book", "Kept “{}” in {} ({:,} characters)".format(row["name"], call["path"], len(words)))
        offset = max(0, int(call.get("offset") or 0))
        page = words[offset:offset + TEXT_PAGE]
        noted("book", "Read “{}”".format(row["name"]))
        more = "" if offset + len(page) >= len(words) else "\n[{:,} of {:,} characters shown: call again with offset {}.]".format(
            offset + len(page), len(words), offset + len(page))
        # a file in the library came from someone (an upload, a link, a transcription): framed as outside text. A script
        # in NeuralCore was written here.
        return (page if from_core else agent.external(page, "file")) + more

    async def read_transcript(call):
        if not shared.keeps_state:
            return no_run()
        from .. import transcript
        if not call.get("item") and call.get("value"):   # who speaks each line, from the script: only the speakers change
            try:
                names = _structured(call["value"])
                if not isinstance(names, dict):
                    raise ValueError
                lines = dict(await offload(shared.leaves, call.get("path")))
                changed = {}
                for n, who in names.items():
                    if isinstance(lines.get(str(n)), dict):
                        changed[str(n)] = dict(lines[str(n)], speaker=" ".join(str(who).split())[:60])
                if not changed:
                    return "None of those lines is at {}.".format(call.get("path"))
                await offload(shared.write_many, call.get("path"), changed, "speakers")
            except ValueError:
                return "value must be JSON text of {\"<line number>\": \"<speaker>\"}."
            except runs.RunError as error:
                return "Not written: {}".format(error)
            noted("book", "Named the speakers of {} lines".format(len(changed)))
            return json.dumps({"named": len(changed), "speakers": sorted({l["speaker"] for l in changed.values()})}, ensure_ascii=False)
        row = await offload(kit.item_in_module, state.db, user["id"], project, call.get("item"), "text")
        path = await offload(state.outputs.folder, row["user_id"]) / row["filename"] if row else None
        if not path or not path.is_file():
            return await offload(kit.refusal, state.db, user["id"], call.get("item"), "That item is not a transcript in the library.")
        try:
            lines = transcript.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
            written = await offload(shared.write_many, call.get("path"), {str(n): l for n, l in enumerate(lines, start=1)}, "transcript", replace=True)
        except (transcript.TranscriptError, runs.RunError) as error:
            return "Not read: {}".format(error)
        noted("book", "Read {} lines of “{}” into {}".format(len(lines), row["name"], written["path"]))
        speakers = sorted({l["speaker"] for l in lines})
        return agent.external(json.dumps({"written": len(lines), "path": written["path"], "speakers": speakers, "first": lines[:3],
                                          "last": lines[-1]}, ensure_ascii=False), "transcript")

    async def timing(call):
        if not shared.keeps_state:
            return no_run()
        from .. import transcript
        try:
            asked = _structured(call.get("settings"))
            length = float(asked["length"])
            units = [dict(value, id=name) for name, value in await offload(shared.leaves, asked["units"]) if isinstance(value, dict)]
            lines = {int(n): v for n, v in await offload(shared.leaves, asked["lines"]) if n.isdigit() and isinstance(v, dict)}
            speech = {int(n): v for n, v in shared.leaves(asked["speech"]) if n.isdigit()} if asked.get("speech") else {}
        except (ValueError, KeyError, TypeError) as error:
            return "settings must be JSON text with units, lines, length and save_to ({}).".format(type(error).__name__)
        except runs.RunError as error:
            return str(error)
        if not units or not lines:
            return "No units or no lines were found at those paths."
        frames, problems = transcript.grid(units, lines, speech, length)
        if frames:
            try:
                await offload(shared.write_many, asked.get("save_to") or "", frames, "timing", replace=True)
            except runs.RunError as error:
                return "Not written: {}".format(error)
        noted("clock", "Timed {} shots{}".format(len(frames), ", {} to fix".format(len(problems)) if problems else ""))
        return json.dumps({"timed": len(frames), "frames": sum(f["f_out"] - f["f_in"] for f in frames.values()),
                           "problems": problems[:40]}, ensure_ascii=False)

    async def state_check(call):
        if not shared.keeps_state:
            return no_run()
        try:
            found = await offload(shared.coverage, call.get("path"), call.get("against"))
        except runs.RunError as error:
            return str(error)
        noted("check", "Checked {} against {}: {}".format(call.get("path"), call.get("against"),
                                                         "complete" if found["ok"] else "{} missing".format(len(found["missing"]))))
        return json.dumps(found, ensure_ascii=False)

    async def film_op(call):
        """One film operation, queued and waited for (they are quick, free and made on this machine). html and ffmpeg
        are tools of their own now (render_html, ffmpeg); a session begun before still names them here: they still run,
        and the answer says which tool to call next time. An op there is not gets the list, and those two tools named."""
        op = call.get("op")
        if op not in edits.FILM:
            return agent.film_op_unknown(op)
        try:
            settings = _structured(call.get("settings"))
            if not isinstance(settings, dict):
                raise ValueError
        except ValueError:
            return "settings must be an object of the operation's fields."
        if op == "html" and not settings.get("html"):   # the page came as it is in "value", not inside the JSON
            settings["html"] = call.get("value") or ""
        done = await film_done(op, settings)
        return done + agent.FILM_MOVED_NOTE.format(op=op, tool=agent.FILM_MOVED[op]) if op in agent.FILM_MOVED else done

    async def render_html(call):
        """A page or a motion project drawn by HyperFrames: the film tool's html op."""
        return await film_done("html", {k: call[k] for k in RENDER_FIELDS if call.get(k) not in (None, "")})

    async def ffmpeg_job(call):
        """The agent's own ffmpeg command: the film tool's ffmpeg op, checked by ffjob.check when it is queued."""
        return await film_done("ffmpeg", {k: call[k] for k in FFMPEG_FIELDS if k in call})

    async def film_done(op, settings):
        """A film operation queued and waited for: the library ids of what it made, as the model is told them."""
        from .film import queue as film_queue   # film.py builds on this module
        try:
            settings = await offload(shared.resolve_all, settings) if shared.keeps_state else settings
            if settings.get("save_to"):   # the speech spans are kept where save_to points: the episode, most often
                place = shared._writable(settings["save_to"])
                settings = dict(settings, save_to=place.path, **({"state_run": place.run} if place.run != run else {}))
            queued = await offload(film_queue, request, user, dict(settings, op=op, run=run, project_id=project or None), module=project or 0)
        except runs.RunError as error:
            return str(error)
        except HTTPException as error:
            return "Not done: {}".format(error.detail)
        noted("wrench", "{} ({})".format(edits.FILM[op][1], queued["name"]))
        job = await _finished(state, queued["job"])
        if job["status"] != "done":
            return "The {} failed: {}".format(op, job.get("error") or job["status"])
        made = await state.db.aall("SELECT id, kind, name, context FROM generations WHERE job_id = ? ORDER BY id", (queued["job"],))
        made_now.extend(r["id"] for r in made)   # made in this message by the agent's own tools, no step needed
        return agent.fit_result(json.dumps([{"item": r["id"], "kind": r["kind"], "name": r["name"], **json.loads(r["context"] or "{}")}
                                            for r in made], ensure_ascii=False), agent.TOOL_RESULT)

    async def web_fetch(call):
        try:
            found = await web.page(call.get("text"))
        except web.WebError as error:
            return "Not read: {}".format(error)
        noted("search", "Read “{}” on the web".format((found["title"] or found["url"])[:80]))
        offset = max(0, int(call.get("offset") or 0))
        page = found["text"][offset:offset + TEXT_PAGE]
        more = "" if offset + len(page) >= len(found["text"]) else "\n[{:,} of {:,} characters shown: call again with offset {}.]".format(
            offset + len(page), len(found["text"]), offset + len(page))
        head = json.dumps({"url": found["url"], "title": found["title"], "date": found["date"] or "undated"}, ensure_ascii=False)
        return agent.external("{}\n{}".format(head, page or "(the page has no words to read)"), "web", found["url"]) + more

    async def skill_draft(call):
        try:
            draft = skills.save_draft({"title": call.get("text"), "desc": call.get("query"), "text": call.get("value"), "id": call.get("op")},
                                      {"id": user["id"], "name": user.get("name")})
        except ValueError as error:
            return "Not drafted: {}".format(error)
        drafted.append(draft["id"])
        noted("skill", "Drafted the skill “{}” for an admin to publish".format(draft["title"]))
        return json.dumps({"draft": draft["id"], "title": draft["title"], "waits_for": "an admin to publish it in the console"}, ensure_ascii=False)

    async def ask_opinion(about, item=None, purpose="second_opinion"):
        """A second opinion on `about` (and the frames of library item `item`). The second_opinion tool's is charged to
        the user as a message to that model is; the studio's own (purpose agent.AUTO_OPINION) never is: its tokens are
        written down with "charged": False and the run, and left out of the user's count. Returns
        agent.second_opinion's answer; raises agent.AgentError."""
        auto = purpose == agent.AUTO_OPINION
        pictures, labels = [], []
        row = await offload(kit.item_in_module, state.db, user["id"], project, item)
        if row and row["kind"] in ("image", "video") and (await offload(state.outputs.folder, row["user_id"]) / row["filename"]).is_file():
            try:
                for label, picture in (await review.result_frames(await offload(state.outputs.folder, row["user_id"]) / row["filename"], row["kind"]))[:SECOND_OPINION_FRAMES]:
                    pictures.append(picture)
                    labels.append(label)
            except (review.ReviewError, media.MediaError):
                pass
        found = await state.agent.second_opinion(about, pictures, labels, **({"purpose": purpose, "metadata": {"charged": False, "run": run or ""}}
                                                                            if auto else {}), **_model(body))
        if auto:   # the studio's own review: the studio pays
            return found
        # Asked on the user's behalf in their turn: charged as a message to that model is, by its tokens.
        cost = await offload(state.credits.message_cost, found["model"], found["tokens"])
        if cost:
            charged["credits"] += await offload(state.credits.charge_up_to, user["id"], cost, "agent", note="{} · second opinion".format(
                found["model"]), project_id=project or None)
        agent.add_tokens(tokens, found["tokens"])
        return found

    async def second_opinion(call):
        about = str(call.get("text") or "").strip()[:8000]
        if not about:
            return "Say in text what the second opinion is about."
        if call.get("item") and await offload(kit.item_in_module, state.db, user["id"], project, call["item"]) is None:
            return await offload(kit.refusal, state.db, user["id"], call["item"], "No such item.")
        try:
            found = await ask_opinion(about, call.get("item"))
        except agent.AgentError as error:
            return "No second opinion this time: {}".format(error)
        noted("bulb", "Asked {} for a second opinion".format(str(found["model"] or "a stronger model").split("/")[-1]))
        return found["critique"]

    async def workflow_info(call):
        found = agent.workflow_info(offers, call.get("op"))
        if found.startswith("{"):
            noted("plan", "Read the workflow {}".format(str(call.get("op")).strip()))
        return found

    async def import_url(call):
        from .. import fetch
        from .library import IMPORTED, _file_in   # library.py files what is brought in
        url = str(call.get("text") or "").strip()
        try:
            data, kind, final = await fetch.fetch(url)
        except fetch.FetchError as error:
            return "Not brought in: {}".format(error)
        made = await _file_in(request, user, data, fetch.filename_for(final, kind, data), kind, project or None, "Brought in from a link",
                              workflow=IMPORTED, name=" ".join(str(call.get("query") or "").split())[:80], source=url)
        noted("attach", "Brought in “{}” from a link".format(made["name"]))
        return agent.external(json.dumps({"item": made["id"], "kind": kind, "name": made["name"], **made["context"]}, ensure_ascii=False),
                              "link", final)

    threaded = []   # the thread of the conversation with Claude, when it keeps one (_thread)

    tools = {"find_assets": find_assets, "look": look, "check_shots": check_shots, "review": review_it, "save_note": save_note,
             "book_save": book_save, "book_import": book_import, "page_build": page_build, "page_write": page_write, "page_read": page_read,
             "state_read": state_read, "state_write": state_write, "state_check": state_check, "film": film_op,
             "render_html": render_html, "ffmpeg": ffmpeg_job, "import_url": import_url,
             "transcript": read_transcript, "timing": timing, "read_text": read_text, "read_skill": read_skill, "memory": memory_tool,
             "preset_search": preset_search, "craft_search": craft_search, "web_fetch": web_fetch, "skill_draft": skill_draft, "second_opinion": second_opinion,
             "workflow_info": workflow_info, "voices": voices_tool}
    # Workflows in full only of the kinds the message (or the user's turn before it) is about: the rest go as one line each,
    # read in full with workflow_info (they were about 28,000 characters of every first message, the video models'
    # prompt guides most of it). A skill in use names what it needs: then every workflow goes in full, as before.
    earlier = [t.get("instruction") for t in (body.get("history") or [])[-1:] if isinstance(t, dict)] \
        if isinstance(body.get("history"), list) else []
    detailed = agent.likely_kinds([instruction, *earlier]) if with_tools and not picked else None
    drafted = []   # the skills drafted in this message (skill_draft)
    made_now = []  # what the film tool made in this message: work done without a step
    explain = body.get("explain") is True   # the panel's "Explain more": the reply may teach

    canvas_boards = await offload(boards_text, state, user["id"], project) if project else ""
    # A message that looks like a big job comes with the craft note that fits it and the closest examples of strong
    # work (craft_library): in the message, so the system prompt stays the same for the whole conversation.
    craft_given = ""
    if with_tools and not long_skill and agent.looks_big(instruction, body.get("history")):
        earlier_said = " ".join(str(t.get("instruction") or "") for t in (body.get("history") or [])[-1:] if isinstance(t, dict))
        about_job = "{} {}".format(instruction, earlier_said if len(instruction) < 60 else "").strip()
        craft_given = "\n\n".join(p for p in (await offload(craft_library.pointer, about_job),
                                              await offload(craft_library.examples_part, about_job)) if p)
        if craft_given:
            noted("bulb", "Found the craft note and the examples of strong work that fit this job")

    async def plan(message):
        """One answer of the model, timed, and the steps of it that can run. Returns (answer, steps, dropped, seconds)."""
        asked = time.monotonic()
        system = agent.system() + ("\n\n" + "\n\n".join([recall.RULES, presets.RULES, craft_library.RULES, agent.RESEARCH_RULES, agent.SKILL_RULES, phonetic.RULES])
                                   if with_tools else "")
        # A long skill goes first, in the system prompt: every call of a run then opens the same way, and a hosted
        # service can read that opening from its cache instead of anew (the rest of the message changes as the run goes).
        first = long_skill and with_tools
        if first:
            system += "\n\n" + agent.skills_part(guides)
        parts = agent.question_parts(message, offers, selection, state.catalog.current(state.settings.default_workflow),
                                     agent.past_turns(body.get("history")), pinned, recent, memory.book_for_model(book),
                                     "" if first else guides, body.get("direction") or "",
                                     (await offload(recall.digest, state.db, user["id"], project) if project else None) if with_tools else None,
                                     skills.catalogue(picked) if with_tools and not long_skill else "", explain if with_tools else None,
                                     canvas_boards if with_tools and project else None, detailed, craft_given)
        full = "\n\n".join(text for _, text in parts)
        # A conversation with Claude goes on in one session (a thread): a later message sends only what is new.
        thread = await offload(_thread, state, user, project, body, chosen_model, system)
        threaded[:] = [thread] if thread is not None else []
        traces.SESSION.set(thread["key"] if thread is not None else "")   # the Agent tab, as Langfuse shows it

        # The answer's shape names the workflows a step may use: every readable one switched on for the user, sorted, not
        # only those offered to this message. Claude's session is opened again (a new Claude Code process) whenever its shape
        # changes, and the offered ones change as the conversation goes (a picture attached, a workflow named); which
        # can run is still checked step by step.
        answer_ids = sorted({w["id"] for w in every_workflow if not w.get("error") and w["id"] in usable_ids} | {o["id"] for o in offers})

        async def asked_with(asking):
            going = {"thread": thread} if thread is not None else {}
            if with_tools:   # the model works in a loop of tool calls, and may search the web
                return await state.agent.ask_with_tools(system, asking, answer_ids, tools, finishing, rounds=rounds,
                                                        **going, **_model(body), **({"web": True} if _hosted_claude(state) else {}),
                                                        **({"reply_chars": agent.RUN_REPLY_CHARS} if long_skill else {}))
            return await state.agent.ask(system, asking, answer_ids, **going, **_model(body))

        if thread is None:
            answer = await asked_with(full)
        else:
            # The tab's session is kept for admins to watch (sessions.py): what is asked and sent, and (claude.py) all
            # Claude does in it.
            row = await offload(_session_of, state, user, project, body, chosen_model, thread)
            record, hosted = thread["record"], _hosted_claude(state) or {}
            window = hosted.get("window") or claude.WINDOW
            if row["model"] != chosen_model and row["messages"]:
                await offload(record, "model", "Model changed: {} → {}".format(row["model"], chosen_model), {"from": row["model"], "to": chosen_model})
            await offload(record, "user", message)
            going_on = bool(thread.get("id"))
            # Near the end of its context the session is compacted first (Claude Code also does it by itself, at the
            # same point, in the middle of a turn): it goes on, the same session, from a summary of what came before.
            if going_on and sessions.fullness(thread.get("size") or 0, window) >= sessions.COMPACT:
                before = thread.get("size") or 0
                try:
                    after = await claude.compact(hosted, thread)
                    noted("book", "Compacted this conversation's context: it was {}% full{}".format(
                        round(100 * before / window), ", now {}%".format(round(100 * after / window)) if after else ""))
                except (claude.Failed, claude.Busy) as error:
                    record("error", "Could not compact: {}".format(error))
                except claude.Lost:
                    thread["id"], going_on = None, False
            # A compaction (here, in the user's Compact, or by Claude Code in the middle of a turn) keeps a summary of the
            # conversation, not its parts word for word: the message after one sends every part again.
            seen = thread["seen"] if thread.get("seen_at", 0) == (thread.get("compacted") or 0) else {}
            asking = agent.follow_up(parts, seen) if going_on else full
            if going_on and thread.get("missed"):
                asking = _missed_text(thread["missed"]) + "\n\n" + asking
                await offload(record, "note", "Sent along {} turns another model answered".format(len(thread["missed"])))
            thread.update(seen=agent.fingerprints(parts), seen_at=thread.get("compacted") or 0, full=full)
            await offload(record, "prompt", asking, {"going_on": going_on, "model": chosen_model})
            started_with = thread.get("id")
            try:
                answer = await asked_with(asking)
            except agent.ContextLost:   # its session is gone: the conversation starts a new one, with the whole message
                record("note", "The Claude session was gone: a new one starts, with the whole message")
                thread["id"] = None
                started_with = None
                answer = await asked_with(full)
            except Exception as error:
                await offload(record, "error", str(error) or type(error).__name__)
                raise
            # A turn another model answered (Claude was busy) is not in the session: the next message sends it along.
            thread["stood_in"] = answer.get("model") != chosen_model
            await offload(record, "answer", str(answer.get("reply") or ""), {"model": answer.get("model") or chosen_model, "steps": len(answer.get("steps") or []),
                                                             "question": bool(answer.get("question")), "tokens": answer.get("tokens")})
            if not thread["stood_in"]:
                await offload(sessions.update, state.db, row["id"], claude_id=thread.get("id"), model=chosen_model, messages=1,
                                context_tokens=thread.get("size") or 0, context_window=window)
                thread["context"] = sessions.context(thread.get("size") or 0, window)
                if thread.get("id") and thread["id"] != started_with:   # a new session: it gets its title, for VS Code's list
                    name = sessions.title(body.get("tab"), await offload(_project_name, state, project), user.get("name"))
                    await offload(sessions.update, state.db, row["id"], title=name)
                    _soon(claude.rename(hosted, dict(thread), name))
            if going_on:
                noted("book", "Went on with this conversation's Claude session: sent only what is new")
        seconds = time.monotonic() - asked
        # Each answer is charged at the price of the model that gave it (another one may have stood in for a busy one): a
        # flat price per message, or a Claude model's tokens. The tokens were used already, so a user who has fewer
        # credits than they cost gives all they have.
        used = answer.get("model") or chosen_model
        cost = await offload(state.credits.message_cost, used, answer.get("tokens"))
        if cost:
            cost = await offload(state.credits.charge_up_to, user["id"], cost, "agent", note=used, project_id=project or None)
            charged["credits"] += cost
            charged["model"] = used
        steps, dropped = await build(answer["steps"])
        if answer.get("tools") is not None:
            answer["tools"] = list(answer["tools"])
            searched = sum(1 for name in answer["tools"] if name in claude.WEB_TOOLS)
            if searched:   # Claude Code searched the web itself: no studio tool saw it
                noted("search", "Searched the web{}".format(" {} times".format(searched) if searched > 1 else ""))
        if answer.get("empty_sent_back"):
            noted("retry", "The model stopped with nothing to show, so it was asked to carry on")
        agent.add_tokens(tokens, answer.get("tokens"))
        return answer, steps, dropped, seconds

    async def build(raw):
        """The steps of an answer that can be carried out, priced, and the ones left out with the reason. Nothing is queued."""
        steps, dropped = [], []
        made_by = {}   # the number the model gave a step (1 for its first) -> where that step's result is in `steps`
        for number, proposed in enumerate(raw[:agent.MAX_STEPS] if isinstance(raw, list) else [], start=1):
            made_by[number] = len(steps)   # taken back below if the step is dropped
            before = len(steps)
            # Separating a voice or transcribing is work on a sound, and a model often calls it "sound": a sound step
            # that names a workflow made to take a sound file is that workflow's step, not a sound put on a video.
            if isinstance(proposed, dict) and proposed.get("tool") == agent.SOUND_TOOL and proposed.get("workflow") in hears:
                proposed = dict(proposed, tool="generate")
            if isinstance(proposed, dict) and proposed.get("tool") == agent.SOUND_TOOL:
                made = agent.sound_for(proposed, known)
                if made:   # a sound on a video: queued on Approve through the sound endpoint, which costs nothing
                    placed = {}
                    planned_fields(placed, proposed, [])
                    made["sound"].update({k: v for k, v in placed.items() if k in ("shot_number", "shot_numbers", "board")})
                    steps.append({"name": made["name"], "workflow_title": "Sound", "kind": "video", "prompt": "", "facts": made["facts"],
                                  "time": "a few seconds", "credits": 0, "settings": None, "start": None, "sound": made["sound"]})
                reason = None if made else agent.NO_SOUND_EDIT
            elif isinstance(proposed, dict) and proposed.get("tool") == agent.ASSEMBLE_TOOL:
                # the shots in order; of a shot made in several variations, the first stands in the cut
                planned = [n for n, s in enumerate(steps) if s["kind"] == "video" and s.get("settings") and (s.get("variation") or {}).get("n", 1) == 1]
                music_at = made_by.get(proposed.get("after"))
                music_planned = music_at is not None and music_at < len(steps) and steps[music_at]["kind"] == "audio" and bool(steps[music_at].get("settings"))
                named = await _named_videos(state, user, project, proposed)   # the takes it names, else the selected videos
                made = agent.assemble_for(proposed, planned, named or videos, known, music_planned,
                                          ((steps[planned[0]].get("current") or {}).get("orientation") if planned else None))
                if made:   # the finished cut: queued on Approve once the shots (and music) are made
                    made["assemble"]["music_step"] = music_at if music_planned else None
                    steps.append({"name": made["name"], "workflow_title": "Final cut", "kind": "video", "prompt": "", "facts": made["facts"],
                                  "time": "under a minute", "credits": 0, "settings": None, "start": None, "assemble": made["assemble"]})
                reason = None if made else "there were no shots or selected videos to put together"
            else:
                wanted = str(proposed.get("workflow") or "") if isinstance(proposed, dict) else ""
                if wanted and wanted not in schemas and wanted.split("/", 1)[0] in pinned_kinds:
                    instead = next((w for w in chat_pins if w in schemas and w.split("/", 1)[0] == wanted.split("/", 1)[0]), None)
                    if instead:
                        noted("plan", "“{}” was planned on {}, which this chat does not use: it is made on {}".format(
                            proposed.get("name") or "a step", wanted, schemas[instead]["title"]))
                        proposed = dict(proposed, workflow=instead)
                cut_from = videos
                if isinstance(proposed, dict) and proposed.get("tool") in agent.EDIT_TOOLS + agent.MOTION_TOOLS:
                    cut_from = await _named_videos(state, user, project, proposed) or videos   # the videos it names, else the selected
                reason = await _plan_step(state, proposed, instruction, steps, made_by, schemas, names, kinds, cut_from, pinned, project, shapes, book_assets,
                                          menu, shared)
                if len(steps) > before and steps[-1].get("settings"):
                    vary(steps, proposed)
            if len(steps) == before:
                del made_by[number]
                if reason:
                    dropped.append(((proposed.get("name") if isinstance(proposed, dict) else "") or "a step", reason))
        return steps, dropped

    def thought(answer, seconds):
        return logged({"type": "thought", "text": str(answer.get("thought") or ""), "seconds": round(seconds, 1)})

    tokens = {}   # what the model read and wrote for this message, every call added up
    message = agent.carry_over(instruction, body.get("history"))
    yield status("Thinking…")
    # The model is asked in a task, so what its tools do is shown while it works (a long run makes dozens of calls),
    # and the stream keeps moving. A closed stream (the user pressed Stop) stops the work too.
    async def live(asking):
        task = asyncio.ensure_future(plan(asking))
        try:
            while True:
                done, _ = await asyncio.wait([task], timeout=LIVE_EVERY)
                while tool_events:
                    yield activity(*tool_events.pop(0))
                if done:
                    break
                yield status("Working…" if run else "Thinking…")
        finally:
            if not task.done():
                task.cancel()
        result[:] = [task.result()]

    result = []
    async for event in live(message):
        yield event
    answer, steps, dropped, seconds = result[0]
    if saved_direction and not answer.get("direction"):
        answer["direction"] = saved_direction[0]
    yield thought(answer, seconds)
    # A reply that says it is making something while no step survived would leave the user waiting for nothing:
    # the model is asked once more, and if it still plans nothing, the reply says plainly that nothing was made.
    # The same when the model said the message approves what its last reply proposed ("go_ahead") and asked nothing.
    def claims(answer):
        return agent.claims_work(instruction, answer["reply"], answer.get("claims_making"))

    def went_ahead(answer):
        return answer.get("go_ahead") is True and not answer.get("question") and not answer.get("questions")
    if not steps and not made_now and (claims(answer) or went_ahead(answer)):
        yield activity("retry", "The first answer said it was making something but planned nothing, so I asked again"
                       if claims(answer) else "The message approved the last idea but nothing was planned, so I asked again")
        yield status("Thinking again…")
        async for event in live(message + "\n" + agent.NO_STEPS):
            yield event
        answer, steps, dropped, seconds = result[0]
        yield thought(answer, seconds)
        if not steps and not made_now and claims(answer):
            answer["reply"] = agent.EMPTY_CLAIM
    for name, reason in dropped:
        yield activity("skip", "Left out “{}”: {}".format(name, reason))
    if not steps and agent.wants_sound(instruction, body.get("history"), answer.get("wants_sound")):
        made = agent.sound_for({}, known)   # the model only talked: make the step that was asked for
        if made:
            steps.append({"name": made["name"], "workflow_title": "Sound", "kind": "video", "prompt": "", "facts": made["facts"],
                          "time": "a few seconds", "credits": 0, "settings": None, "start": None, "sound": made["sound"]})
            answer["reply"] = "I'll put {}. Approve to make it.".format(made["facts"])
    steps = steps[:agent.MAX_STEPS]
    for step in steps:   # every generation is a shot with an id of its own: a retake becomes take 2 of the same shot
        if step.get("settings"):
            step["shot_id"] = uuid.uuid4().hex[:8]
            step["settings"]["shot"] = {"id": step["shot_id"], "take": 1}
            # its results stack on the canvas by this group; the variations of one shot stack together, on the first's
            first = next((s for s in reversed(steps[:steps.index(step)]) if (s.get("variation") or {}).get("n") == 1), None) \
                if (step.get("variation") or {}).get("n", 1) > 1 else None
            step["settings"]["placement_group"] = (first or step)["shot_id"]
            if run:   # the job is tagged as the run's
                step["settings"]["run_of"] = run
            step["settings"]["turn"] = traces.mark()   # its render joins this turn's trace in Langfuse once approved
    # The content check (content_check.py): the fast model reads the plan's words before it is shown for Approve. A
    # "block" (in the mode that blocks) refuses it plainly; a "warn" is one line on the plan card. It fails open.
    content_note = ""
    checked = await content_check.check(state.agent, state.db, user["id"], steps, instruction) if steps else None
    if checked and checked.get("error"):
        yield activity("skip", "The content check could not run this time, so the plan goes on without it")
    elif checked and content_check.problem(checked):
        yield activity("skip", "The content check stopped this plan: {}".format(", ".join(checked["categories"]) or "flagged"))
        answer["reply"], steps = content_check.problem(checked), []
    elif checked and checked["flag"] == "warn":
        yield activity("check", "The content check flagged this plan: {}".format(", ".join(checked["categories"]) or "a note"))
        content_note = checked["note"]
    if steps:
        yield activity("plan", "Checked and priced {} {}".format(len(steps), "step" if len(steps) == 1 else "steps"))
    if tokens.get("prompt"):
        yield activity("info", "Read {:,} tokens{} and wrote {:,}".format(
            tokens["prompt"], " ({:,} from the cache)".format(tokens["cached"]) if tokens.get("cached") else "", tokens.get("answer", 0)))
    # Items the reply names as [[item:12]] or [[asset:3]] are shown as small pictures; the browser gets their names.
    # a reply the user's memory shaped names the keys it used on its last line: shown as chips, not as words
    said, remembered = recall.used_in(answer["reply"] or "", {e["key"] for e in await offload(recall.entries, state.db, user["id"], project)})
    chips, reply = agent.chips_in(said, await offload(_named_here, state, user, project, said, {**book_items, **known}), book_assets)
    await offload(_linked, state, chips)
    if charged["credits"]:
        state.notify(user["id"])   # the open pages show the new balance
    # A reply left empty: in a long run the model stopped mid-step, and "go" carries on; otherwise it has nothing to make.
    nothing = RUN_STOPPED if run and long_skill else "Tell me what you would like to see and I will plan it."
    reply = reply or ("Here is the plan." if steps else nothing)
    asked_all = agent.clean_questions(answer.get("questions"))   # several questions, answered together
    stepped = list(dict.fromkeys(s["resolution_note"] for s in steps if s.get("resolution_note")))
    if stepped:   # an admin switched a resolution off: the plan is made at the next one, and the reply says so
        reply += "\n\n" + " ".join(stepped)
    if await offload(_grading, state):   # a share of the turns is graded by the fast model, beside the answer (never charged)
        _soon(_grade(state, instruction, picked, reply, steps, answer.get("question"), _model(body).get("model")))
    for thread in threaded:   # the next message goes on with this session when its history ends with this reply
        await offload(_keep_thread, state, user, project, body, chosen_model, thread, None if thread.get("stood_in") else reply)
    concept = agent.clean_concept(answer.get("concept"))   # a big job's idea in one sentence: kept for the messages after
    if concept and shared.keeps_state and not long_skill:
        try:
            await offload(shared.write, "/concept", concept, "agent")
        except (runs.RunError, ValueError):
            pass   # a module this user may only read: the plan stands without it
    yield {"type": "plan", "reply": reply, "concept": concept, "content_note": content_note,
           "thought": str(answer.get("thought") or ""), "activity": log, "seconds": round(time.monotonic() - started, 1),
           "chips": chips, "memory_used": remembered, "direction": answer.get("direction") or "", "steps": steps, "total": sum(s["credits"] for s in steps), "llm": charged,
           "balance": await offload(state.credits.balance, user["id"]), "question": None if asked_all else agent.clean_question(answer.get("question")),
           "questions": asked_all, "run": run,
           # a long skill's run goes on by itself: once these steps are made, the Agent tab tells the agent what they made;
           # a turn that made nothing but saved its work (a stage of planning) goes on at once
           "continues": bool(run and long_skill and not answer.get("question") and not answer.get("questions")
                             and (steps or await offload(shared.saved_since, since))),
           "tokens": tokens, "drafts": drafted, "explain": explain,
           # how full the Claude session's context is: past 80% the panel offers to compact it now
           "context": next((t.get("context") for t in threaded if t.get("context")), None)}


def _grading(state):
    """Whether this turn is one the fast model grades for Langfuse: langfuse_grade_share percent of them, when a
    Langfuse is in use. Off (0) unless an admin sets it in the console's Settings."""
    try:
        share = float(state.db.setting("langfuse_grade_share", "0") or 0)
    except ValueError:
        return False
    sender = getattr(state.traces, "langfuse", None)
    return share > 0 and sender is not None and random.random() * 100 < share and sender.target() is not None


async def _grade(state, instruction, picked, reply, steps, question, model):
    """The fast model's grade of one turn (did it follow its skill, is the reply clear, are the steps sensible), sent to
    Langfuse as the score "claude-grade" on the turn's trace, and the creative rubric's marks beside it as
    "creative-idea", "creative-hook" ... (1 to 5, docs/creative-rubric.md). The call is written down as a "grade" like
    any other; it is never charged to the user."""
    found = await state.agent.grade(instruction, picked, reply, steps, question, model)
    run = traces.RUN.get()
    state.traces.langfuse.score(run, "claude-grade", found["score"], found["why"])
    for mark, value in (found.get("rubric") or {}).items():
        state.traces.langfuse.score(run, "creative-" + mark.replace("_", "-"), value)


def _referenced(proposed, shared):
    """(the step with its state references put in, where its result is kept or None), or (None, the reason it can't run).
    "$state:/path" may stand in a prompt (the words kept there), in start_from, source and audio (a library id), in a
    reference's item or asset, and in the words of a motion scene; "save_to" names the state path its result goes to."""
    text = json.dumps(proposed, ensure_ascii=False)
    if "$state:" not in text and not proposed.get("save_to"):
        return proposed, None
    if shared is None or not shared.keeps_state:
        return None, "it names the state, and this conversation keeps none"

    def library_id(value):
        found = shared.resolve(value)
        if isinstance(found, bool) or not isinstance(found, (int, dict)) or (isinstance(found, dict) and not found.get("asset")):
            raise runs.RunError("{} does not hold a library item".format(value))
        return found

    out = dict(proposed)
    try:
        for key in ("prompt", "name", "end_state"):
            if isinstance(out.get(key), str) and "$state:" in out[key]:
                out[key] = shared.fill_text(out[key])
        for key in ("start_from", "source", "audio"):
            if isinstance(out.get(key), str) and out[key].startswith("$state:"):
                found = library_id(out[key])
                if isinstance(found, dict):
                    raise runs.RunError("{} must be a library item, not a NeuralCore entry".format(key))
                out[key] = found
        if isinstance(out.get("uses"), list):
            uses = []
            for use in out["uses"]:
                if isinstance(use, dict):
                    use = dict(use)
                    for key in ("item", "asset"):
                        if isinstance(use.get(key), str) and use[key].startswith("$state:"):
                            found = library_id(use[key])
                            use["item"], use["asset"] = (0, found["asset"]) if isinstance(found, dict) else (found, 0)
                uses.append(use)
            out["uses"] = uses
        if isinstance(out.get("scenes"), list):
            out["scenes"] = [dict(s, **{k: shared.fill_text(s[k]) for k in ("heading", "text") if isinstance(s.get(k), str) and "$state:" in s[k]})
                             if isinstance(s, dict) else s for s in out["scenes"]]
        slot = core.slot_of(shared, out["save_to"]) if isinstance(out.get("save_to"), str) and out["save_to"].strip() else None
    except runs.RunError as error:
        return None, "{}".format(error)
    return out, slot


async def _plan_step(state, proposed, instruction, steps, made_by, schemas, names, kinds, videos, pinned, project, shapes, assets=None, menu=None,
                     shared=None):
    """Check one step the model proposed and add what can be carried out to `steps`. A step that can't run adds nothing,
    and the reason is returned (None when the step was added, or when leaving it out is not worth saying).
    shared: the conversation's core.Core, for the state references in the step and its save_to."""
    if not isinstance(proposed, dict):
        return "it could not be read"
    proposed, slot = await offload(_referenced, proposed, shared)
    if proposed is None:
        return slot
    said_as = []
    if proposed.get("tool", "generate") == "generate" and str(proposed.get("workflow") or "").startswith("video/") and proposed.get("prompt"):
        # Hindi or Hinglish words a video model says wrong are respelled in the spoken lines before the prompt goes
        respelled, said_as = phonetic.respell(proposed["prompt"], proposed.get("phonetic") or [])
        proposed = dict(proposed, prompt=respelled)
    if proposed.get("tool") in agent.MOTION_TOOLS:
        # Words and shapes drawn by HyperFrames: queued on Approve through the motion endpoint, which charges by the length.
        made = agent.motion_for(proposed, videos)
        if made:
            scenes = made["motion"].get("scenes")
            seconds = sum(s["seconds"] for s in scenes) if scenes else next(v["seconds"] for v in videos if v["id"] == made["motion"]["source"])
            steps.append({"name": made["name"], "workflow_title": "Motion graphics", "kind": "video", "prompt": made["words"],
                          "facts": made["facts"], "time": "under a minute", "why": agent.why(proposed),
                          "credits": await offload(state.credits.cost, MOTION_WORKFLOW if scenes else credits.OVERLAY, seconds),
                          "settings": None, "start": None, "motion": made["motion"]})
            return None
        return "it had no words to show, or no selected video to put them on"
    pieces = agent.parts_asked(instruction, proposed) if proposed.get("tool") == "trim" else 0
    if pieces:
        if any("edit" in step for step in steps):
            return   # the split is already planned; a second trim of the same video adds nothing
        proposed = dict(proposed, tool="split", parts=pieces)   # the user asked for pieces, not for one cut
    if proposed.get("tool") in agent.EDIT_TOOLS:
        # An edit of videos the user has: the browser runs it through the timeline export, which costs nothing.
        cuts = agent.edits_for(proposed, videos)
        for edit in cuts:
            steps.append({"name": edit["name"], "workflow_title": "Edit", "kind": "video", "prompt": "", "facts": edit["facts"],
                          "time": "a few seconds", "credits": 0, "settings": None, "start": None, "edit": {"clips": edit["clips"]}})
        return None if cuts else "select the video to cut on the canvas first"
    schema = schemas.get(proposed.get("workflow"))
    original = proposed   # kept on the step, so the shot can be made again as a still and then as a clip
    if schema and proposed.get("tool", "generate") == "generate":   # the camera the agent chose is said in the prompt
        proposed = dict(proposed, prompt=camera.apply(proposed.get("prompt"), camera.clean(proposed), schema["id"].split("/", 1)[0]))
    if not schema:
        return "there is no workflow “{}” it can use".format(proposed.get("workflow") or "")
    if not agent.offer(schema):
        return "{} needs reference files, and none were attached".format(schema["title"])
    uses = agent.uses_for(schema, proposed, kinds, assets)
    left_out = [i for i in proposed.get("leave_out") or [] if isinstance(i, int)] if isinstance(proposed.get("leave_out"), list) else []
    # A model that takes no reference pictures keeps the always-on people and places the same from words: what they show.
    special = set((schema.get("slots") or {}).values())
    if pinned and proposed.get("prompt") and schema["id"].split("/", 1)[0] in ("image", "video") \
            and not any(r["kind"] in ("image", "video") for r in schema["refs"] if r["id"] not in special):
        words = kit.in_words(pinned, left_out)
        if words:
            proposed = dict(proposed, prompt=proposed["prompt"].rstrip() + "\n" + words)
    # A prompt longer than its model reads well, or than a job takes, goes back to the model to be shortened: never cut unseen.
    too_long = agent.too_long(schema, original.get("prompt"), proposed.get("prompt")) if proposed.get("tool", "generate") == "generate" else None
    if too_long:
        return too_long
    # A step can start on what an earlier step of this plan makes, if that is a picture or a video
    # and this workflow has a first frame to put it in.
    first_frame = (schema.get("slots") or {}).get("first_frame")
    place = _place(proposed)
    last = len(steps) - 1
    while last > 0 and (steps[last].get("variation") or {}).get("n", 1) > 1:
        last -= 1
    before = steps[last] if steps else None
    follows = last if place and before and before.get("settings") and before["kind"] == "video" and before.get("place") == place else None
    # The shot just before was in the same place: this one goes on from its last frame, unless it is told what to start on.
    if follows is not None and schema["id"].startswith("video/") and first_frame and not proposed.get("after") \
            and not proposed.get("start_from") and not any(use["slot"] == first_frame for use in uses):
        proposed = dict(proposed, after=next((n for n, at in made_by.items() if at == follows), 0))
    earlier = made_by.get(proposed.get("after"))
    chained = earlier is not None and earlier < len(steps) and bool(first_frame) and steps[earlier]["kind"] != "audio"
    # A song's length is not left to the model, which likes to ask for the longest one (and it is paid by the second):
    # the length the user named, or else the video shots planned before it, rounded up to a length the workflow offers.
    if (agent.length_control(schema) and not any(c["role"] == "duration" for c in schema["controls"])) \
            or schema.get("capability") == "music":
        wanted = agent.seconds_asked(instruction) or sum(
            (s["settings"] or {}).get("values", {}).get(next((c["id"] for c in schemas[s["settings"]["workflow"]]["controls"] if c["role"] == "duration"), ""), 0)
            * (s["settings"] or {}).get("clips", 1) for s in steps if s.get("settings") and s["kind"] == "video")
        proposed = dict(proposed, duration=math.ceil(wanted)) if wanted else proposed
    # A resolution asked for that an admin switched off is not offered: the step is made at the next one, and says so.
    asked_at, stepped_from = proposed.get("resolution"), ""
    if isinstance(asked_at, int) and not isinstance(asked_at, bool) and schema["resolutions"] and asked_at not in schema["resolutions"]:
        try:
            used_at, stepped_from = await offload(state.credits.fit_resolution, schema["id"], asked_at, sorted(set(schema["resolutions"]) | {asked_at}))
        except ValueError:
            used_at = None
        if stepped_from and used_at in schema["resolutions"]:
            proposed = dict(proposed, resolution=used_at)
    built = agent.settings_for(schema, proposed, set(names), project or None,
                               {use["slot"] for use in uses}, {use["id"] for use in uses if use["id"]}, chained)
    if not built:
        return "it had no prompt, or {} needs files it was not given".format(schema["title"])
    settings, start = built
    keep = memory.clean_keep(proposed.get("keep"), schema["id"].split("/", 1)[0])
    if keep:   # kept in shared memory once it is made
        settings["keep"] = keep
    if slot:   # its result is kept at this path of the state once it is made (core.keep_take)
        settings["save_to_state"] = slot
    if isinstance(proposed.get("check"), str) and proposed["check"].strip():   # what its review checks closely
        settings["check"] = " ".join(proposed["check"].split())[:400]
    voice = (schema.get("slots") or {}).get("voice_track")
    if proposed.get("clean_voice") is True and voice and any(use["slot"] == voice for use in uses):
        settings["clean_voice"] = True   # its voice track has music or noise under it: the voice is taken out first (jobs.py)
    planned_fields(settings, proposed, uses)
    # A shot takes the shape of the picture it starts on: a portrait picture in a landscape video comes out squashed.
    agent.shape_like(schema, settings, steps[earlier].get("shape") if chained else shapes.get(start))
    try:
        stepped = await offload(fit_resolution, state, schema, settings) or stepped_from   # a resolution switched off: the next one allowed
    except HTTPException as error:
        return str(error.detail)
    # The project's always-on entries go into every slot meant for them that the step left empty, but those it leaves out.
    uses = uses + [dict(fill, cast=True) for fill in kit.fills(
        schema, pinned, {use["slot"] for use in uses}, {use["asset"] for use in uses if use.get("asset")}, left_out,
        {use["id"] for use in uses if use["id"]} | ({start} if start else set()))]
    steps.append(await _shown_step(state, schema, settings, menu or [], uses,
                                   {"id": start, "name": names[start], "slot": first_frame} if start else None,
                                   {"step": earlier, "slot": first_frame} if chained else None, agent.why(proposed)))
    steps[-1]["camera"] = camera.clean(proposed)
    steps[-1]["proposal"] = original
    steps[-1]["place"] = place
    if said_as:   # shown on the card: the words the video model is given to say, respelled
        steps[-1]["phonetic"] = said_as
    if stepped:
        steps[-1]["resolution_note"] = stepped
        steps[-1]["why"] = " ".join(filter(None, [steps[-1].get("why"), stepped]))
    for key in ("shot_number", "board"):
        if key in settings:
            steps[-1][key] = settings[key]
    if follows is not None and not chained:   # not started on it, but still checked against it
        steps[-1]["follows"] = follows
    return None


PLANNED_KEYS = ("shot_number", "shot_numbers", "board", "placement_group", "review_refs", "variation", "clean_voice")   # settings a card keeps when changed
PINNABLE = ("video", "image", "audio", "upscaler")   # the kinds of workflow a chat can be pinned to (body "workflows")


def boards_text(state, user_id, project):
    """The canvas's boards as the agent is told them: one line each, its name and what is on it."""
    try:
        owner, where = placement.canvas_of(state.db, user_id, project)
        found = placement.boards(state.db, owner, where)
    except Exception as error:   # the boards are a help: the message goes without them
        print("The canvas boards could not be read: {}".format(error))
        return ""
    lines = []
    for board in found:
        shots = sorted({s["shot_number"] for s in board["stacks"] if s.get("shot_number")})
        lines.append("- {}: {} {}{}".format(board["name"], len(board["stacks"]), "card" if len(board["stacks"]) == 1 else "cards",
                                           " (shots {})".format(", ".join(map(str, shots))) if shots else ""))
    return "\n".join(lines)
SECOND_OPINION_FRAMES = 6   # frames of a result shown to the second opinion


def planned_fields(settings, proposed, uses):
    """The fields of a planned step that go with its job: its shot number in the story and the canvas board its result
    goes on (for the canvas: settings "shot_number", an int, and "board", a string), and the references its review
    compares it with ("review_refs", for the check made once it is done, aftercare.py)."""
    numbers = [n for n in (placement.clean_shot_number(v) for v in proposed.get("shot_numbers") or []) if n] \
        if isinstance(proposed.get("shot_numbers"), list) else []
    number = placement.clean_shot_number(proposed.get("shot_number")) or (numbers[0] if len(set(numbers)) == 1 else None)
    if number:
        settings["shot_number"] = number
    if numbers:   # a sound or music that belongs to these shots (8.2)
        settings["shot_numbers"] = sorted(set(numbers))[:50]
    board = placement.clean_board(proposed.get("board"))
    if board:
        settings["board"] = board
    refs = [{"asset": u["asset"]} if u.get("asset") else {"id": u["id"]} for u in uses if (u.get("asset") or u.get("id")) and u["kind"] in ("image", "video")]
    if refs:
        settings["review_refs"] = refs[:review.MAX_REFERENCES * 2]


def vary(steps, proposed):
    """A step asked for in several variations ("variations" 2 to agent.MAX_VARIATIONS): the step just added is made that
    many times, each a step of its own with a new seed (seed_mode random), the same shot number and board, each priced.
    Never past agent.MAX_STEPS steps in the plan."""
    wanted = proposed.get("variations") if isinstance(proposed.get("variations"), int) and not isinstance(proposed.get("variations"), bool) else 1
    wanted = max(1, min(agent.MAX_VARIATIONS, wanted, agent.MAX_STEPS - len(steps) + 1))
    if wanted < 2:
        return
    first = steps[-1]
    first["variation"] = first["settings"]["variation"] = {"n": 1, "of": wanted}
    for n in range(2, wanted + 1):
        twin = json.loads(json.dumps(first))
        twin["settings"].update(seed_mode="random", variation={"n": n, "of": wanted})
        twin["settings"].pop("keep", None)   # one take is kept for reuse, not every variation
        twin["keep"] = None
        twin.update(variation={"n": n, "of": wanted}, name="{} · v{}".format(first["name"], n)[:80])
        twin["settings"]["name"] = twin["name"]
        steps.append(twin)


def _named_here(state, user, project, reply, items):
    """The items the model may name, with those the reply names that it was not given but that are of this project (or,
    out of any project, the user's own): a film a long run made is shown when asked for, not taken out."""
    asked = [i for i in agent.named_ids(reply) if i not in items]
    if not asked:
        return items
    marks = ", ".join("?" * len(asked))
    if project:
        with as_everyone():   # a shared project: what its members made too
            rows = state.db.all("SELECT id, kind, name FROM generations WHERE project_id = ? AND id IN (" + marks + ")", (project, *asked))
    else:
        rows = state.db.all("SELECT id, kind, name FROM generations WHERE user_id = ? AND project_id IS NULL AND id IN (" + marks + ")",
                            (user["id"], *asked))
    return {**items, **{r["id"]: {"name": r["name"], "kind": r["kind"]} for r in rows}}


def _linked(state, chips):
    """Each item and entry of the reply with its studio link (/api/m/<public id>, library.media_link): one to copy."""
    for table, key in (("generations", "item"), ("assets", "asset")):
        ids = [int(k.split(":")[1]) for k in chips if k.startswith(key + ":")]
        for row_id, public in core.public_ids(state.db, table, ids).items():
            if public:
                chips["{}:{}".format(key, row_id)]["link"] = "/api/m/" + public


def _place(step):
    """Where a shot happens, as compared between shots: its "place" in lower case, spaces made single."""
    return " ".join(str(step.get("place") or "").lower().split())[:80]


def _orientation(schema, settings, ctx):
    """landscape, portrait or square: what a job's shape is called on its approval card, or None when it has none."""
    if schema.get("size"):
        return ctx["orientation"]
    shape = agent.shape_of(schema, settings, ctx)
    if not shape:
        return None
    ratio = shape[0] / shape[1]
    return "landscape" if ratio > 1.15 else "portrait" if ratio < 0.87 else "square"


async def _shown_step(state, schema, settings, menu, uses, start, after, why=""):
    """One planned generation as the browser shows it: checked and priced, with what its approval card can change."""
    quote = await price(state, await state.catalog.load(schema["id"]), settings)
    ctx = workflows.context(schema, settings)
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    kind = schema["id"].split("/", 1)[0]
    aspect = any(c["input"] == "aspect_ratio" and c.get("choices") for c in schema["controls"])         or any(o["id"] == "aspect_ratio" for o in schema["options"])   # a provider's model: its Shape option
    resolutions = schema["resolutions"] if schema.get("size") or "resolution" in roles or schema.get("resolution_option") else []
    span = schema.get("seconds") or {}
    durations = [d for d in SHOT_LENGTHS + list(range(16, 31, 5)) if span.get("min", 4) <= d <= span.get("max", 15)]
    return {"name": settings["name"], "workflow_title": schema["title"], "kind": kind,
            "prompt": settings["values"][roles["prompt"]["id"]] if "prompt" in roles else "", "facts": workflows.summary(schema, ctx), "time": quote["text"],
            "credits": quote["credits"], "settings": settings, "start": start, "uses": uses, "after": after,
            "shape": agent.shape_of(schema, settings, ctx), "why": why, "keep": settings.get("keep"),
            # What the card offers: the other workflows of the same kind, and this one's shapes, sizes and lengths.
            "menu": {"workflows": [w for w in menu if w["kind"] == kind],
                     "shapes": bool(schema.get("size") or aspect or agent.orientation_option(schema)), "resolutions": resolutions,
                     "durations": durations if "duration" in roles else []},
            "current": {"orientation": _orientation(schema, settings, ctx), "resolution": _resolution_of(ctx.get("resolution")) or None,
                        "duration": int(ctx["duration"]) if ctx.get("duration") else None}}


def _resolution_of(value):
    """A resolution as a number (720), from 720, "720" or a provider's "720p"; 0 when it says none."""
    found = re.match(r"^\s*(\d{3,4})", str(value or ""))
    return int(found.group(1)) if found else 0


SHEET_TYPES = (".csv", ".tsv")


async def _bring_in_sheets(state, user, project, given, selection):
    """Bring every asset sheet among the attached items (given: their ids) into the module's NeuralCore (sheet.py), and
    say so on its line of `selection` (added there when the message's words did not point at it). Returns the lines
    shown to the user. A sheet already brought in adds nothing and fetches nothing again (its rows are there by name)."""
    from .. import sheet
    ids = [i for i in given if isinstance(i, int) and not isinstance(i, bool)][:MAX_SELECTION]
    rows = [r for r in [await offload(kit.item_in_module, state.db, user["id"], project, i, "text") for i in ids]
            if r and r["filename"].lower().endswith(SHEET_TYPES)]
    shown = []
    for row in rows:
        path = await offload(state.outputs.folder, row["user_id"]) / row["filename"]
        line = next((s for s in selection if s["id"] == row["id"]), None)
        if line is None:
            line = {"tag": "@{}".format(len(selection) + 1), "id": row["id"], "kind": "text", "name": row["name"]}
            selection.append(line)
        if not project:
            line["sheet"] = "an asset sheet, not brought in: NeuralCore belongs to a project and this message is in none. Say so."
            continue
        try:
            entries, left = sheet.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except (OSError, sheet.SheetError):
            continue   # a table that is not an asset sheet (a shot list, say): an attached text like any other
        keeper = await offload(kit.keeper_of, state.db, user["id"], project)
        with core.as_everyone() if keeper != user["id"] else contextlib.nullcontext():
            done = await sheet.bring_in(state.db, state.assets_dir / str(keeper), keeper, project, entries)
        line["sheet"] = sheet.told(done, left, row["name"])
        line.pop("begins", None)   # what it is, said whole above
        new = sum(1 for a in done["added"] if a["new"])
        if new or done["failed"]:
            shown.append("Brought {} entr{} from {} into NeuralCore{}{}".format(
                new, "y" if new == 1 else "ies", row["name"], ", {} looks linked".format(len(done["looks"])) if done["looks"] else "",
                ", {} failed".format(len(done["failed"])) if done["failed"] else ""))
    return shown


def attachment_line(item):
    """One attached item as the check of a skill is told it: its tag, its name and what it is, by its content."""
    what = {"audio": "a sound", "video": "a video", "image": "a picture", "text": "a text"}.get(item["kind"], item["kind"])
    if item.get("sheet"):
        return "{} {} (an asset sheet: its characters, locations and props are in NeuralCore now)".format(item["tag"], item["name"])
    if item.get("seconds"):
        what += ", {:.1f} s long".format(item["seconds"])
    if item["kind"] == "text" and "characters" in item:
        what += " of {:,} characters, which begins: “{}”".format(item["characters"], item.get("begins", ""))
    return "{} {} ({})".format(item["tag"], item["name"], what)


# The kinds of file a missing thing may be, by its words: what the check of a skill calls missing is given when the user
# attached a file of that kind.
KIND_WORDS = {
    "audio": re.compile(r"\b(audio|sound|voice|mix|track|music|song|narration|recording|mp3|wav|stem)\b", re.I),
    "text": re.compile(r"\b(script|text|document|screenplay|story|transcript|srt|lyrics|article|words|doc|docx)\b", re.I),
    "image": re.compile(r"\b(image|images|picture|pictures|photo|photos|still|stills|sheet|sheets|character|characters|location|locations|prop|props)\b", re.I),
    "video": re.compile(r"\b(video|clip|clips|footage)\b", re.I),
}


def attached_kind(missing, selection):
    """The kind of attached file that answers a thing the check called missing, or None."""
    have = {s["kind"] for s in selection}
    return next((kind for kind, words in KIND_WORDS.items() if kind in have and words.search(str(missing))), None)
