"""The library: each user's finished images and videos, organised in projects."""

import contextlib
import csv
import io
import json
import re
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .. import audit, fetch, kit, media, placement, refs, semantic, sharing, showcase, storage
from ..db import as_everyone, offload
from ..catalog import KINDS
from ..outputs import MAIN_CANVAS

FIRST_MODULE = "Module 1"
from ..references import media_kind, read_text_upload, read_upload, safe_name, text_kind, upload_reference
from .deps import costly, current_user, limited, uploading

router = APIRouter(prefix="/api", tags=["library"])


def _path(request, row):
    """The item's file here (downloaded into its folder first when the media are kept elsewhere: storage.py)."""
    outputs = request.app.state.outputs
    return outputs.fetch(outputs.folder(row["user_id"]) / row["filename"])


def _own(request, user, item_id, need=None):
    """An item of the user's, or, with `need`, one made in a project shared with them where their role allows that."""
    db = request.app.state.db
    row = db.one("SELECT * FROM generations WHERE id = ? AND user_id = ?", (item_id, user["id"]))
    if row is None and need:
        with as_everyone():
            other = db.one("SELECT * FROM generations WHERE id = ?", (item_id,))
        if other and other["project_id"] and sharing.role_in(db, user["id"], other["project_id"])[0]:
            sharing.require(db, user, other["project_id"], need)
            row = other
    if row is None:
        raise HTTPException(404, "No such item.")
    return row


def _own_project(request, user, project_id, need="owner"):
    """A project or module the user may act on: theirs, or one shared with them where their role allows `need`."""
    return sharing.require(request.app.state.db, user, project_id, need)


# ---------------------------------------------------------------- items

LIBRARY_PAGE_MOST = 200   # the most items one page of the library holds (`limit`)


def _cursor(text):
    """A page's place in the list, as the page before gave it: "<created>:<id>" of its last item; None for the start."""
    created, _, item_id = text.partition(":")
    try:
        return float(created), int(item_id)
    except ValueError:
        raise HTTPException(400, "That page of the library can't be found; start from the first page.")


def search_words(q):
    """The words of a library search, at most six: letters and digits of any script, lowercase."""
    return [w.lower() for w in re.findall(r"\w+", q or "")][:6]


def search_sql(q, alias="g"):
    """SQL and its values for the items a search finds: every word is in the item's name, summary, workflow or
    settings (its prompt), as the start of a word there (full-text search, generations.search, migration 0009), or,
    a word of four letters or more, near a word of the name, a letter or two wrong (trigrams). ("", []) when there is
    nothing to search."""
    sql, values = "", []
    for word in search_words(q):
        if len(word) >= SEARCH_TYPOS_FROM:
            sql += " AND ({a}.search @@ to_tsquery('simple', ?) OR ? <% {a}.name)".format(a=alias)
            values += [word + ":*", word]
        else:   # a short word, or a number: as typed ("3" is not "4")
            sql += " AND {a}.search @@ to_tsquery('simple', ?)".format(a=alias)
            values.append(word + ":*")
    return sql, values


SEARCH_TYPOS_FROM = 4   # letters a word of a search has before a near spelling of it counts (search_sql)


def _shown(item, user):
    """An item as the library lists it: its settings and context as JSON, whether it is the user's, who made it if not."""
    item["settings"] = json.loads(item["settings"])
    item["context"] = json.loads(item["context"])
    item["mine"] = item.pop("user_id") == user["id"]
    if item["mine"]:
        del item["made_by"]
    return item


def _listing(rows, user, **more):
    """The library's answer as JSON: {"items": [...], **more}. Its rows hold only plain values (str, int, float, None),
    and the settings and context read from JSON, so they are written out as they are: FastAPI's jsonable_encoder walked
    every value of every item first, two thirds of the time of a canvas of 20,000 items."""
    return json.dumps({"items": [_shown(item, user) for item in rows], **more}, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


async def _listed(rows, user, **more):
    """_listing, made off the event loop (a canvas's whole list is megabytes), as the response."""
    return Response(await offload(_listing, rows, user, **more), media_type="application/json")


@router.get("/library")
async def list_items(request: Request, kind: str = "", q: str = "", project: str = "", run: str = "", modules: int = 0,
                     all: int = 0, limit: int = 0, cursor: str = "", job: str = "", meaning: int = 0,
                     user: dict = Depends(current_user)):
    """`project` is a project id, "none" for items in no project, or empty for everything; with `modules=1` a project's
    modules count as part of it. `run`: the working files of that run (slices, trims, references of a long skill), which
    are otherwise left out. `all=1`: every item, not the newest 500. The canvas asks for it: it drops
    from its saved layout whatever the list leaves out, so a cut-off list would lose the places of older work.
    `limit`: a page of at most that many items (up to 200) instead, with "next_cursor" for the next page (null after the
    last); `cursor`: where that page starts. `job`: only what that job made. `meaning=1` with `q`: the items closest in
    meaning to the words, closest first (semantic.py), when search by meaning is on; otherwise as without it."""
    # Each item comes with what its details panel shows: the job's cost and the project's name.
    # In a project: what everyone in it made (a shared project's members too), read once the user is found to be in it.
    # Anywhere else: the user's own items.
    shared = project.isdigit() and int(project) > 0 and bool(await offload(_own_project, request, user, int(project), "viewer"))
    sql = ("SELECT g.*, j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
           "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id WHERE " + ("1 = 1" if shared else "g.user_id = ?"))
    sql += " AND g.run = ?"
    params = ([] if shared else [user["id"]]) + [run[:64]]
    if kind in (*KINDS, "text"):
        sql, params = sql + " AND g.kind = ?", params + [kind]
    if job:
        sql, params = sql + " AND g.job_id = ?", params + [job[:64]]
    if project == "none":
        sql += " AND g.project_id IS NULL"
    elif project.isdigit() and modules:
        sql, params = sql + " AND g.project_id IN (SELECT id FROM projects WHERE id = ? OR parent_id = ?)", params + [int(project)] * 2
    elif project.isdigit():
        sql, params = sql + " AND g.project_id = ?", params + [int(project)]
    embedder = request.app.state.embedder
    if meaning and q.strip() and embedder is not None:   # by meaning: the items in view, closest first (semantic.py)
        try:
            with as_everyone() if shared else contextlib.nullcontext():
                ids = [r["id"] for r in await request.app.state.db.aall(sql.replace("SELECT g.*, j.cost", "SELECT g.id, j.cost", 1), params)]
                near = await offload(semantic.nearest, request.app.state.db, embedder, q, "g.id = ANY(?)", [ids],
                                     min(limit, LIBRARY_PAGE_MOST) if limit > 0 else 60)
                rows = {r["id"]: r for r in await request.app.state.db.aall(sql + " AND g.id = ANY(?)", params + [near])}
            items = [rows[i] for i in near if i in rows]
            return await (_listed(items, user, next_cursor=None) if limit > 0 else _listed(items, user))
        except semantic.SemanticError:
            pass   # the embedding API can't be reached: the words are searched instead, below
    found, values = search_sql(q)   # every word in its name, summary, workflow or prompt; or a name typed a little wrong
    sql, params = sql + found, params + values
    if limit > 0:   # a page: newest first, the same created time ordered by id, so no item is skipped or shown twice
        limit = min(limit, LIBRARY_PAGE_MOST)
        if cursor:
            created, item_id = _cursor(cursor)
            sql, params = sql + " AND (g.created < ? OR (g.created = ? AND g.id < ?))", params + [created, created, item_id]
        with as_everyone() if shared else contextlib.nullcontext():
            rows = await request.app.state.db.aall(sql + " ORDER BY g.created DESC, g.id DESC LIMIT ?", params + [limit + 1])
        page = rows[:limit]
        after = "{!r}:{}".format(page[-1]["created"], page[-1]["id"]) if len(rows) > limit else None
        return await _listed(page, user, next_cursor=after)
    with as_everyone() if shared else contextlib.nullcontext():
        items = await request.app.state.db.aall(sql + " ORDER BY g.created DESC" + ("" if all else " LIMIT 500"), params)
    return await _listed(items, user)


@router.get("/library/placement")
async def canvas_placement(request: Request, project: int = 0, user: dict = Depends(current_user)):
    """The named boards of a canvas and the stacks on them, as finished jobs placed their results (placement.py). Items
    deleted since are left out. `project` 0: the canvas of the user's work in no project."""
    db = request.app.state.db
    owner = (await offload(_own_project, request, user, project, "viewer"))["owner_id"] if project else user["id"]
    with as_everyone():
        known = {r["id"] for r in await db.aall("SELECT id FROM generations WHERE " + ("project_id = ?" if project else "user_id = ? AND project_id IS NULL"),
                                         (project or user["id"],))}
    return {"boards": await offload(placement.boards, db, owner, project, known), "names": list(placement.BOARDS)}


UPLOADED = "upload/file"   # what an item the user brought in is filed under: it was not made with a workflow


@router.post("/library/upload", dependencies=[limited("upload", 60, 600), uploading])
async def upload_item(request: Request, user: dict = Depends(current_user)):
    """Multipart form with "file" (an image, a video, a sound, a script: .docx, .pdf, .txt, or a transcript: .srt,
    .json) and "project_id".
    The file joins the library and the project's canvas like a finished generation, so it can be a frame to start on, a
    reference or part of a cut. Nothing is charged."""
    form = await request.form(max_files=1, max_fields=10)
    upload = form.get("file")
    if not hasattr(upload, "filename"):
        raise HTTPException(400, "Choose a file.")
    filename = upload.filename
    if text_kind(upload.filename):   # a script or a transcript: kept as its words (a Word file as plain text)
        (data, filename), kind = await read_text_upload(upload), "text"
    else:
        data = await read_upload(upload)   # refuses what is too large or is not the image, video or sound it says it is
        filename, kind = upload.filename, media_kind(upload.filename)   # a HEIC or AVIF photo is a JPEG or PNG now
    project = str(form.get("project_id") or "")
    project_id = (await offload(_own_project, request, user, int(project), "creator"))["id"] if project.isdigit() and int(project) else None
    return await _file_in(request, user, data, filename, kind, project_id, "Uploaded")


IMPORTED = "upload/link"   # an item brought in from a link on another site


@router.post("/library/import", dependencies=[costly("import"), uploading])
async def import_link(body: dict, request: Request, user: dict = Depends(current_user)):
    """{"url", "project_id"?, "name"?}: the picture, clip or sound at a link on another site, brought into the library
    (see fetch.py for what is fetched and what is refused). Nothing is charged."""
    url = str(body.get("url") or "").strip()
    if not url or len(url) > 2000:
        raise HTTPException(400, "Give the link to bring in.")
    project_id = (await offload(_own_project, request, user, body["project_id"], "creator"))["id"] if isinstance(body.get("project_id"), int) and body["project_id"] else None
    try:
        data, kind, final = await fetch.fetch(url)
    except fetch.FetchError as error:
        raise HTTPException(400, str(error))
    name = " ".join(str(body.get("name") or "").split())[:80]
    return await _file_in(request, user, data, fetch.filename_for(final, kind, data), kind, project_id, "Brought in from a link",
                          workflow=IMPORTED, name=name, source=url)


async def _file_in(request, user, data, filename, kind, project_id, summary, workflow=UPLOADED, name="", source=""):
    """A file the user brought in, saved and filed in the library like a finished generation."""
    folder = await offload(request.app.state.outputs.folder, user["id"])
    folder.mkdir(parents=True, exist_ok=True)
    name = name or (filename.rsplit(".", 1)[0].strip() or kind)[:80]
    target = folder / "{}_{}_{}".format("upload", time.strftime("%Y%m%d_%H%M%S"), safe_name(filename))
    target.write_bytes(data)
    # A "video" that is only a sound (cover art, or one frame held still: audio exported "as a video") is kept as the
    # sound it is, its codec copied, and filed as audio.
    if kind == "video" and await media.sound_only(target):
        sound = await media.keep_sound(target, target.stem)
        target.unlink(missing_ok=True)
        target, kind, data = sound, "audio", sound.read_bytes()
    context = {}
    if kind in ("video", "image"):
        found = await media.probe(target)
        context = {k: v for k, v in (("width", found["width"]), ("height", found["height"])) if v}
        if kind == "video" and found["seconds"]:
            context["duration"] = round(found["seconds"], 2)
    elif kind == "audio":
        found = await media.probe(target)
        if found["seconds"]:
            context["duration"] = round(found["seconds"], 2)
    db = request.app.state.db
    filed = await offload(request.app.state.outputs.settle, user["id"], project_id, target)   # into its project's folder
    outputs = request.app.state.outputs
    await offload(lambda: outputs.keep(outputs.folder(user["id"]) / filed))   # and kept for good (storage.py)
    await db.arun("INSERT INTO generations (user_id, job_id, project_id, workflow, kind, name, filename, summary, settings, "
           "context, seconds, size, created) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
           (user["id"], project_id, workflow, kind, name, filed, summary,
            json.dumps({"name": name, "prompt": "", **({"source": source} if source else {})}), json.dumps(context), len(data), time.time()))
    row = await db.aone("SELECT * FROM generations WHERE user_id = ? AND filename = ?", (user["id"], filed))
    return dict(row, settings=json.loads(row["settings"]), context=json.loads(row["context"]))


@router.get("/library/{item_id}")
async def get_item(item_id: int, request: Request, user: dict = Depends(current_user)):
    """One item as the library list gives it (settings, context, cost, project), for a page that needs only that one."""
    await offload(_own, request, user, item_id, "viewer")
    with as_everyone():   # an item of a project shared with the user is not one of their rows; _own asked
        item = await request.app.state.db.aone(
            "SELECT g.*, j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
            "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id WHERE g.id = ?", (item_id,))
    return _shown(dict(item), user)


@router.get("/library/{item_id}/file")
async def get_file(item_id: int, request: Request, download: bool = False, user: dict = Depends(current_user)):
    row = await offload(_own, request, user, item_id, "viewer")
    outputs = request.app.state.outputs
    path = outputs.folder(row["user_id"]) / row["filename"]
    elsewhere = storage.signed(request.app.state, "outputs", path, path.name if download else None)
    if elsewhere:   # kept in Blob Storage: the browser fetches it from there (storage.py)
        return elsewhere
    if not path.is_file():
        raise HTTPException(404, "The file is missing from storage.")
    return FileResponse(path, filename=path.name if download else None)


PUBLIC_ID = re.compile(r"[0-9a-f]{12}")


@router.get("/m/{ref}")
async def media_link(ref: str, request: Request, download: bool = False, user: dict = Depends(current_user)):
    """The studio's own link to a result or a NeuralCore entry, by its 12-character id (/api/m/3f9a1c2b7e44): it stays
    the same however the file is moved or renamed. Only someone signed in who may see the item opens it: the file is
    served by the item's or the entry's own route, which asks."""
    ref = ref.split(".", 1)[0].lower()
    if not PUBLIC_ID.fullmatch(ref):
        raise HTTPException(404, "No such item.")
    db = request.app.state.db
    with as_everyone():
        item = await db.aone("SELECT id FROM generations WHERE public_id = ?", (ref,))
        entry = None if item else await db.aone("SELECT id FROM assets WHERE public_id = ?", (ref,))
    if item:
        return await get_file(item["id"], request, download, user)
    if entry:
        from .kit import entry_file
        return await entry_file(entry["id"], request, user)
    raise HTTPException(404, "No such item.")


NOT_READY = {"Retry-After": "1", "Cache-Control": "no-store"}


async def _made_poster(path):
    """The poster, made once (media.poster: a second request waits for the first). One that can't be read is a 404; one
    that can't be put in place yet (Windows: its older copy still being sent) is a 503 the browser asks again for."""
    try:
        return await media.poster(path)
    except media.MediaError as error:
        raise HTTPException(404, str(error))
    except OSError:
        raise HTTPException(503, "The thumbnail is being made. Ask again in a moment.", headers=NOT_READY)


async def poster_response(request, path):
    """A video's poster. The browser keeps it and only asks whether it has changed, which costs no download."""
    state = request.app.state
    if state.storage.name != "local":   # kept in Blob Storage: made once and kept there, then signed
        poster = media.poster_path(path)
        if not await offload(storage.kept, state, poster):
            path = await offload(storage.here, path)
            if not path.is_file():
                raise HTTPException(404, "The file is missing from storage.")
            poster = await _made_poster(path)
            await offload(storage.keep_path, state, poster)
        return storage.signed(state, None, poster)
    if not path.is_file():
        raise HTTPException(404, "The file is missing from storage.")
    poster = await _made_poster(path)
    webp = media.webp_of(poster)   # the smaller copy, to a browser that takes WebP, once it was made (new results)
    if "image/webp" in request.headers.get("accept", "") and webp.is_file() and webp.stat().st_mtime >= poster.stat().st_mtime:
        poster = webp
    headers = {"Cache-Control": "private, no-cache", "Vary": "Accept"}
    response = FileResponse(poster, stat_result=poster.stat(), headers=headers)
    if request.headers.get("if-none-match") == response.headers["etag"]:
        return Response(status_code=304, headers={"ETag": response.headers["etag"], **headers})
    return response


@router.get("/library/{item_id}/poster")
async def get_poster(item_id: int, request: Request, user: dict = Depends(current_user)):
    row = await offload(_own, request, user, item_id, "viewer")
    outputs = request.app.state.outputs
    return await poster_response(request, await offload(lambda: outputs.folder(row["user_id"]) / row["filename"]))


@router.get("/library/{item_id}/frame")
async def get_frame(item_id: int, request: Request, at: float = 0.0, user: dict = Depends(current_user)):
    """The frame of a video at `at` seconds, for the keyframes the agent shows under a result. Made once and kept,
    per tenth of a second, next to the video's poster."""
    row = await offload(_own, request, user, item_id, "viewer")
    if row["kind"] != "video":
        raise HTTPException(400, "Only a video has frames.")
    path = await offload(_path, request, row)
    if not path.is_file():
        raise HTTPException(404, "The file is missing from storage.")
    tenth = max(0, min(int(round(at * 10)), 36000))
    target = media.poster_path(path).with_name("{}.{}.jpg".format(path.name, tenth))
    if not media.fresh(target, path):
        async with media.making(target):   # made once: the keyframes under a result are asked for together
            if not media.fresh(target, path):
                target.parent.mkdir(exist_ok=True)
                try:
                    made = await media.frame_at(path, tenth / 10, target)
                except OSError:
                    raise HTTPException(503, "The frame is being made. Ask again in a moment.", headers=NOT_READY)
                if not made:
                    raise HTTPException(404, "The video has no frame there.")
                await offload(request.app.state.outputs.keep, target)
    elsewhere = storage.signed(request.app.state, "posters", target)
    if elsewhere:
        return elsewhere
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.put("/library/{item_id}")
async def update_item(item_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    """Rename an item, move it to a project (project_id null = no project) or rate it (rating 1, -1, or 0 to clear)."""
    await offload(_own, request, user, item_id)
    db = request.app.state.db
    if "name" in body and str(body["name"]).strip():
        await db.arun("UPDATE generations SET name = ? WHERE id = ?", (str(body["name"]).strip()[:80], item_id))
    if "rating" in body:
        if body["rating"] not in (1, -1, 0) or isinstance(body["rating"], bool):
            raise HTTPException(400, "A rating is 1, -1 or 0.")
        await db.arun("UPDATE generations SET rating = ? WHERE id = ?", (body["rating"], item_id))
        if body["rating"]:   # Langfuse: the user's thumb, as a score on the turn that made it (turned over, it is replaced)
            await offload(request.app.state.traces.langfuse.item_score, item_id, "user-thumb", 1 if body["rating"] > 0 else 0, "rating-{}".format(item_id))
    if "project_id" in body:
        if body["project_id"] is not None:
            await offload(_own_project, request, user, body["project_id"], "creator")
        await db.arun("UPDATE generations SET project_id = ? WHERE id = ?", (body["project_id"], item_id))
        await offload(request.app.state.outputs.refile, user["id"], item_id, body["project_id"])   # its file follows it to that project's folder
    return {"ok": True}


@router.delete("/library/{item_id}")
async def delete_item(item_id: int, request: Request, user: dict = Depends(current_user)):
    row = await offload(_own, request, user, item_id)
    await offload(media.remove_result, await offload(_path, request, row))
    await request.app.state.db.arun("DELETE FROM generations WHERE id = ?", (item_id,))
    return {"ok": True}


@router.post("/library/{item_id}/reference")
async def as_reference(item_id: int, request: Request, kind: str = "image", user: dict = Depends(current_user)):
    """Make a library item usable as a reference in a new job. kind is what the slot takes: an image slot gets an
    image as it is or a video's last frame; a video slot a video; an audio slot a sound, or a video for its sound."""
    row = await offload(_own, request, user, item_id, "creator")   # a picture someone else made in the project, used to make the next
    path = await offload(_path, request, row)
    if not path.is_file():
        raise HTTPException(404, "The file is missing from storage.")
    comfy = request.app.state.comfy
    if kind == "image" and row["kind"] == "video":
        with tempfile.TemporaryDirectory() as tmp:
            frame = await media.last_frame(path, Path(tmp) / (path.stem + "_last.png"))
            name = await upload_reference(comfy, frame.name, frame.read_bytes(), "image/png", db=request.app.state.db, user_id=user["id"])
        return {"comfy_name": name, "name": "End of " + row["name"]}
    if row["kind"] == kind or (kind == "audio" and row["kind"] == "video"):
        name = await upload_reference(comfy, path.name, path.read_bytes(), db=request.app.state.db, user_id=user["id"])
        return {"comfy_name": name, "name": row["name"]}
    raise HTTPException(400, "{} is {}, and this needs {}.".format(
        row["name"], {"image": "an image", "video": "a video", "audio": "a sound"}.get(row["kind"], "a text"),
        {"image": "an image or a video", "video": "a video", "audio": "a sound"}.get(kind, "something else")))


# ---------------------------------------------------------------- projects

# A project and its modules: "p.id = ? OR p.parent_id = ?" in the counts below, so a project counts what its modules hold.
_IN_PROJECT = "g.project_id IN (SELECT q.id FROM projects q WHERE q.id = p.id OR q.parent_id = p.id)"


@router.get("/projects")
async def list_projects(request: Request, user: dict = Depends(current_user)):
    """Every project and module of the user, and those shared with them. A module has "parent_id" and "parent_name"; a
    project has "modules", the number of its modules, and counts (items, cover, updated) over itself and its modules
    together. "role" is the user's in it ("owner" in their own), and a shared one says whose it is ("owner_name")."""
    db = request.app.state.db
    shared = await offload(sharing.shared_ids, db, user["id"])
    where = "p.user_id = ?" + (" OR p.id IN ({})".format(", ".join("?" * len(shared))) if shared else "")
    with as_everyone() if shared else contextlib.nullcontext():
        rows = await db.aall(
        "SELECT p.id, p.ref, p.name, p.canvas_name, p.created, p.parent_id, p.user_id, pp.name AS parent_name, pp.ref AS parent_ref, ow.name AS owner_name, "
        "(SELECT COUNT(*) FROM project_members pm WHERE pm.project_id = COALESCE(p.parent_id, p.id)) AS members, "
        "(SELECT COUNT(*) FROM projects m WHERE m.parent_id = p.id) AS modules, "
        "(SELECT COUNT(*) FROM generations g WHERE " + _IN_PROJECT + " AND g.run = '') AS items, "
        # The newest item of a project is its cover on the Home page, and tells when it was last worked on.
        "(SELECT g.id FROM generations g WHERE " + _IN_PROJECT + " AND g.run = '' ORDER BY g.created DESC LIMIT 1) AS cover_id, "
        "(SELECT g.kind FROM generations g WHERE " + _IN_PROJECT + " AND g.run = '' ORDER BY g.created DESC LIMIT 1) AS cover_kind, "
        "(SELECT MAX(g.created) FROM generations g WHERE " + _IN_PROJECT + ") AS updated "
        "FROM projects p LEFT JOIN projects pp ON pp.id = p.parent_id JOIN users ow ON ow.id = p.user_id "
        "WHERE " + where + " ORDER BY lower(p.name)", (user["id"], *shared))
    for row in rows:
        mine = row.pop("user_id") == user["id"]
        row["role"] = "owner" if mine else (await offload(sharing.role_in, db, user["id"], row["id"]))[0]
        if mine:
            row.pop("owner_name")
    return {"projects": rows}


@router.get("/refs/{ref}")
async def find_ref(ref: str, request: Request, user: dict = Depends(current_user)):
    """The project or module a link's id (PRJ..., MOD...) names, if the user may see it: {"id", "ref", "parent_id",
    "parent_ref"}. 404 for an id that names nothing, or something the user is not in."""
    db = request.app.state.db
    with as_everyone():
        row = await db.aone("SELECT p.id, p.ref, p.parent_id, pp.ref AS parent_ref FROM projects p LEFT JOIN projects pp ON pp.id = p.parent_id "
                     "WHERE p.ref = ?", (ref,)) if refs.looks_like(ref, refs.PROJECT, refs.MODULE) else None
    if not row:
        raise HTTPException(404, "No such project.")
    await offload(_own_project, request, user, row["id"], "viewer")
    return row


@router.get("/projects/{project_id}")
async def get_project(project_id: int, request: Request, user: dict = Depends(current_user)):
    """A project's page: the project, its own canvas as the first module ("main"), then its modules, each with its items,
    cover and last change. For a module, the project it is in."""
    db = request.app.state.db
    here = await offload(_own_project, request, user, project_id, "viewer")
    top = await offload(_own_project, request, user, here["top_id"], "viewer")

    def counted(row, main=False):
        stats = db.one("SELECT COUNT(*) AS items, MAX(created) AS updated FROM generations WHERE project_id = ? AND run = ''", (row["id"],))
        cover = db.one("SELECT id, kind FROM generations WHERE project_id = ? AND run = '' ORDER BY created DESC LIMIT 1", (row["id"],))
        name = (row["canvas_name"] or MAIN_CANVAS) if main else row["name"]   # the project's own canvas goes by its own name
        return {"id": row["id"], "ref": row["ref"], "name": name, "created": row["created"], "main": main, "items": stats["items"],
                "updated": stats["updated"], "cover_id": cover and cover["id"], "cover_kind": cover and cover["kind"]}
    with as_everyone():   # what everyone in the project made, now that the user is found to be in it
        modules = [await offload(counted, top, True)] + [await offload(counted, m) for m in await db.aall("SELECT * FROM projects WHERE parent_id = ? ORDER BY created", (top["id"],))]
    return {"project": {"id": top["id"], "ref": top["ref"], "name": top["name"], "created": top["created"], "role": top["role"], "members": await offload(sharing.members, db, top["id"]),
                        "items": sum(m["items"] for m in modules), "updated": max((m["updated"] or 0 for m in modules), default=0) or None,
                        **next(({"cover_id": m["cover_id"], "cover_kind": m["cover_kind"]} for m in sorted(modules, key=lambda m: -(m["updated"] or 0))
                                if m["cover_id"]), {"cover_id": None, "cover_kind": None})},
            "modules": modules}


# ---------------------------------------------------------------- a project's analytics

# What a project's credits went on, by the kind of thing made. A sound is music or a voice by its workflow.
ASSET_TYPES = (("video", "Videos"), ("voiceover", "Voiceover"), ("music", "Music"), ("image", "Images"),
               ("motion", "Motion graphics"), ("edit", "Edits"), ("llm", "Agent"))
PERIODS = ("today", "7", "30", "month")


def _asset_type(workflow, kind):
    if str(workflow).startswith("audio/"):
        return "music" if "music" in str(workflow).lower() else "voiceover"
    return {"video": "video", "upscaler": "video", "image": "image", "motion": "motion"}.get(kind, "edit")


def _period(period, now=None):
    """(start, end) of a period, by this machine's clock: today, the last 7 or 30 days, or this month."""
    now = now or time.time()
    day = time.localtime(now)
    midnight = time.mktime((day.tm_year, day.tm_mon, day.tm_mday, 0, 0, 0, 0, 0, -1))
    if period == "today":
        return midnight, now
    if period == "month":
        return time.mktime((day.tm_year, day.tm_mon, 1, 0, 0, 0, 0, 0, -1)), now
    return midnight - (int(period) - 1) * 86400, now


def project_analytics_data(db, user, project_id, period):
    sharing.require(db, user, project_id, "viewer")
    with as_everyone():   # the spend and the work of everyone in the project
        return _project_analytics(db, user, project_id, period)


def _project_analytics(db, user, project_id, period):
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    root = row["parent_id"] or project_id
    project = db.one("SELECT * FROM projects WHERE id = ?", (root,))
    modules = [dict(project, main=True)] + [dict(m, main=False) for m in db.all(
        "SELECT * FROM projects WHERE parent_id = ? ORDER BY id", (root,))]
    ids = [m["id"] for m in modules]
    marks = ", ".join("?" * len(ids))
    period = period if period in PERIODS else "7"
    start, end = _period(period)
    before = start - (end - start)
    # What a job spent is its price less what was given back: the charge itself is written before the job has an id.
    jobs = db.all("SELECT j.id, j.project_id, j.workflow, j.kind, j.status, j.created, j.user_id, j.cost - j.credits_refunded AS spent "
                  "FROM jobs j WHERE j.user_id = ? AND j.project_id IN ({}) AND j.created >= ? AND j.created < ?".format(marks),
                  (user["id"], *ids, before, end))
    talks = db.all("SELECT project_id, created, -amount AS spent FROM credit_events WHERE user_id = ? AND reason = 'agent' AND project_id IN ({}) "
                   "AND created >= ? AND created < ?".format(marks), (user["id"], *ids, before, end))
    made = db.all("SELECT project_id, kind, workflow, created FROM generations WHERE user_id = ? AND project_id IN ({}) AND run = '' "
                  "AND created >= ? AND created < ?".format(marks), (user["id"], *ids, start, end))
    first = {r["project_id"]: r["first"] for r in db.all(
        "SELECT project_id, MIN(created) AS first FROM generations WHERE user_id = ? AND project_id IN ({}) GROUP BY project_id".format(marks),
        (user["id"], *ids))}
    spends = [(j["project_id"], _asset_type(j["workflow"], j["kind"]), j["created"], j["spent"] or 0) for j in jobs] + \
             [(t["project_id"], "llm", t["created"], t["spent"] or 0) for t in talks]
    now_spend = [x for x in spends if x[2] >= start]
    spent, spent_before = sum(x[3] for x in now_spend), sum(x[3] for x in spends if x[2] < start)

    days, at = [], start
    while at < end and len(days) < 40:
        days.append(time.strftime("%Y-%m-%d", time.localtime(at)))
        at += 86400
    daily = {day: {t: 0 for t, _ in ASSET_TYPES} for day in days}
    for _, kind, when, credits in now_spend:
        day = time.strftime("%Y-%m-%d", time.localtime(when))
        if day in daily:
            daily[day][kind] += credits
    by_type = {t: {"credits": 0, "generations": 0} for t, _ in ASSET_TYPES}
    for _, kind, _, credits in now_spend:
        by_type[kind]["credits"] += credits
    for g in made:
        by_type[_asset_type(g["workflow"], g["kind"])]["generations"] += 1

    rows = []
    for number, m in enumerate(modules, start=1):
        mine = [x for x in now_spend if x[0] == m["id"]]
        items = [g for g in made if g["project_id"] == m["id"]]
        kinds = {x[1] for x in mine} | {_asset_type(g["workflow"], g["kind"]) for g in items}
        types = {t: {"credits": sum(x[3] for x in mine if x[1] == t), "generations": sum(1 for g in items if _asset_type(g["workflow"], g["kind"]) == t)}
                 for t, _ in ASSET_TYPES}
        rows.append({"id": m["id"], "number": number, "name": (m["canvas_name"] or MAIN_CANVAS) if m["main"] else m["name"], "main": m["main"],
                     "first": first.get(m["id"]), "generations": len(items), "asset_types": len(kinds),
                     "credits": sum(x[3] for x in mine), "types": {t: v for t, v in types.items() if v["credits"] or v["generations"]}})
    rows.sort(key=lambda r: (-r["credits"], -r["generations"], r["number"]))
    return {
        "project": {"id": root, "ref": project["ref"], "name": project["name"]}, "period": period, "start": start, "end": end, "owner": user["email"],
        "spend": spent, "spend_before": spent_before,
        "change": None if not spent_before else round(100 * (spent - spent_before) / spent_before),
        "generations": len(made), "active_modules": sum(1 for r in rows if r["generations"] or r["credits"]),
        "contributors": len({j["user_id"] for j in jobs if j["created"] >= start}),
        "types": [{"id": t, "label": label, **by_type[t]} for t, label in ASSET_TYPES],
        "days": days, "daily": [daily[d] for d in days], "modules": rows,
    }


@router.get("/projects/{project_id}/analytics")
async def project_analytics(project_id: int, request: Request, period: str = "7", user: dict = Depends(current_user)):
    """What a project (its modules too) spent and made in a period (today, 7, 30 or month): by day and kind of thing
    made, and by module. Credits are what the jobs cost less their refunds, and the agent's messages in the project."""
    return await offload(project_analytics_data, request.app.state.db, user, project_id, period)


@router.get("/projects/{project_id}/analytics.csv")
async def project_analytics_csv(project_id: int, request: Request, period: str = "7", user: dict = Depends(current_user)):
    found = await offload(project_analytics_data, request.app.state.db, user, project_id, period)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["module", "first generation", "generations", "asset types", "credits"] + [label + " credits" for _, label in ASSET_TYPES])
    for r in found["modules"]:
        writer.writerow([r["name"], time.strftime("%Y-%m-%d", time.localtime(r["first"])) if r["first"] else "", r["generations"],
                         r["asset_types"], r["credits"]] + [r["types"].get(t, {}).get("credits", 0) for t, _ in ASSET_TYPES])
    name = "".join(c if c.isalnum() else "-" for c in found["project"]["name"]).strip("-") or "project"
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="{}-{}.csv"'.format(name, found["period"])})


@router.post("/projects/{project_id}/duplicate")
async def duplicate_project(project_id: int, request: Request, user: dict = Depends(current_user)):
    """A copy of a project to start again from: its modules (empty canvases of the same names) and its NeuralCore,
    named "<name> copy". What was made stays with the first project."""
    db = request.app.state.db
    row = await offload(_own_project, request, user, project_id)
    root = await db.aone("SELECT * FROM projects WHERE id = ?", (row["parent_id"] or project_id,))
    ref = refs.of_project(None)
    copy = await db.arun("INSERT INTO projects (user_id, name, created, canvas_name, ref) VALUES (?, ?, ?, ?, ?)",
                  (user["id"], (root["name"] + " copy")[:60], time.time(), root["canvas_name"], ref))
    for m in await db.aall("SELECT id, name FROM projects WHERE parent_id = ? ORDER BY id", (root["id"],)):
        module = await db.arun("INSERT INTO projects (user_id, name, created, parent_id, ref) VALUES (?, ?, ?, ?, ?)",
                        (user["id"], m["name"], time.time(), copy, refs.of_project(copy)))
        await offload(kit.copy_entries, db, user["id"], m["id"], module)   # each module's NeuralCore is its own
    await offload(kit.copy_entries, db, user["id"], root["id"], copy)
    return {"id": copy, "ref": ref, "name": (root["name"] + " copy")[:60]}


@router.post("/projects")
async def create_project(body: dict, request: Request, user: dict = Depends(current_user)):
    """{"name", "parent_id"?}: a project, or with parent_id a module inside that project (a module holds no modules)."""
    name = str(body.get("name", "")).strip()[:60]
    if not name:
        raise HTTPException(400, "Give the project a name.")
    parent = None
    if body.get("parent_id"):
        parent = await offload(_own_project, request, user, body["parent_id"], "creator") if isinstance(body["parent_id"], int) else None
        if parent is None or parent["parent_id"]:
            raise HTTPException(400, "A module goes inside a project, not inside another module.")
    # A new project's own canvas is its first module, "Module 1"; the modules added to it go on from "Module 2".
    # A module of a shared project is the project owner's, like the project: everyone in it works there.
    ref = refs.of_project(parent and parent["id"])
    with as_everyone():
        project_id = await request.app.state.db.arun("INSERT INTO projects (user_id, name, created, parent_id, canvas_name, ref) VALUES (?, ?, ?, ?, ?, ?)",
                                              (parent["owner_id"] if parent else user["id"], name, time.time(), parent and parent["id"],
                                               "" if parent else FIRST_MODULE, ref))
    return {"id": project_id, "ref": ref, "name": name, "parent_id": parent and parent["id"],
            "parent_ref": parent and parent.get("ref")}


@router.put("/projects/{project_id}")
async def rename_project(project_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    await offload(_own_project, request, user, project_id, "manager")
    name = str(body.get("name", "")).strip()[:60]
    if not name:
        raise HTTPException(400, "Give the project a name.")
    outputs = request.app.state.outputs
    before = await offload(outputs.folder_of, project_id)
    await request.app.state.db.arun("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))
    await offload(outputs.rename, user["id"], before, await offload(outputs.folder_of, project_id))   # its folder (with its modules') takes the new name
    return {"ok": True}


@router.put("/projects/{project_id}/canvas")
async def rename_canvas(project_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    """Rename a project's own canvas (shown as "Main canvas" until it is named). Its folder of results takes the name."""
    here = await offload(_own_project, request, user, project_id, "manager")
    if here["parent_id"]:
        raise HTTPException(400, "A module is renamed as a module.")
    name = str(body.get("name", "")).strip()[:60]
    if not name:
        raise HTTPException(400, "Give the canvas a name.")
    outputs = request.app.state.outputs
    before = await offload(outputs.relative, project_id)
    await request.app.state.db.arun("UPDATE projects SET canvas_name = ? WHERE id = ?", ("" if name == MAIN_CANVAS else name, project_id))
    await offload(outputs.rename, user["id"], before, await offload(outputs.relative, project_id))
    return {"ok": True, "name": name}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, request: Request, user: dict = Depends(current_user)):
    """Delete a project, or a module, and everything in it, so nothing that can no longer be used stays in storage: what
    was made in it (the files, their posters and keyframes), its jobs still waiting or running (their credits given
    back), and its canvases and agent tabs. A project takes its modules and its NeuralCore with it. The jobs'
    records stay, in no project, for the credit history."""
    probe = await offload(_own_project, request, user, project_id, "viewer")
    here = await offload(_own_project, request, user, project_id, "manager" if probe["parent_id"] else "owner")   # a module: a manager; a project: its owner
    state, db = request.app.state, request.app.state.db
    people = await offload(sharing.people_of, db, project_id)   # whose work is in it: the owner's and every member's
    owner = here["owner_id"]
    with as_everyone():
        gone = [project_id] if here["parent_id"] else [m["id"] for m in await db.aall("SELECT id FROM projects WHERE parent_id = ?", (project_id,))] + [project_id]
        its_folder = await offload(state.outputs.folder_of, project_id)   # a project's folder holds its modules' folders: all of it
        marks = ", ".join("?" * len(gone))
        for job in await db.aall("SELECT id, user_id FROM jobs WHERE status IN ('queued', 'running') AND project_id IN ({})".format(marks), gone):
            await offload(state.jobs.remove, job["user_id"], job["id"])   # a running one stops at its next check; its result is not kept (jobs._record)
        removed = await db.aall("SELECT id, user_id, filename FROM generations WHERE project_id IN ({})".format(marks), gone)
        for row in removed:
            await offload(media.remove_result, await offload(state.outputs.folder, row["user_id"]) / row["filename"])
        await db.arun("DELETE FROM generations WHERE project_id IN ({})".format(marks), gone)
        for one in gone:
            await db.arun("UPDATE jobs SET project_id = NULL WHERE project_id = ?", (one,))
            # Its canvas and agent tabs go with it: a project made later must not open with them.
            await db.arun("DELETE FROM boards WHERE project_id = ?", (one,))
            for row in await db.aall("SELECT id FROM assets WHERE project_id = ? AND user_id = ?", (one, owner)):   # its NeuralCore
                await offload(kit.remove, db, state.assets_dir / str(owner), owner, row["id"])   # files too
            await db.arun("DELETE FROM projects WHERE id = ?", (one,))
    for person in people:
        await offload(state.outputs.remove_folder, person, its_folder)   # whatever is left in their folder of it; never the backup's copy
        state.notify(person, library_changed=True)
    return {"ok": True, "items_deleted": len(removed)}


# ---------------------------------------------------------------- people in a project

@router.get("/projects/{project_id}/members")
async def project_members(project_id: int, request: Request, user: dict = Depends(current_user)):
    """Everyone in a project and their roles, the user's own role, and the roles there are to give."""
    here = await offload(_own_project, request, user, project_id, "viewer")
    return {"members": await offload(sharing.members, request.app.state.db, here["top_id"]), "role": here["role"],
            "roles": [{"id": r, "label": sharing.LABELS[r], "about": sharing.ABOUT[r]} for r in sharing.ROLES]}


@router.post("/projects/{project_id}/members")
async def add_members(project_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    """{"people": [{"email", "role"}]}: add people to the whole project (all its modules). Someone already in it gets
    the role given. Each email that could not be added comes back with why."""
    here = await offload(_own_project, request, user, project_id, "manager")
    people = body.get("people") if isinstance(body.get("people"), list) else []
    if not people or len(people) > 50:
        raise HTTPException(400, "Add between 1 and 50 people at a time.")
    db = request.app.state.db
    added, problems = await offload(sharing.add, db, here, user, people)
    if added:
        await offload(audit.record, request, user, "Shared a project", "project {}".format(here["top_id"]), ", ".join("{} as {}".format(a["email"], a["role"]) for a in added))
    for person in added:
        request.app.state.notify(person["user_id"], library_changed=True)   # the project appears in their list
    return {"added": added, "problems": problems, "members": await offload(sharing.members, db, here["top_id"])}


@router.put("/projects/{project_id}/members/{member_id}")
async def change_member(project_id: int, member_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    here = await offload(_own_project, request, user, project_id, "manager")
    await offload(sharing.change, request.app.state.db, here, member_id, str(body.get("role") or ""))
    return {"members": await offload(sharing.members, request.app.state.db, here["top_id"])}


@router.delete("/projects/{project_id}/members/{member_id}")
async def remove_member(project_id: int, member_id: int, request: Request, user: dict = Depends(current_user)):
    """Take someone out of a project, or, for their own id, leave it. What they made there stays in it."""
    here = await offload(_own_project, request, user, project_id, "viewer" if member_id == user["id"] else "manager")
    if member_id == user["id"] and here["role"] == "owner":
        raise HTTPException(400, "The owner can't leave their own project. Delete it instead.")
    await offload(sharing.change, request.app.state.db, dict(here, role="owner") if member_id == user["id"] else here, member_id, None)
    request.app.state.notify(member_id, library_changed=True)
    return {"members": await offload(sharing.members, request.app.state.db, here["top_id"])}


# ---------------------------------------------------------------- the showcase on the Home page

def _showcase_file(request, key):
    item = showcase.find(request.app.state.db, key)
    path = item and storage.fetch_path(request.app.state, showcase.path_of(request.app.state.showcase_dir, item))
    if not path or not path.is_file():
        raise HTTPException(404, "No such item on the Home page.")
    return item, path


@router.get("/showcase")
async def get_showcase(request: Request, user: dict = Depends(current_user)):
    """What an admin picked for every user's Home page: its sections, and the items in the order they are shown."""
    data = await offload(showcase.load, request.app.state.db)
    return {"sections": data["sections"], "items": [showcase.public(i) for i in data["items"]]}


@router.get("/showcase/{key}/file")
async def showcase_file(key: str, request: Request, download: bool = False, user: dict = Depends(current_user)):
    item, path = await offload(_showcase_file, request, key)
    return (storage.signed(request.app.state, "showcase", path, safe_name(item["name"]) + path.suffix if download else None)
            or FileResponse(path, filename=safe_name(item["name"]) + path.suffix if download else None))


@router.get("/showcase/{key}/poster")
async def showcase_poster(key: str, request: Request, user: dict = Depends(current_user)):
    return await poster_response(request, (await offload(_showcase_file, request, key))[1])
