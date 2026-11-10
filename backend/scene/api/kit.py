"""The kit of a project (see kit.py): what it is made from, by name, and what is always on in its shots.

GET    /api/kit?project=          the entries, in order (none outside a project)
POST   /api/kit                   add: a file (multipart "file", "name", "type", "project_id", "always"), a library item
                                  (JSON {"item", "name", "type", "project_id", "always"}) or a script (JSON {"text", "name"})
PUT    /api/kit/{id}              change: name, type, about, use_note, always
POST   /api/kit/order             {"project_id", "ids"}: the entries in this order
POST   /api/kit/sheet             an asset sheet (a CSV: type, name, link, notes a row) brought in, each picture fetched
DELETE /api/kit/{id}
GET    /api/kit/{id}/file         the entry's file

What the user reads calls it NeuralCore. Each project has its own; its modules share it; there is none outside a project.
In a shared project the kit is the owner's: everyone in it sees it, and a creator or more changes it (sharing.py).
"""

import asyncio
import contextlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .. import kit, memory, sharing, storage
from ..db import as_everyone, offload
from ..references import media_kind, read_text_upload, read_upload, text_kind
from .deps import current_user, json_object, limited, project_ref, uploading

router = APIRouter(prefix="/api/kit", tags=["kit"])
SCRIPT_CHARS = 200_000   # the most a script typed or pasted into the kit holds


def _folder(request, user):
    return request.app.state.assets_dir / str(user["id"])


def _keeper(request, user, project, need):
    """(project id or None, whose kit it is, and how to read it): the user's own, or for a shared project its owner's,
    read on the owner's behalf once the user is found to be in it with role `need`."""
    project = project_ref(project)
    if not project:
        return None, user, contextlib.nullcontext
    found = sharing.require(request.app.state.db, user, project, need)
    if found["owner_id"] == user["id"]:
        return found["id"], user, contextlib.nullcontext
    return found["id"], {"id": found["owner_id"]}, as_everyone


def _keeper_of_entry(request, user, asset_id, need="creator"):
    """The same for a kit entry asked for by its id: the user's own entry, or one in a project shared with them where
    their role is `need` or more."""
    db = request.app.state.db
    if kit.entry(db, user["id"], asset_id) is not None:
        return user, contextlib.nullcontext
    with as_everyone():
        row = db.one("SELECT project_id FROM assets WHERE id = ?", (asset_id,))
    if row is None or not row["project_id"]:
        raise HTTPException(404, "No such NeuralCore entry.")
    _, keeper, reading = _keeper(request, user, row["project_id"], need)
    return keeper, reading


def describe_soon(request, user, project):
    """Have the agent's model look at the kit's pictures it has not described yet, in the background: the panel and
    the agent read the cards when they are done."""
    state = request.app.state

    async def look():   # it inherits this request's context: whose rows it reads
        rows = await offload(kit.entries, state.db, user["id"], project)
        entries = [memory._asset_entry(row) for row in rows if not row["about"]]
        if any(e["kind"] in ("image", "video") for e in entries):
            await memory.describe_missing(state, user["id"], entries, limit=8, seconds=600)
    asyncio.ensure_future(look()).add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


@router.get("")
async def get_kit(request: Request, project: int = 0, user: dict = Depends(current_user)):
    state = request.app.state
    project, keeper, reading = await offload(_keeper, request, user, project, "viewer")
    with reading():
        describe_soon(request, keeper, project)
        entries = [memory.kit_row(e) for e in await offload(kit.entries, state.db, keeper["id"], project)]
    return {"entries": entries, "project": bool(project),
            "types": [{"id": tag, "label": said} for tag, said in kit.TYPES.items()]}


@router.post("", dependencies=[limited("kit", 60, 600), uploading])
async def add_entry(request: Request, user: dict = Depends(current_user)):
    state = request.app.state
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await json_object(request)
        project, keeper, reading = await offload(_keeper, request, user, body.get("project_id"), "creator")
        if not project:
            raise HTTPException(400, "NeuralCore belongs to a project. Open a project first.")
        folder = _folder(request, keeper)
        name, tag, always = kit.clean_name(body.get("name")), kit.tag_of(body.get("type")), bool(body.get("always"))
        if body.get("item"):
            from .library import _own   # an item of the user's, or one made by someone else in this shared project
            item = await offload(_own, request, user, body["item"], "creator") if isinstance(body["item"], int) else None
            source = await offload(state.outputs.folder, item["user_id"]) / item["filename"] if item else None
            if not source or not source.is_file():
                raise HTTPException(404, "No such library item.")
            with reading():
                asset = await offload(kit.add, state.db, folder, keeper["id"], project, source.read_bytes(), Path(item["filename"]).name, item["kind"],
                                name or item["name"], tag, always, True, item.get("about") or "", made_from=item["id"])
                if body.get("type"):
                    await offload(kit.update, state.db, keeper["id"], asset, {"type": body["type"]})
        elif isinstance(body.get("text"), str) and body["text"].strip():
            if not name:
                raise HTTPException(400, "Give the script a name.")
            words = body["text"].strip()[:SCRIPT_CHARS].encode("utf-8")
            with reading():
                asset = await offload(kit.add, state.db, folder, keeper["id"], project, words, name + ".txt", "text", name, body.get("type") or "script", always)
        else:
            raise HTTPException(400, "Send a file, a library item or the text of a script.")
    else:
        form = await request.form(max_files=1, max_fields=10)
        upload = form.get("file")
        if not hasattr(upload, "filename"):
            raise HTTPException(400, "Choose a file.")
        project, keeper, reading = await offload(_keeper, request, user, form.get("project_id"), "creator")
        if not project:
            raise HTTPException(400, "NeuralCore belongs to a project. Open a project first.")
        if text_kind(upload.filename):
            data, filename = await read_text_upload(upload)
            kind = "text"
        else:
            kind = media_kind(upload.filename)
            if kind is None:
                raise HTTPException(400, "Use a picture, a video, a sound, or a script (.txt, .md, .docx, .pdf).")
            data = await read_upload(upload)
            filename = upload.filename   # a HEIC or AVIF photo is a JPEG or PNG now
        tag = form.get("type") or ("script" if kind == "text" else "voice" if kind == "audio" else "other")
        with reading():
            asset = await offload(kit.add, state.db, _folder(request, keeper), keeper["id"], project, data, filename, kind,
                            str(form.get("name") or filename.rsplit(".", 1)[0]), tag, str(form.get("always") or "") in ("1", "true", "on"),
                            use_note=str(form.get("use_note") or ""))
    with reading():
        describe_soon(request, keeper, project)
        return memory.kit_row(await offload(kit.entry, state.db, keeper["id"], asset))


@router.post("/sheet", dependencies=[limited("kit-sheet", 10, 600), uploading])
async def import_sheet(request: Request, user: dict = Depends(current_user)):
    """An asset sheet (a CSV or TSV: one row an entry, with its type, name, a link to its picture and notes) brought into
    a project's NeuralCore, each row's picture fetched from its link (sheet.py). Multipart "file" and "project_id", or
    JSON {"text", "project_id"}. Returns what was added, what was there already, the looks linked and the rows that
    failed, with why."""
    from .. import sheet
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await json_object(request)
        given, text = body.get("project_id"), str(body.get("text") or "")
    else:
        form = await request.form(max_files=1, max_fields=4)
        upload = form.get("file")
        if not hasattr(upload, "filename"):
            raise HTTPException(400, "Choose the sheet: a .csv or .tsv file.")
        data, _ = await read_text_upload(upload)
        given, text = form.get("project_id"), data.decode("utf-8-sig")
    project, keeper, reading = await offload(_keeper, request, user, given, "creator")
    if not project:
        raise HTTPException(400, "NeuralCore belongs to a project. Open a project first.")
    try:
        rows, left = sheet.parse(text)
    except sheet.SheetError as error:
        raise HTTPException(400, str(error))
    with reading():
        done = await sheet.bring_in(request.app.state.db, _folder(request, keeper), keeper["id"], project, rows)
        describe_soon(request, keeper, project)
    return dict(done, left_out=left)


@router.get("/{asset_id}/file")
async def entry_file(asset_id: int, request: Request, user: dict = Depends(current_user)):
    keeper, reading = await offload(_keeper_of_entry, request, user, asset_id, "viewer")
    with reading():
        found = await offload(kit.entry, request.app.state.db, keeper["id"], asset_id)
    path = _folder(request, keeper) / found["filename"] if found else None
    elsewhere = path and storage.signed(request.app.state, "kit", path)
    if elsewhere:   # kept in Blob Storage: the browser fetches it from there (storage.py)
        return elsewhere
    if path is None or not path.is_file():
        raise HTTPException(404, "The file is missing from storage.")
    return FileResponse(path)


@router.get("/{asset_id}/poster")
async def entry_poster(asset_id: int, request: Request, user: dict = Depends(current_user)):
    """A small copy of an entry's picture, or a still from its clip, for its thumbnail (as a library item's poster)."""
    from .library import poster_response
    keeper, reading = await offload(_keeper_of_entry, request, user, asset_id, "viewer")
    with reading():
        found = await offload(kit.entry, request.app.state.db, keeper["id"], asset_id)
    if found is None:
        raise HTTPException(404, "No such NeuralCore entry.")
    return await poster_response(request, _folder(request, keeper) / found["filename"])


@router.put("/{asset_id}")
async def change_entry(asset_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    keeper, reading = await offload(_keeper_of_entry, request, user, asset_id)
    with reading():
        try:
            found = await offload(kit.update, request.app.state.db, keeper["id"], asset_id, body)
        except ValueError as error:   # a look, a palette or a relative that does not fit (kit._links)
            raise HTTPException(400, str(error))
    if found is None:
        raise HTTPException(404, "No such NeuralCore entry.")
    return memory.kit_row(found)


@router.post("/order")
async def order_entries(body: dict, request: Request, user: dict = Depends(current_user)):
    project, keeper, reading = await offload(_keeper, request, user, body.get("project_id"), "creator")
    ids = [i for i in body["ids"] if isinstance(i, int) and not isinstance(i, bool)] if isinstance(body.get("ids"), list) else []
    with reading():
        await offload(kit.reorder, request.app.state.db, keeper["id"], project, ids)
        return {"entries": [memory.kit_row(e) for e in await offload(kit.entries, request.app.state.db, keeper["id"], project)]}


@router.delete("/{asset_id}")
async def delete_entry(asset_id: int, request: Request, user: dict = Depends(current_user)):
    keeper, reading = await offload(_keeper_of_entry, request, user, asset_id)
    with reading():
        removed = await offload(kit.remove, request.app.state.db, _folder(request, keeper), keeper["id"], asset_id)
    if not removed:
        raise HTTPException(404, "No such NeuralCore entry.")
    return {"ok": True}
