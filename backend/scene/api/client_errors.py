"""What goes wrong in the browser (R2, T5): the studio's pages and the phone site send their uncaught errors, unhandled
promise rejections and, for a tenth of page views, their Web Vitals (LCP, INP, CLS) to POST /api/client-errors. Only a
signed-in user's are taken, at most 30 a minute each, and only the newest 5,000 rows are kept. The admin console's
System section reads them (GET /api/admin/client-errors): the newest errors, and the vitals of the last seven days."""

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db import as_everyone
from .deps import admin_user, current_user, limited

router = APIRouter(prefix="/api", tags=["client-errors"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

APPS = ("studio", "phone")
KINDS = ("error", "rejection", "vital")
VITALS = {"LCP": (2500, 4000), "INP": (200, 500), "CLS": (0.1, 0.25)}   # good up to, poor from (web.dev's thresholds)
KEEP = 5000
SHOWN = 50
WEEK = 7 * 86400


def _text(value, most):
    return str(value or "")[:most]


@router.post("/client-errors", status_code=204, dependencies=[limited("client-errors", 30, 60)])
async def report(body: dict, request: Request, user: dict = Depends(current_user)):
    """{"app": "studio" or "phone", "kind": "error", "rejection" or "vital", "message" (a vital's name: LCP, INP or
    CLS), "stack"?, "page", "build", "value"? (a vital's number)}. Nothing is answered."""
    app, kind = body.get("app"), body.get("kind")
    if app not in APPS or kind not in KINDS:
        raise HTTPException(400, "Say which app it was and what kind of report.")
    value = body.get("value")
    if kind == "vital":
        if body.get("message") not in VITALS or not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value < 1e7:
            raise HTTPException(400, "A vital is LCP, INP or CLS with its number.")
    else:
        value = None
    db = request.app.state.db
    made = await db.arun(
        "INSERT INTO client_errors (user_id, app, kind, message, stack, page, build, value, user_agent, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user["id"], app, kind, _text(body.get("message"), 500), _text(body.get("stack"), 4000), _text(body.get("page"), 300),
         _text(body.get("build"), 60), value, _text(request.headers.get("user-agent"), 300), time.time()))
    if made and int(made) % 100 == 0:   # now and then, the oldest beyond the newest KEEP go
        with as_everyone():
            await db.arun("DELETE FROM client_errors WHERE id <= ?", (int(made) - KEEP,))


def _p75(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.75 * len(ordered)))] if ordered else None


@admin_router.get("/client-errors")
async def latest(request: Request, user: dict = Depends(admin_user)):
    """{"errors": the newest SHOWN errors and rejections, with who and where, "vitals": per name, the last seven days'
    count, 75th percentile and share rated good}."""
    db = request.app.state.db
    with as_everyone():
        errors = await db.aall(
            "SELECT c.id, c.app, c.kind, c.message, c.stack, c.page, c.build, c.user_agent, c.created, u.email "
            "FROM client_errors c LEFT JOIN users u ON u.id = c.user_id WHERE c.kind <> 'vital' "
            "ORDER BY c.created DESC, c.id DESC LIMIT ?", (SHOWN,))
        vitals = await db.aall("SELECT message, value FROM client_errors WHERE kind = 'vital' AND created >= ?",
                               (time.time() - WEEK,))
    summary = []
    for name, (good, _poor) in VITALS.items():
        values = [r["value"] for r in vitals if r["message"] == name and r["value"] is not None]
        summary.append({"name": name, "count": len(values), "p75": _p75(values),
                        "good": round(sum(v <= good for v in values) / len(values), 3) if values else None})
    return {"errors": [dict(e) for e in errors], "vitals": summary}
