"""Share links: one library item that anyone with the link can watch, without signing in, for a while.

The owner makes a link (POST /api/library/{id}/share) and sends it on; /s/<token> is a small page with the player and
/s/<token>/file the file. Only the token's hash is kept, so a copy of the database opens nothing. A link stops working
when it runs out (share_days), when the owner turns sharing off for the item, or when the item is deleted."""

import html
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .. import audit
from ..db import as_everyone
from ..security import token_hash
from .deps import current_user, limited
from .library import _own, _path

router = APIRouter(tags=["shares"])


def _days(request):
    days = request.app.state.settings.share_days
    if days <= 0:
        raise HTTPException(403, "Share links are turned off on this studio.")
    return days


@router.post("/api/library/{item_id}/share", dependencies=[limited("share", 60, 3600)])
async def make_link(item_id: int, request: Request, user: dict = Depends(current_user)):
    """A new link to the item: {"path": "/s/<token>", "expires"}. The address in front of the path is the studio's,
    as whoever opens it reaches it (the public one, for someone else)."""
    row = _own(request, user, item_id, "creator")
    days = _days(request)
    token = secrets.token_urlsafe(18)
    expires = time.time() + days * 86400
    request.app.state.db.run("INSERT INTO shares (token_hash, user_id, item_id, created, expires) VALUES (?, ?, ?, ?, ?)",
                             (token_hash(token), user["id"], row["id"], time.time(), expires))
    audit.record(request, user, "Shared a link", row["name"], "{} days".format(days))
    return {"path": "/s/" + token, "expires": expires}


@router.delete("/api/library/{item_id}/share")
async def stop_links(item_id: int, request: Request, user: dict = Depends(current_user)):
    """Stop every link of yours to the item."""
    _own(request, user, item_id, "viewer")
    request.app.state.db.run("DELETE FROM shares WHERE item_id = ? AND user_id = ?", (item_id, user["id"]))
    return {"ok": True}


def _shared(request, token):
    """The item a link opens, or a 404 that says nothing about why."""
    db = request.app.state.db
    with as_everyone():
        link = db.one("SELECT * FROM shares WHERE token_hash = ? AND expires > ?", (token_hash(token), time.time()))
        row = link and db.one("SELECT * FROM generations WHERE id = ?", (link["item_id"],))
    if not link or not row or request.app.state.settings.share_days <= 0:
        raise HTTPException(404, "This link doesn't open anything. It may have run out.")
    return link, row


@router.get("/s/{token}", response_class=HTMLResponse, dependencies=[limited("shared", 120, 60, by="address")])
async def shared_page(token: str, request: Request):
    link, row = _shared(request, token)
    with as_everyone():
        request.app.state.db.run("UPDATE shares SET views = views + 1 WHERE token_hash = ?", (link["token_hash"],))
    name = html.escape(row["name"])
    src = "/s/{}/file".format(html.escape(token))
    media = {"video": '<video src="{}" controls autoplay playsinline loop></video>',
             "audio": '<audio src="{}" controls autoplay></audio>',
             "image": '<img src="{}" alt="">'}.get(row["kind"], '<a class="file" href="{}">Open the file</a>').format(src)
    return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{name} · Scene.ai</title>
<style>
html,body{{margin:0;height:100%;background:#000;color:#fff;font:15px -apple-system,system-ui,Segoe UI,Roboto,sans-serif}}
main{{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:24px;box-sizing:border-box}}
video,img{{max-width:100%;max-height:78vh;border-radius:14px;background:#111}}
audio{{width:min(520px,100%)}}
h1{{font-size:20px;font-weight:600;margin:0;text-align:center}}
p{{margin:0;color:rgba(235,235,245,.6);font-size:13px}}
a{{color:#8b7bff}}
</style></head><body><main>{media}<h1>{name}</h1><p>Made with Scene.ai</p></main></body></html>""".format(name=name, media=media),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/s/{token}/file", dependencies=[limited("shared-file", 600, 60, by="address")])
async def shared_file(token: str, request: Request, download: bool = False):
    _, row = _shared(request, token)
    path = _path(request, row)
    if not path.is_file():
        raise HTTPException(404, "The file is missing from storage.")
    return FileResponse(path, filename=path.name if download else None, headers={"Cache-Control": "private, max-age=3600"})
