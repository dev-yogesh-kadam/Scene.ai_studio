"""What the phone app (mobile/) reads that the studio's pages don't need: lighter lists, a page at a time, and running
a failed job again. Every route here only reads or makes what the studio's own routes would; none of them changes how
those behave."""

import contextlib
import json
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import audit, placement
from ..catalog import KINDS
from ..comfy import workflows
from ..db import as_everyone
from .deps import current_user, limited
from ..outputs import MAIN_CANVAS
from .library import _own, _own_project

router = APIRouter(prefix="/api", tags=["mobile"])

PAGE = 30
MOST = 60
# What the phone shows of a job: the queue's own snapshot (jobs.py), without the settings it was made with.
JOB_FIELDS = ("id", "name", "workflow", "kind", "status", "created", "started", "finished", "est_seconds", "eta_seconds",
              "step", "steps", "node", "clip", "clips", "position", "waiting_for_server", "reason", "cost", "project_id")


@router.get("/mobile/jobs")
async def mobile_jobs(request: Request, user: dict = Depends(current_user)):
    """The user's jobs as the queue has them, each with the prompt it was made from and, once done, the library items
    it made (for the player). "paused": an admin paused the renders."""
    state = request.app.state
    jobs = state.jobs.snapshot(user["id"])
    done = [j["id"] for j in jobs if j["status"] == "done"]
    made = {}
    if done:
        rows = state.db.all("SELECT id, job_id, kind FROM generations WHERE user_id = ? AND job_id IN ({}) ORDER BY id"
                            .format(",".join("?" * len(done))), [user["id"], *done])
        for row in rows:
            made.setdefault(row["job_id"], []).append({"id": row["id"], "kind": row["kind"]})
    shown = []
    for job in jobs:
        settings = job.get("settings") or {}
        slim = {k: job.get(k) for k in JOB_FIELDS}
        slim.update(prompt=str(settings.get("prompt") or "")[:500], workflow_title=settings.get("workflow_title") or "",
                    items=made.get(job["id"], []))
        shown.append(slim)
    return {"jobs": shown, "paused": state.jobs.paused()}


def _slim_item(item, user_id):
    settings = json.loads(item["settings"] or "{}")
    context = json.loads(item["context"] or "{}")
    shown = {k: item[k] for k in ("id", "name", "kind", "workflow", "seconds", "size", "created", "rating", "project_id",
                                  "project_name", "public_id", "job_id", "cost")}
    shown.update(prompt=str(settings.get("prompt") or "")[:1000], workflow_title=settings.get("workflow_title") or "",
                 width=context.get("width"), height=context.get("height"), orientation=context.get("orientation"),
                 ext=PurePath(item["filename"]).suffix.lower(), mine=item["user_id"] == user_id)
    if not shown["mine"]:
        shown["made_by"] = item["made_by"]
    return shown


@router.get("/mobile/library")
async def mobile_library(request: Request, kind: str = "", q: str = "", project: str = "", starred: int = 0, exact: int = 0,
                         offset: int = 0, limit: int = PAGE, user: dict = Depends(current_user)):
    """The library a page at a time, newest first: {"items", "next_offset"} (null after the last page). The same items
    as GET /api/library, without the settings and context each carries there. `starred=1`: only the ones rated up.
    `project`: a project with its modules, or with `exact=1` only that project's own canvas (or that one module)."""
    offset, limit = max(0, offset), max(1, min(limit, MOST))
    shared = project.isdigit() and int(project) > 0 and bool(_own_project(request, user, int(project), "viewer"))
    sql = ("SELECT g.*, j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
           "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id WHERE g.run = '' AND "
           + (("g.project_id = ?" if exact else "g.project_id IN (SELECT id FROM projects WHERE id = ? OR parent_id = ?)")
              if shared else "g.user_id = ?"))
    params = ([int(project)] if exact else [int(project)] * 2) if shared else [user["id"]]
    if kind in (*KINDS, "text"):
        sql, params = sql + " AND g.kind = ?", params + [kind]
    if starred:
        sql += " AND g.rating > 0"
    for word in q.split()[:6]:
        like = "%{}%".format(word.replace("%", r"\%").replace("_", r"\_"))
        sql += " AND (g.name LIKE ? ESCAPE '\\' OR g.summary LIKE ? ESCAPE '\\' OR g.settings LIKE ? ESCAPE '\\')"
        params += [like] * 3
    with as_everyone() if shared else contextlib.nullcontext():
        rows = request.app.state.db.all(sql + " ORDER BY g.created DESC, g.id DESC LIMIT ? OFFSET ?", params + [limit + 1, offset])
    more = len(rows) > limit
    return {"items": [_slim_item(r, user["id"]) for r in rows[:limit]], "next_offset": offset + limit if more else None}


@router.get("/mobile/library/{item_id}")
async def mobile_item(item_id: int, request: Request, user: dict = Depends(current_user)):
    """One item as the list shows it, for the player opened from a push or a finished job."""
    row = _own(request, user, item_id, "viewer")
    db = request.app.state.db
    with as_everyone():   # an item of a project shared with the user is not one of their rows
        extra = db.one("SELECT j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
                       "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id WHERE g.id = ?", (item_id,))
    return _slim_item(dict(row, **extra), user["id"])


MODULE_ITEMS = 2000


@router.get("/mobile/modules/{project_id}")
async def mobile_module(project_id: int, request: Request, user: dict = Depends(current_user)):
    """A module (or a project's own canvas) laid out for a phone instead of the infinite canvas: its story shots in
    order, each with its takes newest first; its boards (Characters, Locations, Outputs...) with their stacks; and how
    many items it holds. Every item as the library list shows it."""
    db = request.app.state.db
    here = _own_project(request, user, project_id, "viewer")
    with as_everyone():   # what everyone in the project made, now that the user is found to be in it
        rows = db.all("SELECT g.*, j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
                      "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id "
                      "WHERE g.project_id = ? AND g.run = '' ORDER BY g.created DESC, g.id DESC LIMIT ?", (project_id, MODULE_ITEMS))
        top = db.one("SELECT id, ref, name, canvas_name FROM projects WHERE id = ?", (here["top_id"],))
    shown = {row["id"]: _slim_item(row, user["id"]) for row in rows}

    # The story: every result made for a numbered shot, retakes stacked on their shot, the newest take first.
    shots = {}
    for row in rows:
        number = placement.clean_shot_number(json.loads(row["settings"] or "{}").get("shot_number"))
        if number:
            shots.setdefault(number, []).append(shown[row["id"]])
    story = [{"number": n, "takes": shots[n]} for n in sorted(shots)]

    boards = []
    for board in placement.boards(db, here["owner_id"], project_id, set(shown)):
        stacks = [{"group": s["group"], "shot_number": s.get("shot_number"), "items": [shown[i] for i in s["items"]]} for s in board["stacks"]]
        if stacks:
            boards.append({"name": board["name"], "stacks": stacks})
    boards.sort(key=lambda b: (b["name"] != placement.FINAL_VIDEO, b["name"] != placement.OUTPUTS, b["name"].lower()))   # the finished film first

    main = project_id == top["id"]
    return {"module": {"id": project_id, "ref": here.get("ref"), "name": (top["canvas_name"] or MAIN_CANVAS) if main else here["name"],
                       "main": main, "role": here["role"], "project": {"id": top["id"], "ref": top["ref"], "name": top["name"]}},
            "shots": story, "boards": boards, "items": len(rows), "updated": rows[0]["created"] if rows else None}


@router.get("/mobile/workflows")
async def mobile_workflows(request: Request, user: dict = Depends(current_user)):
    """The workflows the phone can start, each with the few settings it offers: the prompt, the length, the settings
    marked primary, the quality choices, and its reference slots ("refs": the pictures, videos or sounds it is given;
    "optional" false for the ones it needs). "prompt_optional": it can be made without words."""
    state = request.app.state
    found = []
    for listed in await state.catalog.listing():
        if listed.get("error") or listed["kind"] not in KINDS or not state.credits.enabled(listed["id"], user):
            continue
        try:
            schema = workflows.describe(await state.catalog.load(listed["id"]))
        except (workflows.WorkflowError, HTTPException, KeyError, ValueError):
            continue
        prompt = next((c for c in schema["controls"] if c["role"] == "prompt"), None)
        if prompt is None and not schema["refs"]:
            continue
        controls = [{k: c.get(k) for k in ("id", "type", "role", "label", "default", "choices")}
                    for c in schema["controls"] if c["role"] in ("prompt", "duration") or (c.get("primary") and not c["role"])]
        allowed = state.credits.allowed_resolutions(schema["id"], schema["resolutions"]) if schema["size"] else []
        found.append({"id": schema["id"], "kind": listed["kind"], "title": schema["title"], "description": schema["description"],
                      "hints": schema["hints"][:4], "controls": controls, "options": schema["options"],
                      "size": schema["size"], "resolutions": allowed, "prompt_optional": bool(schema.get("prompt_optional")),
                      "refs": [{"id": r["id"], "kind": r["kind"], "label": r["label"], "optional": bool(r["optional"])} for r in schema["refs"]]})
    return {"workflows": found}


@router.post("/mobile/credit-request", dependencies=[limited("credit-request", 5, 3600)])
async def credit_request(body: dict, request: Request, user: dict = Depends(current_user)):
    """Body: {"amount", "note"?}. Ask the admins for credits: it goes into the audit log (the admin console's
    Activity). Nothing is given until an admin does it."""
    amount = body.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= 1_000_000:
        raise HTTPException(400, "Ask for between 1 and 1,000,000 credits.")
    note = " ".join(str(body.get("note") or "").split())[:300]
    audit.record(request, user, "Asked for credits", user["email"], "{} cr{}".format(amount, " · " + note if note else ""))
    return {"ok": True}


@router.get("/mobile/waiting")
async def waiting_plans(request: Request, user: dict = Depends(current_user)):
    """The agent's plans that wait for the user's approval, newest first, in any module: [{"project_id", "module",
    "project", "tab", "tab_name", "instruction", "reply", "steps", "total", "at"}]. A plan waits from when the agent
    proposes it until it is approved or turned down, in the studio or on the phone."""
    db = request.app.state.db
    rows = db.all("SELECT project_id, kind, data, updated FROM boards WHERE user_id = ? AND kind LIKE 'agent-%' "
                  "AND data LIKE ? ORDER BY updated DESC LIMIT 30", (user["id"], '%"state": "proposed"%'))
    found = []
    for row in rows:
        try:
            runs_ = json.loads(row["data"]).get("runs") or []
        except ValueError:
            continue
        last = next((r for r in reversed(runs_) if isinstance(r, dict) and r.get("state") == "proposed"), None)
        if not last or not row["project_id"]:
            continue
        with as_everyone():
            place = db.one("SELECT p.id, p.name, p.canvas_name, p.parent_id, pp.name AS parent_name FROM projects p "
                           "LEFT JOIN projects pp ON pp.id = p.parent_id WHERE p.id = ?", (row["project_id"],))
        index = db.one("SELECT data FROM boards WHERE user_id = ? AND project_id = ? AND kind = 'agent'", (user["id"], row["project_id"]))
        tabs = (json.loads(index["data"]).get("tabs") or []) if index else []
        tab = row["kind"][len("agent-"):]
        if not place:
            continue
        found.append({"project_id": row["project_id"], "module": place["name"] if place["parent_id"] else (place["canvas_name"] or MAIN_CANVAS),
                      "project": place["parent_name"] or place["name"], "tab": tab,
                      "tab_name": next((t.get("name") for t in tabs if isinstance(t, dict) and t.get("id") == tab), "Agent"),
                      "instruction": str(last.get("instruction") or "")[:300], "reply": str(last.get("reply") or "")[:300],
                      "steps": len(last.get("steps") or []), "total": last.get("total") or 0, "at": last.get("at")})
    return {"plans": found}


@router.get("/mobile/credits")
async def mobile_credits(request: Request, user: dict = Depends(current_user)):
    """The user's balance and their latest 30 credit changes, newest first."""
    db = request.app.state.db
    events = db.all("SELECT c.amount, c.reason, c.note, c.created, j.name AS job_name FROM credit_events c "
                    "LEFT JOIN jobs j ON j.id = c.job_id WHERE c.user_id = ? ORDER BY c.created DESC, c.id DESC LIMIT 30",
                    (user["id"],))
    return {"balance": request.app.state.credits.balance(user["id"]), "events": events}


@router.post("/jobs/{job_id}/retry", dependencies=[limited("jobs", 30, 60)])
async def retry_job(job_id: str, request: Request, user: dict = Depends(current_user)):
    """Run one of the user's failed or cancelled jobs again with the same settings. Its first run was given back, so
    this is charged like a new job: {"id", "credits"}."""
    state = request.app.state
    job = state.db.one("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"]))
    if job is None:
        raise HTTPException(404, "No such job.")
    if job["status"] not in ("failed", "cancelled"):
        raise HTTPException(400, "Only a failed or cancelled job can be run again.")
    cost = job["cost"] or 0
    over = state.credits.cap_problem(user["id"], cost)
    if over:
        raise HTTPException(429, over)
    if cost and not state.credits.charge(user["id"], cost, "generation", note="Run again"):
        raise HTTPException(402, "This needs {} credits and you have {}. Ask an admin for more.".format(
            cost, state.credits.balance(user["id"])))
    new_id = state.jobs.add(user["id"], job["name"], job["workflow"], json.loads(job["settings"]), job["summary"],
                            job["est_seconds"], cost, job["project_id"], job["seconds_requested"])
    return {"id": new_id, "credits": cost}
