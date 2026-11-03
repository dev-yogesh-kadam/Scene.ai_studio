"""The state of the user's long runs (runs.py): read, write, list and check, for the agent and for the Agent tab."""

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import core, recall, runs, sharing
from .deps import current_user

router = APIRouter(prefix="/api", tags=["runs"])


def _guarded(work):
    try:
        return work()
    except runs.RunError as error:
        raise HTTPException(400, str(error))


@router.get("/runs")
async def list_runs(request: Request, user: dict = Depends(current_user)):
    return {"runs": runs.listing(request.app.state.db, user["id"])}


@router.get("/runs/{run}/state")
async def read_state(run: str, request: Request, path: str, offset: int = 0, limit: int = runs.PAGE, user: dict = Depends(current_user)):
    return _guarded(lambda: runs.read(request.app.state.db, user["id"], run, path, offset, limit))


@router.put("/runs/{run}/state")
async def write_state(run: str, body: dict, request: Request, user: dict = Depends(current_user)):
    """Body: {"path", "value", "writer"?}; "append": true adds the value as one line of the list at the path."""
    db = request.app.state.db
    if "value" not in body:
        raise HTTPException(400, "Give the value to keep.")
    if body.get("append") is True:
        return _guarded(lambda: runs.append(db, user["id"], run, body.get("path"), body["value"], body.get("writer")))
    return _guarded(lambda: runs.write(db, user["id"], run, body.get("path"), body["value"], body.get("writer")))


@router.delete("/runs/{run}/state")
async def delete_state(run: str, request: Request, path: str, user: dict = Depends(current_user)):
    return {"deleted": _guarded(lambda: runs.delete(request.app.state.db, user["id"], run, path))}


@router.get("/runs/{run}/coverage")
async def check_coverage(run: str, request: Request, path: str, against: str, user: dict = Depends(current_user)):
    """Whether every name under `against` has one under `path`: {"ok", "missing", "extra", "count"}."""
    return _guarded(lambda: runs.coverage(request.app.state.db, user["id"], run, path, against))


# ---------------------------------------------------------------- NeuralCore's shared memory (core.py), for its Memory view

def _core(request, user, project, run):
    if project:
        sharing.require(request.app.state.db, user, project, "viewer")
    run = run if run and runs.RUN.match(run) else ""
    try:
        return core.Core(request.app.state.db, user["id"], run, project)
    except runs.RunError as error:
        raise HTTPException(404, str(error))


@router.get("/core/memory")
async def core_memory(request: Request, project: int = 0, run: str = "", user: dict = Depends(current_user)):
    """The module's memory as NeuralCore shows it: {"total", "writable", "leaves"} of its own notes, "cast" (the project's
    entries as the module uses them) and "assets" ({"total", "records"}: the catalogue, newest first)."""
    shared = _core(request, user, project, run)
    found = _guarded(shared.tree)
    return dict(found, cast=_guarded(shared.cast), assets=_guarded(shared.catalogue))


@router.put("/core/state")
async def core_write(body: dict, request: Request, user: dict = Depends(current_user)):
    """Body: {"project_id", "run"?, "path", "value"}: a leaf changed by hand in the Memory view."""
    shared = _core(request, user, body.get("project_id") or 0, str(body.get("run") or ""))
    if "value" not in body:
        raise HTTPException(400, "Give the value to keep.")
    return _guarded(lambda: shared.write(body.get("path"), body["value"], "user"))


@router.delete("/core/state")
async def core_delete(request: Request, path: str, project: int = 0, run: str = "", user: dict = Depends(current_user)):
    shared = _core(request, user, project, run)
    return {"deleted": _guarded(lambda: shared.delete(path))}


# ---------------------------------------------------------------- what the agent remembers of the user (recall.py)

@router.get("/remembered")
async def my_memory(request: Request, user: dict = Depends(current_user)):
    return {"entries": recall.entries(request.app.state.db, user["id"])}


@router.delete("/remembered")
async def forget_memory(request: Request, key: str, user: dict = Depends(current_user)):
    try:
        return {"forgotten": recall.forget(request.app.state.db, user["id"], key)}
    except recall.RecallError as error:
        raise HTTPException(400, str(error))
