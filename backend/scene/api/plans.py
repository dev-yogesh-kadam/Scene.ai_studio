"""The agent's plans, run by the server (plans.py, docs/r1-plan-runner-design.md): stored when the agent makes one,
approved (its price reserved at once), stopped, resumed, and the take a shot's finished cut uses."""

import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from .. import preferences
from .deps import costly, current_user
from ..db import offload

router = APIRouter(prefix="/api")


def _runner(request: Request):
    return request.app.state.plans


@router.post("/agent/plans", dependencies=[costly("plan")])
async def create_plan(body: dict, request: Request, user: dict = Depends(current_user)):
    """{steps, name?, tab?, project_id?}: the steps as the agent's plan gives them. Priced; nothing is charged."""
    return await _runner(request).create(user, body)


@router.get("/agent/plans")
async def list_plans(request: Request, tab: str = "", project: int | None = None, user: dict = Depends(current_user)):
    return {"plans": await offload(_runner(request).listing, user, tab, project)}


@router.get("/agent/plans/{plan_id}")
async def get_plan(plan_id: int, request: Request, user: dict = Depends(current_user)):
    runner = _runner(request)
    return runner.shown(await offload(runner.get, user, plan_id))


@router.post("/agent/plans/{plan_id}/approve", dependencies=[costly("plan")])
async def approve_plan(plan_id: int, request: Request, body: dict | None = Body(None), user: dict = Depends(current_user)):
    """Reserve the plan's price and run it. Approving twice charges once. {"auto": true}: the page approves it by itself,
    without the user's Approve, which their permission (GET /api/agent/preferences) must allow for every step's kind."""
    if body and body.get("auto") is True:
        row = await offload(_runner(request).get, user, plan_id)
        kinds = {str(step.get("kind") or "") for step in json.loads(row["steps"]) if isinstance(step, dict)}
        if not preferences.runs_without_approve(await offload(preferences.agent, request.app.state.db, user["id"]), kinds):
            raise HTTPException(403, "This plan waits for your Approve: your permission asks before it runs.")
    return await _runner(request).approve(user, plan_id)


@router.post("/agent/plans/{plan_id}/stop")
async def stop_plan(plan_id: int, request: Request, user: dict = Depends(current_user)):
    return await offload(_runner(request).stop, user, plan_id)


@router.get("/agent/plans/{plan_id}/redo")
async def redo_plan(plan_id: int, request: Request, user: dict = Depends(current_user)):
    """What resuming a stopped or failed plan would make again, why each was not made, what is changed so it can be,
    and the price: shown for approval before /resume. Nothing is charged or queued."""
    return await _runner(request).redo(user, plan_id)


@router.post("/agent/plans/{plan_id}/resume", dependencies=[costly("plan")])
async def resume_plan(plan_id: int, request: Request, user: dict = Depends(current_user)):
    """A stopped or failed plan goes on: what is left is priced, reserved and run."""
    return await _runner(request).approve(user, plan_id, again=True)


@router.post("/agent/plans/{plan_id}/choose")
async def choose_take(plan_id: int, body: dict, request: Request, user: dict = Depends(current_user)):
    """{step, item}: the take of a shot step the finished cut uses."""
    step, item = body.get("step"), body.get("item")
    if item is not None and not isinstance(item, int):
        raise HTTPException(400, "A take is a library item's id.")
    return await offload(_runner(request).choose, user, plan_id, step, item)
