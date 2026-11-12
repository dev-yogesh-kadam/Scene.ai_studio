"""How the studio reaches Claude Code (claude.py), as an admin picks it in the console's Servers & APIs, "Claude
connection":

- "api_key": the `claude` installed with the studio (in its image) runs here, with an Anthropic API key.
- "lufi_bridge": the bridge on the PC LUFI runs the Claude Code signed in there, reached over Tailscale at its address,
  with its key (docs/servers.md). For testing only.

What is in use comes from the first that has it: a SCENE_* environment variable (Key Vault on Azure; the console can't
change those), the console's choice (the `settings` table, its keys sealed with vault.py), config.json. A change takes
effect on the next call to Claude, with no restart: apply() sets it in claude.CONNECTION, here and, through
shared.on_changed("settings"), in every other process of the app (main.py). The keys never go back to a page.

While the bridge is in use, the studio runs on its owner's personal Claude subscription, and they are its one user:
sign-up is closed (api/auth.signup_open) and only admins may use the agent (guard). Picking the API key lifts both."""

import asyncio
import time
from urllib.parse import urlsplit

import httpx

from . import claude, vault
from .db import ACTING, EVERYONE, as_everyone, offload

MODES = {claude.API_KEY: "Anthropic API key", claude.LUFI_BRIDGE: "LUFI bridge"}
FIELDS = ("claude_connection", "claude_bridge_url", "claude_bridge_key", "anthropic_api_key")
KEYS = ("claude_bridge_key", "anthropic_api_key")
TESTING = "Testing on a personal Claude subscription"
ADMINS_ONLY = "While the studio is tested on a personal Claude subscription, only admins can use the agent."
ANTHROPIC = "https://api.anthropic.com"   # where an API key is checked (key_works)
CHECK_WAIT = 10   # seconds a check of the connection may take
VERSION_EVERY = 600   # seconds the version of the `claude` here is known for before `claude -v` is run again
_versions = {}   # the claude program -> (when it was asked, its version)


def current(db, settings):
    """{field of FIELDS: its value in use}, and "fixed": the fields an environment variable sets."""
    fixed = set(getattr(settings, "from_environment", None) or ()) & set(FIELDS)
    found = {}
    for field in FIELDS:
        value = getattr(settings, field, "")
        if field not in fixed:
            saved = db.setting(field)
            if saved is not None:
                value = vault.reveal(saved) if field in KEYS else saved
        found[field] = str(value or "").strip()
    if found["claude_connection"] not in MODES:
        found["claude_connection"] = claude.API_KEY
    found["fixed"] = sorted(fixed)
    return found


def apply(db, settings):
    """Put the connection in use in claude.CONNECTION: every call to Claude after this one goes by it."""
    found = current(db, settings)
    claude.CONNECTION = {"mode": found["claude_connection"], "api_key": found["anthropic_api_key"],
                         "bridge_url": found["claude_bridge_url"], "bridge_key": found["claude_bridge_key"]}


def public(db, settings):
    """What the console's page is shown of the connection: never a key, only whether there is one."""
    found = current(db, settings)
    return {"mode": found["claude_connection"], "modes": MODES, "bridge_url": found["claude_bridge_url"],
            "has_bridge_key": bool(found["claude_bridge_key"]), "has_api_key": bool(found["anthropic_api_key"]),
            "fixed": found["fixed"], "testing": TESTING if found["claude_connection"] == claude.LUFI_BRIDGE else ""}


def clean_url(text):
    """The bridge's address, http(s)://host:port and nothing more. Raises ValueError when it is not one."""
    text = str(text or "").strip().rstrip("/")
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password \
            or parts.path or parts.query or parts.fragment:
        raise ValueError("The bridge's address is its scheme, host and port, like http://100.64.0.7:8765.")
    return text


def save(db, settings, body):
    """Keep the console's choice: {"mode", "bridge_url", "bridge_key", "api_key"}, each optional; a key left blank keeps
    the one there is. Then apply() it. Returns what changed, in words for the audit log (never a key). Raises
    ValueError with what is wrong."""
    now = current(db, settings)
    changes = {}
    if "mode" in body:
        mode = str(body.get("mode") or "").strip()
        if mode not in MODES:
            raise ValueError("Pick the Anthropic API key or the LUFI bridge.")
        changes["claude_connection"] = mode
    if "bridge_url" in body:
        changes["claude_bridge_url"] = clean_url(body.get("bridge_url"))
    for name, field in (("bridge_key", "claude_bridge_key"), ("api_key", "anthropic_api_key")):
        key = str(body.get(name) or "").strip()
        if key:
            changes[field] = key
    changes = {field: value for field, value in changes.items() if value != now[field]}
    for field in changes:
        if field in now["fixed"]:
            raise ValueError("{} is set by the environment variable SCENE_{}: change it there.".format(
                field.replace("_", " ").capitalize(), field.upper()))
    after = dict(now, **changes)
    if after["claude_connection"] == claude.LUFI_BRIDGE and not (after["claude_bridge_url"] and after["claude_bridge_key"]):
        raise ValueError("The LUFI bridge needs its address and its key.")
    for field, value in changes.items():
        db.set_setting(field, vault.seal(value) if field in KEYS else value)
    apply(db, settings)
    said = []
    if "claude_connection" in changes:
        said.append("connection: {} to {}".format(MODES[now["claude_connection"]], MODES[after["claude_connection"]]))
    if "claude_bridge_url" in changes:
        said.append("bridge address: {}".format(after["claude_bridge_url"] or "none"))
    said += ["a new {}".format(name) for field, name in (("claude_bridge_key", "bridge key"), ("anthropic_api_key", "API key"))
             if field in changes]
    return said


def testing():
    """Whether the studio runs on the LUFI bridge now: a personal subscription, for testing."""
    return claude.CONNECTION.get("mode") == claude.LUFI_BRIDGE


def _role(db, user_id):
    with as_everyone():
        row = db.one("SELECT role FROM users WHERE id = ?", (int(user_id),))
    return (row or {}).get("role")


def guard_for(db):
    """claude.GUARD for this database: on the bridge, a request of a user who is not an admin may not reach Claude. The
    console's requests and the studio's own work (the queue: no one request's) act for everyone, and pass."""
    async def guard():
        acting = ACTING.get()
        if not testing() or acting == EVERYONE:
            return
        if await offload(_role, db, acting) != "admin":
            raise claude.Failed(ADMINS_ONLY)
    return guard


async def status(run_claude=False):
    """How the connection in use is: {"mode", "online", "detail" (why not), "claude_version", "signed_in" (the bridge's
    Claude Code), "key_works" (the API key), "running" (calls running now), "limit" (the most the bridge runs at once),
    "bridge_version", "testing"}. On the bridge, its /health; with a key, the key asked of Anthropic's API (a list of
    one model: no tokens) and `claude -v` here. run_claude: also run `claude -v` through the bridge, so the way the
    calls go (its WebSocket) is tried too: the console's Test."""
    connection = dict(claude.CONNECTION)
    found = {"mode": connection["mode"], "online": False, "detail": "", "claude_version": "", "signed_in": None, "key_works": None,
             "running": claude.RUNNING["now"], "limit": None, "bridge_version": "", "testing": TESTING if testing() else ""}
    if connection["mode"] == claude.LUFI_BRIDGE:
        await _bridge_status(found, connection, run_claude)
    else:
        await _key_status(found, connection)
    return found


async def _bridge_status(found, connection, run_claude):
    if not connection["bridge_url"] or not connection["bridge_key"]:
        found["detail"] = "The LUFI bridge has no address or key yet: set them in Servers & APIs, Claude connection."
        return
    try:
        said = await asyncio.to_thread(claude.bridge_call, "GET", "/health")
    except (claude.Busy, claude.Failed) as error:
        found["detail"] = str(error)
        return
    number = lambda v: v if isinstance(v, int) and not isinstance(v, bool) else None
    found.update(claude_version=str(said.get("claude_version") or "")[:40], bridge_version=str(said.get("bridge_version") or "")[:40],
                 signed_in=said.get("signed_in") if isinstance(said.get("signed_in"), bool) else None,
                 running=number(said.get("calls_now")) or 0, limit=number(said.get("limit")))
    if found["signed_in"] is False:
        found["detail"] = "Claude on LUFI is signed out: sign Claude Code in again on LUFI."
    elif said.get("enabled") is False:
        found["detail"] = "The LUFI bridge is switched off. Switch it on on LUFI, or pick the API key connection."
    elif said.get("up") is not True:
        found["detail"] = "The LUFI bridge says it is not well: {}".format(str(said.get("last_error") or "no reason given")[:300])
    elif run_claude:
        try:
            found["claude_version"] = await version() or found["claude_version"]
        except (claude.Busy, claude.Failed) as error:
            found["detail"] = "The bridge answers, but could not run Claude Code: {}".format(error)
    found["online"] = not found["detail"]


async def _key_status(found, connection):
    program = claude.find()
    if not program:
        found["detail"] = claude.NOT_INSTALLED
        return
    seen = _versions.get(program)
    if seen and time.time() - seen[0] < VERSION_EVERY:
        found["claude_version"] = seen[1]
    else:
        try:
            found["claude_version"] = await version()
        except (claude.Busy, claude.Failed) as error:
            found["detail"] = str(error)
            return
        _versions[program] = (time.time(), found["claude_version"])
    if not connection["api_key"]:
        found["detail"] = "No Anthropic API key yet: paste one in Servers & APIs, Claude connection."
        return
    try:
        async with httpx.AsyncClient(timeout=CHECK_WAIT) as http:
            answer = await http.get(ANTHROPIC + "/v1/models", params={"limit": 1},
                                    headers={"x-api-key": connection["api_key"], "anthropic-version": "2023-06-01"})
    except httpx.HTTPError as error:
        found["detail"] = "Anthropic's API did not answer ({}).".format(type(error).__name__)
        return
    if answer.status_code in (401, 403):
        found["key_works"], found["detail"] = False, "Anthropic refused the API key: paste a working one."
    elif answer.status_code != 200:
        found["detail"] = "Anthropic's API answered {} to the check of the key.".format(answer.status_code)
    else:
        found["key_works"] = True
    found["online"] = not found["detail"]


async def version():
    """Claude Code's version, from `claude -v` run by the connection in use ("" when it printed none)."""
    ran = await claude._run(["-v"], "", None, CHECK_WAIT * 2)
    words = str(ran.stdout or "").split()
    return words[0][:40] if words else ""
