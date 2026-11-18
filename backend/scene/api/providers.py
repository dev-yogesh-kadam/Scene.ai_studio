"""The console's Servers & APIs → Providers (providers/registry.py, providers/router.py): every provider with its keys,
adding a key (checked with the provider before it is saved), changing, testing and removing keys and providers, the
provider router's switch, and which provider the agent uses. Admins only (staff.ADMIN_ONLY). A key is never sent back:
only its label and last 4 characters."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import audit, claude_connection, health
from ..db import offload
from ..providers import registry
from ..providers.base import BUILT_IN, CLAUDE_KINDS, KEYLESS, KINDS, SELF_HOSTED, KeyProblem, ProviderProblem, RequestProblem
from ..providers.comfyui import capability_of
from .deps import admin_user, current_user

router = APIRouter(prefix="/api/admin/providers", tags=["admin"])


async def _listing(state):
    found = await offload(registry.listing, state.db, state.settings)
    return {"kinds": KINDS, "self_hosted": list(SELF_HOSTED), "keyless": list(KEYLESS), "built_in": list(BUILT_IN), "providers": found,
            "router": await offload(registry.router_mode, state.db), "modes": list(registry.ROUTER_MODES),
            "agent_provider": await offload(registry.agent_provider_id, state.db),
            "testing": claude_connection.TESTING if claude_connection.testing() else ""}


async def _changed(state, kind=None):
    """After a change: the router looks again, the offered models are read again, ComfyUI's servers (the load
    balancer) and the Claude connection (claude.CONNECTION, in every process) are read again."""
    state.router.forget()
    if state.catalog.providers is not None:
        await state.catalog.providers.refresh(force=True)
    if kind in (None, "comfyui"):
        await offload(state.comfy_pool.reload)
        health.forget(state, "endpoints")
        state.jobs._wake()
    if kind is None or kind in CLAUDE_KINDS:
        await offload(claude_connection.apply, state.db, state.settings)
        if getattr(state.db, "shared", None) is not None:
            await offload(state.db.shared.changed, "settings")   # the app's other processes read it again
        health.forget(state, "model")


@router.get("")
async def list_providers(request: Request, user: dict = Depends(admin_user)):
    return await _listing(request.app.state)


async def _check(state, row, secret):
    """Ask a provider about a key before it is saved: whoami and models. {"ok", "models", "credits", "alerts", "error",
    "status", "info", "found"} (found: the models, to save with the key)."""
    adapter = await offload(state.router.adapter, row)   # a ComfyUI one reads its endpoints row
    try:
        said = await adapter.whoami(secret)
        found = await adapter.models(secret)
    except KeyProblem as problem:
        return {"ok": False, "status": problem.status or "unknown", "error": str(problem), "models": 0}
    except (ProviderProblem, RequestProblem) as problem:
        return {"ok": False, "status": "unknown", "error": str(problem), "models": 0}
    credits = said.get("credits") if isinstance(said.get("credits"), dict) else {}
    return {"ok": True, "status": "ok", "error": "", "models": len(found), "credits": credits.get("available"),
            "alerts": [str(a) for a in said.get("alerts") or []][:6], "info": said, "found": found}


def _public(check):
    return {k: v for k, v in check.items() if k not in ("info", "found")}


@router.post("/keys")
async def add_key(body: dict, request: Request, user: dict = Depends(admin_user)):
    """Add a key: to an existing provider (`provider_id`), or to a new one (`kind`, its `base_url` once for a
    self-hosted one, `name`). The key is checked with the provider first (whoami and models); one that fails is not
    saved unless `save_anyway`. Answers {"check", "saved", "provider_id", "key_id"} and the whole listing."""
    state = request.app.state
    secret = str(body.get("secret") or "").strip()
    provider_id = body.get("provider_id")
    if provider_id:
        row = await offload(registry.provider, state.db, provider_id)
        if row is None:
            raise HTTPException(404, "There is no such provider.")
    else:
        kind = str(body.get("kind") or "")
        if kind not in KINDS:
            raise HTTPException(400, "Pick a provider type.")
        base_url = registry.clean_url(body.get("base_url")) if kind in SELF_HOSTED else ""
        if kind in SELF_HOSTED and not base_url:
            raise HTTPException(400, "A new {} provider needs its address, once.".format(KINDS[kind]))
        row = {"id": None, "kind": kind, "name": str(body.get("name") or KINDS[kind]), "base_url": base_url, "legacy": "", "active": 1}
    if row["kind"] in KEYLESS:
        raise HTTPException(400, "{} has no key: it uses the account Claude Code is signed in with on this PC.".format(KINDS[row["kind"]]))
    if row["kind"] in BUILT_IN:
        raise HTTPException(400, "{} needs no key: its tools run on this PC.".format(KINDS[row["kind"]]))
    if not secret and row["kind"] != "comfyui":
        raise HTTPException(400, "Paste the key.")
    check = await _check(state, row, secret)
    if not check["ok"] and not body.get("save_anyway"):
        return dict(await _listing(state), check=_public(check), saved=False)
    try:
        if not provider_id:
            provider_id = await offload(registry.add_provider, state.db, row["kind"], row["name"], row["base_url"])
        key_id = await offload(registry.add_key, state.db, provider_id, secret, body.get("label"), body.get("max_concurrent"),
                               body.get("daily_cap"), 0, check["status"], check.get("info"), check["error"])
    except (ValueError, LookupError) as error:
        raise HTTPException(400, str(error))
    if check["ok"]:
        await offload(registry.save_models, state.db, provider_id, key_id, check["found"])
    added = await offload(registry.key, state.db, key_id)
    owner = await offload(registry.provider, state.db, provider_id)
    await offload(audit.record, request, user, "Added a provider key", owner["name"], "{} (…{}){}".format(
        added["label"], added["last4"] or "", "" if check["ok"] else ", saved though it failed: " + check["error"][:120]))
    await _changed(state, owner["kind"])
    return dict(await _listing(state), check=_public(check), saved=True, provider_id=provider_id, key_id=key_id)


MANY_AT_ONCE = 4   # keys of one paste checked with the provider at the same time


@router.post("/keys/many")
async def add_keys(body: dict, request: Request, user: dict = Depends(admin_user)):
    """Several keys of one provider pasted at once (`text`, one a line: "label<TAB>key" as the generation server's
    "Copy all" gives them, or the key alone), to an existing provider (`provider_id`) or a new one (`kind`, `name`,
    `base_url`). Each is checked with the provider and saved when it works (or with `save_anyway`); a key with no label
    takes the label the provider gives it. A key the provider has already is left out. Answers {"results": [{"line",
    "label", "saved", "check"}], "saved", "provider_id"} and the whole listing."""
    state = request.app.state
    try:
        pasted = registry.parse_keys(body.get("text"))
    except ValueError as error:
        raise HTTPException(400, str(error))
    provider_id = body.get("provider_id")
    if provider_id:
        row = await offload(registry.provider, state.db, provider_id)
        if row is None:
            raise HTTPException(404, "There is no such provider.")
    else:
        kind = str(body.get("kind") or "")
        if kind not in KINDS:
            raise HTTPException(400, "Pick a provider type.")
        base_url = registry.clean_url(body.get("base_url")) if kind in SELF_HOSTED else ""
        if kind in SELF_HOSTED and not base_url:
            raise HTTPException(400, "A new {} provider needs its address, once.".format(KINDS[kind]))
        row = {"id": None, "kind": kind, "name": str(body.get("name") or KINDS[kind]), "base_url": base_url, "legacy": "", "active": 1}
    if row["kind"] in BUILT_IN:
        raise HTTPException(400, "{} needs no key: its tools run on this PC.".format(KINDS[row["kind"]]))
    if row["kind"] in KEYLESS or row["kind"] == "comfyui":
        raise HTTPException(400, "{} keys are added one at a time.".format(KINDS[row["kind"]]))
    try:   # checked before any key is: one wrong number stops the paste, not half of it
        most = registry._int(body.get("max_concurrent"), None, 1, registry.MOST_CONCURRENT)
        cap = registry._int(body.get("daily_cap"), None, 0)
    except ValueError as error:
        raise HTTPException(400, str(error))
    gate = asyncio.Semaphore(MANY_AT_ONCE)

    async def checked(entry):
        if row["id"] is not None:
            there = await offload(registry.has_secret, state.db, row["id"], entry["secret"])
            if there:
                return entry, None, there
        async with gate:
            return entry, await _check(state, row, entry["secret"]), ""

    results, saved = [], 0
    for entry, check, there in await asyncio.gather(*(checked(e) for e in pasted)):
        if there:
            results.append({"line": entry["line"], "label": there, "saved": False,
                            "check": {"ok": True, "status": "ok", "error": "", "models": 0}, "words": "Already here as " + there})
            continue
        said_label = str(((check.get("info") or {}).get("key") or {}).get("label") or "")
        label = entry["label"] or said_label
        if not check["ok"] and not body.get("save_anyway"):
            results.append({"line": entry["line"], "label": label, "saved": False, "check": _public(check)})
            continue
        if row["id"] is None:   # the first key that is saved makes the new provider
            row["id"] = provider_id = await offload(registry.add_provider, state.db, row["kind"], row["name"], row["base_url"])
        key_id = await offload(registry.add_key, state.db, row["id"], entry["secret"], label, most, cap, 0,
                               check["status"], check.get("info"), check["error"])
        if check["ok"]:
            await offload(registry.save_models, state.db, row["id"], key_id, check["found"])
        added = await offload(registry.key, state.db, key_id)
        saved += 1
        results.append({"line": entry["line"], "label": added["label"], "saved": True, "check": _public(check), "key_id": key_id})
    if saved:
        owner = await offload(registry.provider, state.db, row["id"])
        await offload(audit.record, request, user, "Added provider keys", owner["name"], "{} of {} pasted: {}".format(
            saved, len(pasted), ", ".join(r["label"] for r in results if r["saved"])[:300]))
        await _changed(state, owner["kind"])
    return dict(await _listing(state), results=results, saved=saved, provider_id=row["id"])


# ---------------------------------------------------------------- what makes what

async def _comfy_workflows(state):
    """The studio's ComfyUI workflow files (not the generation server's, nor the providers' models), with their capability."""
    found = []
    for item in await state.catalog.listing():
        if item.get("provider") or item["id"].rsplit("/", 1)[-1].startswith("generation_"):
            continue
        found.append({"id": item["id"], "title": item.get("title") or item["id"], "capability": capability_of(item["id"])})
    return found


async def _coverage(state):
    rows = await offload(registry.coverage, state.db, await _comfy_workflows(state))
    return {"router": await offload(registry.router_mode, state.db), "capabilities": rows}


@router.get("/capabilities")
async def capabilities(request: Request, user: dict = Depends(admin_user)):
    """What makes what: per capability, the providers' models (with the keys that have them) and the ComfyUI
    workflows, and whether ComfyUI is still offered for it."""
    return await _coverage(request.app.state)


@router.put("/capabilities/{capability}")
async def set_capability(capability: str, body: dict, request: Request, user: dict = Depends(admin_user)):
    """ComfyUI switched off (`{"comfyui": false}`) or back on for one capability. Off only while the router is on and a
    live provider key offers it, so something always makes it; back on at any time."""
    state = request.app.state
    on = body.get("comfyui")
    if not isinstance(on, bool):
        raise HTTPException(400, 'Say {"comfyui": true} or false.')
    rows = (await _coverage(state))["capabilities"]
    row = next((r for r in rows if r["capability"] == capability), None)
    if row is None:
        raise HTTPException(404, "There is no capability '{}'.".format(capability))
    if not on and row["comfyui_on"] and not row["can_switch_off"]:
        raise HTTPException(400, "ComfyUI still makes {}: {}".format(row["words"].lower(), row["why_not"]))
    await offload(registry.set_comfyui, state.db, capability, on)
    if on != row["comfyui_on"]:
        await offload(audit.record, request, user, "Switched ComfyUI {} for a capability".format("on" if on else "off"), row["words"], "")
    return await _coverage(state)


# ---------------------------------------------------------------- the voices of the voiceover model (any signed-in user)

voices_router = APIRouter(prefix="/api/voices", tags=["studio"])


@voices_router.get("")
async def voices(request: Request, q: str = "", language: str = "", user: dict = Depends(current_user)):
    """The provider's voices for its voiceover model, for picking a voice id: {"voices": [...], "words"}."""
    found, words = await request.app.state.router.voices(q, language)
    return {"voices": found[:500], "words": words}


@router.put("/keys/{key_id}")
async def change_key(key_id: int, body: dict, request: Request, user: dict = Depends(admin_user)):
    """A key's label, on/off, max at once, daily cap, order, or a new key in its place."""
    state = request.app.state
    if key_id < 0:
        raise HTTPException(400, "This key is set by an environment variable: change it there.")
    try:
        row = await offload(registry.change_key, state.db, key_id, body)
    except LookupError as error:
        raise HTTPException(404, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))
    owner = await offload(registry.provider, state.db, row["provider_id"])
    await offload(audit.record, request, user, "Changed a provider key", owner["name"], "{} (…{}){}{}".format(
        row["label"], row["last4"], "" if row["active"] else ", off", ", a new key pasted" if str(body.get("secret") or "").strip() else ""))
    await _changed(state, owner["kind"])
    return await _listing(state)


@router.post("/keys/{key_id}/test")
async def test_key(key_id: int, request: Request, user: dict = Depends(admin_user)):
    """Ask the provider about this key now: whoami and its models (saved when it works)."""
    state = request.app.state
    if key_id < 0:   # a key an environment variable sets: tested, nothing stored
        rows = await offload(registry.providers, state.db)
        row = next((r for r in rows if registry.FIXED_IDS.get(r["kind"]) == key_id), None)
        fixed = next(iter(registry.fixed_keys(state.settings, row)), None) if row else None
        if fixed is None:
            raise HTTPException(404, "There is no such key.")
        check = await _check(state, row, registry.secret_of(fixed))
        return dict(await _listing(state), check=_public(check))
    key_row = await offload(registry.key, state.db, key_id)
    if key_row is None:
        raise HTTPException(404, "There is no such key.")
    owner = await offload(registry.provider, state.db, key_row["provider_id"])
    check = await state.router.check_key(owner, key_row)
    await _changed(state, owner["kind"])
    return dict(await _listing(state), check=check)


@router.delete("/keys/{key_id}")
async def remove_key(key_id: int, request: Request, user: dict = Depends(admin_user)):
    state = request.app.state
    if key_id < 0:
        raise HTTPException(400, "This key is set by an environment variable: remove it there.")
    if state.router.busy(key_id):
        raise HTTPException(400, "A job is running with this key. Switch it off, and remove it once the job is done.")
    try:
        row = await offload(registry.remove_key, state.db, key_id)
    except LookupError as error:
        raise HTTPException(404, str(error))
    owner = await offload(registry.provider, state.db, row["provider_id"])
    await offload(audit.record, request, user, "Removed a provider key", owner["name"], "{} (…{})".format(row["label"], row["last4"]))
    await _changed(state, owner["kind"])
    return await _listing(state)


@router.put("/router")
async def set_router(body: dict, request: Request, user: dict = Depends(admin_user)):
    """The provider router's switch: off (today's paths), shadow (today's paths, the router's pick logged beside),
    on (the generation models through the providers)."""
    state = request.app.state
    mode = str(body.get("mode") or "")
    if mode not in registry.ROUTER_MODES:
        raise HTTPException(400, "The router is off, shadow or on.")
    before = await offload(registry.router_mode, state.db)
    await offload(state.db.set_setting, registry.ROUTER, mode)
    if before != mode:
        await offload(audit.record, request, user, "Switched the provider router", "", "{} to {}".format(before, mode))
    await _changed(state)
    return await _listing(state)


@router.put("/agent")
async def set_agent(body: dict, request: Request, user: dict = Depends(admin_user)):
    """Which provider the agent uses: Claude on this PC or Anthropic. On Claude on this PC, a personal subscription,
    sign-up stays closed and only admins use the agent."""
    state = request.app.state
    fixed = set(getattr(state.settings, "from_environment", None) or ())
    if "claude_connection" in fixed:
        raise HTTPException(400, "The connection is set by the environment variable SCENE_CLAUDE_CONNECTION: change it there.")
    try:
        row = await offload(registry.set_agent_provider, state.db, body.get("provider_id"))
    except ValueError as error:
        raise HTTPException(400, str(error))
    # The old card's setting kept beside it, for the code of before (claude_connection reads the registry first).
    await offload(state.db.set_setting, "claude_connection", registry.MODE_OF[row["kind"]])
    await offload(audit.record, request, user, "Picked the agent's provider", row["name"], KINDS[row["kind"]])
    await _changed(state, row["kind"])
    return await _listing(state)


@router.put("/{provider_id}")
async def change_provider(provider_id: int, body: dict, request: Request, user: dict = Depends(admin_user)):
    """A provider's name, address, on/off, order; a ComfyUI server's Workflows (`workflows`)."""
    state = request.app.state
    try:
        row = await offload(registry.change_provider, state.db, provider_id, body)
    except LookupError as error:
        raise HTTPException(404, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))
    await offload(audit.record, request, user, "Changed a provider", row["name"], "{}{}".format(
        row["base_url"] or KINDS[row["kind"]], "" if row["active"] else ", off"))
    await _changed(state, row["kind"])
    return await _listing(state)


@router.delete("/{provider_id}")
async def remove_provider(provider_id: int, request: Request, user: dict = Depends(admin_user)):
    state = request.app.state
    row = await offload(registry.provider, state.db, provider_id)
    if row is None:
        raise HTTPException(404, "There is no such provider.")
    held = [k for k in await offload(registry.keys, state.db, provider_id) if state.router.busy(k["id"])]
    endpoint = await offload(registry.endpoint_of, state.db, row)
    if held or (endpoint and state.comfy_pool.running(endpoint["url"])):
        raise HTTPException(400, "A job is running there. Switch it off, and remove it once the job is done.")
    try:
        await offload(registry.remove_provider, state.db, provider_id)
    except ValueError as error:
        raise HTTPException(400, str(error))
    await offload(audit.record, request, user, "Removed a provider", row["name"], row["base_url"] or KINDS[row["kind"]])
    await _changed(state, row["kind"])
    return await _listing(state)

