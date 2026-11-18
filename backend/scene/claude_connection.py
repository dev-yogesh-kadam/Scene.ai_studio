"""How the studio reaches Claude Code (claude.py), as an admin picks it in the console's Servers & APIs → Providers,
"The agent uses":

- "this_pc" (Claude on this PC): the `claude` on this PC runs here, with the account Claude Code is signed in with.
- "api_key": the same `claude`, with an Anthropic API key.

What is in use comes from the first that has it: a SCENE_* environment variable (the console can't change those), the
console's choice (the provider registry; on a database without one, the `settings` table, its key sealed with
vault.py), config.json. A change takes
effect on the next call to Claude, with no restart: apply() sets it in claude.CONNECTION, here and, through
shared.on_changed("settings"), in every other process of the app (main.py). The keys never go back to a page.

A Claude subscription is for its owner's own use. So while Claude on this PC is in use, the studio runs on its owner's
personal subscription, and they are its one user: sign-up is closed (api/auth.signup_open) and only admins
may use the agent (guard). Picking the API key lifts both.

The console signs Claude Code here in and out (login_start, login_code, login_cancel, logout): `claude auth login`
runs here and gives a link to claude.com; the admin signs in there, in their own browser on any machine, and pastes
the code Anthropic's page shows back into the console, which writes it to the waiting `claude`. It is the same
sign-in as `claude` then /login in a terminal on this PC, so it is also the one this PC's own Claude Code uses."""

import asyncio
import json
import os
import re
import subprocess
import threading
import time

import httpx

from . import claude, vault
from .db import ACTING, EVERYONE, as_everyone, offload

MODES = {claude.LOCAL_SIGNIN: "Claude on this PC", claude.API_KEY: "Anthropic API key"}
PERSONAL = (claude.LOCAL_SIGNIN,)   # the modes that run on a personal Claude subscription
FIELDS = ("claude_connection", "anthropic_api_key")
KEYS = ("anthropic_api_key",)
TESTING = "Personal Claude subscription"
ADMINS_ONLY = "While the agent runs on a personal Claude subscription, only admins can use it."
ANTHROPIC = "https://api.anthropic.com"   # where an API key is checked (key_works)
CHECK_WAIT = 10   # seconds a check of the connection may take
VERSION_EVERY = 600   # seconds the version of the `claude` here is known for before `claude -v` is run again
SIGNIN_EVERY = 300    # seconds what `claude auth status` said is known for before it is asked again
LIMITS_SETTING = "claude_plan_limits"   # the plan's limits as last reported (claude.LIMITS), kept across restarts
_versions = {}   # the claude program -> (when it was asked, its version)
_signins = {}    # the claude program -> (when it was asked, what it said: {"signed_in", "account", "plan"})


def _registry(db, settings):
    """The connection as the provider registry has it (providers/registry.py, migration 0015), or None: a stand-in
    database with no registry (a test's), or a registry with no Claude provider. Since 0015 the registry is where the
    console keeps it; the settings rows are kept beside it for the code of before."""
    if getattr(db, "kind", "") != "postgres":
        return None
    from .providers import registry
    try:
        return registry.claude_values(db, settings)
    except Exception as error:   # the tables are not there (a database behind its migrations): the settings, as before
        print("The provider registry could not be read for the Claude connection: {}".format(error))
        return None


def current(db, settings):
    """{field of FIELDS: its value in use}, and "fixed": the fields an environment variable sets. An environment
    variable wins; then the provider registry; then (a database without one) the console's settings rows; then
    config.json."""
    fixed = set(getattr(settings, "from_environment", None) or ()) & set(FIELDS)
    registered = _registry(db, settings)
    found = {}
    for field in FIELDS:
        value = getattr(settings, field, "")
        if field not in fixed:
            if registered is not None:
                value = registered[field] or ("" if field in KEYS else value)
            else:
                saved = db.setting(field)
                if saved is not None:
                    value = vault.reveal(saved) if field in KEYS else saved
        found[field] = str(value or "").strip()
    if found["claude_connection"] not in MODES:
        found["claude_connection"] = claude.LOCAL_SIGNIN
    found["fixed"] = sorted(fixed)
    return found


def apply(db, settings):
    """Put the connection in use in claude.CONNECTION: every call to Claude after this one goes by it."""
    found = current(db, settings)
    claude.CONNECTION = {"mode": found["claude_connection"], "api_key": found["anthropic_api_key"]}


def public(db, settings):
    """What the console's page is shown of the connection: never a key, only whether there is one."""
    found = current(db, settings)
    return {"mode": found["claude_connection"], "modes": MODES, "has_api_key": bool(found["anthropic_api_key"]),
            "fixed": found["fixed"], "testing": TESTING if found["claude_connection"] in PERSONAL else ""}


def save(db, settings, body):
    """Keep the console's choice: {"mode", "api_key"}, each optional; a key left blank keeps the one there is. Then apply() it. Returns what changed, in words for the audit log (never a key). Raises
    ValueError with what is wrong."""
    now = current(db, settings)
    changes = {}
    if "mode" in body:
        mode = str(body.get("mode") or "").strip()
        if mode not in MODES:
            raise ValueError("Pick Claude on this PC or the Anthropic API key.")
        changes["claude_connection"] = mode
    key = str(body.get("api_key") or "").strip()
    if key:
        changes["anthropic_api_key"] = key
    changes = {field: value for field, value in changes.items() if value != now[field]}
    for field in changes:
        if field in now["fixed"]:
            raise ValueError("{} is set by the environment variable SCENE_{}: change it there.".format(
                field.replace("_", " ").capitalize(), field.upper()))
    after = dict(now, **changes)
    for field, value in changes.items():
        db.set_setting(field, vault.seal(value) if field in KEYS else value)
    if getattr(db, "kind", "") == "postgres":   # the registry is where it is read from (current)
        from .providers import registry
        registry.save_claude(db, changes)
    apply(db, settings)
    said = []
    if "claude_connection" in changes:
        said.append("connection: {} to {}".format(MODES[now["claude_connection"]], MODES[after["claude_connection"]]))
    if "anthropic_api_key" in changes:
        said.append("a new API key")
    return said


def testing():
    """Whether the studio runs on a personal Claude subscription now: Claude on this PC."""
    return claude.CONNECTION.get("mode") in PERSONAL


# ---------------------------------------------------------------- the plan's limits, kept

def keep_limits(db):
    """claude.ON_LIMITS for this database: the plan's limits written to the `settings` table as they change, so the
    card has them after a restart and in the app's other processes (status). Written off the event loop."""
    def keep(kept):
        text = json.dumps(kept)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            db.set_setting(LIMITS_SETTING, text)
            return
        loop.create_task(offload(db.set_setting, LIMITS_SETTING, text))
    return keep


def saved_limits(db):
    """The plan's limits as the database last kept them ({} when none)."""
    try:
        found = json.loads(db.setting(LIMITS_SETTING) or "{}")
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in found.items() if isinstance(v, dict)} if isinstance(found, dict) else {}


def load_limits(db):
    """At start: the limits the database kept, put in claude.LIMITS where they are newer than what is there."""
    for window, seen in saved_limits(db).items():
        if (seen.get("seen") or 0) > (claude.LIMITS.get(window) or {}).get("seen", 0):
            claude.LIMITS[window] = seen


def _role(db, user_id):
    with as_everyone():
        row = db.one("SELECT role FROM users WHERE id = ?", (int(user_id),))
    return (row or {}).get("role")


def guard_for(db):
    """claude.GUARD for this database: on a personal subscription, a request of a user who is not an admin may not
    reach Claude. The console's requests and the studio's own work (the queue: no one request's) act for everyone, and
    pass."""
    async def guard():
        acting = ACTING.get()
        if not testing() or acting == EVERYONE:
            return
        if await offload(_role, db, acting) != "admin":
            raise claude.Failed(ADMINS_ONLY)
    return guard


async def status(run_claude=False, db=None):
    """How the connection in use is: {"mode", "online", "detail" (why not, and the fix), "claude_version", "signed_in",
    "key_works" (the API key), "running" (calls answering now), "limit" (the most at once), "testing"}, and for Claude
    on this PC also "account" (the email it is signed in as), "plan" (pro, max ...), "session" and "week" (the plan's
    limits: claude.plan_windows).
    - Claude on this PC: `claude -v` and `claude auth status --json` here (each kept for a while: no call to Claude,
      nothing spent); the limits from the last call that reported them (db: also those another process kept).
    - An API key: the key asked of Anthropic's API (a list of one model: no tokens) and `claude -v` here.
    run_claude: the console's Check, which asks the sign-in again, not from what was kept."""
    connection = dict(claude.CONNECTION)
    found = {"mode": connection["mode"], "online": False, "detail": "", "claude_version": "", "signed_in": None, "key_works": None,
             "running": claude.RUNNING["answering"], "limit": claude.PARALLEL, "testing": TESTING if testing() else ""}
    if connection["mode"] == claude.LOCAL_SIGNIN:
        await _local_status(found, run_claude, db)
    else:
        await _key_status(found, connection)
    return found


async def _local_version(found):
    """found["claude_version"] from `claude -v` here, kept for VERSION_EVERY. False (and found["detail"]) when there is
    no `claude` or it would not run."""
    program = claude.find()
    if not program:
        found["detail"] = claude.NOT_INSTALLED
        return False
    seen = _versions.get(program)
    if seen and time.time() - seen[0] < VERSION_EVERY:
        found["claude_version"] = seen[1]
        return True
    try:
        found["claude_version"] = await version()
    except (claude.Busy, claude.Failed) as error:
        found["detail"] = str(error)
        return False
    _versions[program] = (time.time(), found["claude_version"])
    return True


async def _local_status(found, fresh, db):
    found.update(account="", plan="", **claude.plan_windows(await _limits(db)))
    if not await _local_version(found):
        return
    said = await signin(fresh)
    found.update(signed_in=said["signed_in"], account=said["account"], plan=said["plan"])
    if said["signed_in"] is not True:
        found["detail"] = claude.SIGNED_OUT_HERE if said["signed_in"] is False else \
            "Claude Code did not say whether it is signed in (claude auth status). Press Check again."
    found["online"] = not found["detail"]


async def _limits(db):
    """claude.LIMITS, with any window another process kept in the database since (saved_limits)."""
    kept = dict(claude.LIMITS)
    if db is not None:
        try:
            saved = await offload(saved_limits, db)
        except Exception:   # the card shows what this process saw
            saved = {}
        for window, seen in saved.items():
            if (seen.get("seen") or 0) > (kept.get(window) or {}).get("seen", 0):
                kept[window] = seen
    return kept


async def signin(fresh=False):
    """Who Claude Code here is signed in as, from `claude auth status --json` (it reads its own files: no call to
    Claude), kept for SIGNIN_EVERY: {"signed_in": True | False | None (it did not say), "account": its email, "plan":
    its subscription (pro, max ...)}. Run with no key or token in its environment, as the calls of Claude on this PC
    are, so it says what they would use."""
    program = claude.find()
    seen = _signins.get(program)
    if seen and not fresh and time.time() - seen[0] < SIGNIN_EVERY:
        return seen[1]
    found = {"signed_in": None, "account": "", "plan": ""}
    environment = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and k not in claude.KEY_VARIABLES}
    try:
        process = await asyncio.create_subprocess_exec(
            *claude.RUN_WITH, program, "auth", "status", "--json", stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            output, _ = await asyncio.wait_for(process.communicate(), CHECK_WAIT * 2)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            output = b""
        said = json.loads(output.decode("utf-8", "replace") or "null")
    except (OSError, ValueError):
        said = None
    if isinstance(said, dict):
        logged_in = said.get("loggedIn")
        found["signed_in"] = logged_in if isinstance(logged_in, bool) else None
        if found["signed_in"]:
            found["account"] = str(said.get("email") or "")[:200]
            found["plan"] = str(said.get("subscriptionType") or "")[:40]
    _signins[program] = (time.time(), found)
    return found


async def _key_status(found, connection):
    if not await _local_version(found):
        return
    if not connection["api_key"]:
        found["detail"] = claude.NO_API_KEY
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
    """Claude Code's version, from `claude -v` here, whatever key there is or not, since -v needs none. "" when it
    printed none."""
    ran = await claude._run(["-v"], "", None, CHECK_WAIT * 2, program=claude.LocalProgram())
    words = str(ran.stdout or "").split()
    return words[0][:40] if words else ""


# ---------------------------------------------------------------- signing in and out from the console
#
# The sign-in waiting for its code is a plain process with a thread reading its output, not an asyncio one: the code
# may come in a request served on another event loop than the one that started it.

LOGIN_LINK = re.compile(r"(https://\S+/oauth/authorize\?\S+)\s")   # the link `claude auth login` prints, whole
LOGIN_CODE = re.compile(r"[A-Za-z0-9._~#=+/-]{8,512}")   # what Anthropic's page shows to paste (code#state)
LOGIN_SHOWS = 30    # seconds `claude auth login` may take to print its link
LOGIN_ENDS = 60     # seconds it may take to finish once the code is written
LOGIN_OPEN = 900    # seconds a sign-in may wait for its code before it is stopped
NO_LOGIN = "No sign-in is waiting for a code (it ended, or the studio restarted): press Sign in again."
_login = {}         # the sign-in waiting for its code: {"process", "output" (a list of text), "reader", "link", "started"}
_login_lock = threading.Lock()


def _quiet_environment():
    """This process's environment with no key, token or CLAUDECODE: what `claude` here signs in and out with, as
    signin() asks and the calls of Claude on this PC run."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and k not in claude.KEY_VARIABLES}


def _read_all(process, output):
    while True:
        piece = process.stdout.read1(4096) if hasattr(process.stdout, "read1") else process.stdout.read(1)
        if not piece:
            return
        output.append(piece.decode("utf-8", "replace"))


def _cancel():
    with _login_lock:
        found = dict(_login)
        _login.clear()
    process = found.get("process")
    if process is not None and process.poll() is None:
        process.kill()
        process.wait(5)
    if found.get("reader") is not None:
        found["reader"].join(5)


async def login_cancel():
    """Stops the sign-in waiting for its code, if there is one."""
    await asyncio.to_thread(_cancel)


def _last_words(output):
    """The last line `claude auth login` printed that is not its link or its prompt for the code: why it failed."""
    lines = [line.strip() for line in "".join(output).splitlines()]
    lines = [line for line in lines if line and not line.startswith(("Paste code", "If the browser", "Opening browser"))]
    return lines[-1][:300] if lines else ""


def _start():
    _cancel()
    program = claude.find()
    if not program:
        raise claude.Failed(claude.NOT_INSTALLED)
    environment = _quiet_environment()
    environment["BROWSER"] = "none"   # the link goes to the console, not to a browser on this PC
    try:
        process = subprocess.Popen([*claude.RUN_WITH, program, "auth", "login", "--claudeai"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as error:
        raise claude.Failed("Claude Code can't be started ({}). {}".format(error, claude.NOT_INSTALLED))
    output = []
    reader = threading.Thread(target=_read_all, args=(process, output), daemon=True)
    reader.start()
    with _login_lock:
        _login.update(process=process, output=output, reader=reader, started=time.time())
    waited = 0.0
    while waited < LOGIN_SHOWS:
        found = LOGIN_LINK.search("".join(output))
        if found:
            with _login_lock:
                _login["link"] = found.group(1)
            timer = threading.Timer(LOGIN_OPEN, _stop_if, (process,))
            timer.daemon = True   # never keeps the studio from stopping
            timer.start()
            return {"link": found.group(1)}
        if not reader.is_alive():
            break
        time.sleep(0.1)
        waited += 0.1
    said = _last_words(output)
    _cancel()
    raise claude.Failed("Claude Code did not give a sign-in link{}.".format(" ({})".format(said) if said else ""))


async def login_start():
    """Starts `claude auth login` here (a Claude subscription: --claudeai) and returns {"link"}: the page on claude.com
    to sign in on, which then shows a code for login_code. A sign-in already waiting is stopped first."""
    return await asyncio.to_thread(_start)


def _stop_if(process):
    """LOGIN_OPEN later: the sign-in is stopped if it is the same one and still waits."""
    if _login.get("process") is process:
        _cancel()


def login_waiting():
    """The sign-in waiting for its code here, {"link"}, or None."""
    process = _login.get("process")
    if process is None or process.poll() is not None or not _login.get("link"):
        return None
    return {"link": _login["link"]}


def _write_code(code):
    with _login_lock:
        process, output, reader = _login.get("process"), _login.get("output"), _login.get("reader")
    if process is None or process.poll() is not None:
        _cancel()
        raise claude.Failed(NO_LOGIN)
    try:
        process.stdin.write((code + "\n").encode("utf-8"))
        process.stdin.flush()
        process.wait(LOGIN_ENDS)
    except (subprocess.TimeoutExpired, OSError):
        pass
    reader.join(5)
    ended = process.poll()
    _cancel()
    return ended, _last_words(output)


async def login_code(code):
    """Writes the code Anthropic's page showed to the waiting `claude auth login`, waits for it to end, and returns
    what Claude Code here is signed in as now (signin, asked again). Raises ValueError for text that can't be a code,
    claude.Failed when no sign-in waits or it did not go through (with what Claude Code said)."""
    code = str(code or "").strip()
    if not LOGIN_CODE.fullmatch(code):
        raise ValueError("Paste the code the claude.com page shows after you sign in, whole.")
    ended, words = await asyncio.to_thread(_write_code, code)
    said = await signin(fresh=True)
    if ended == 0 and said["signed_in"]:
        return said
    raise claude.Failed("The sign-in did not go through{}. Press Sign in to get a new link.".format(
        " ({})".format(words) if words else ""))


async def logout():
    """Signs Claude Code here out (`claude auth logout`) and returns what signin says now. The agent stops working on
    Claude on this PC until someone signs in again."""
    await login_cancel()
    program = claude.find()
    if not program:
        raise claude.Failed(claude.NOT_INSTALLED)

    def run():
        return subprocess.run([*claude.RUN_WITH, program, "auth", "logout"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_quiet_environment(),
                              timeout=CHECK_WAIT * 2, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        ran = await asyncio.to_thread(run)
    except subprocess.TimeoutExpired:
        raise claude.Failed("Claude Code did not sign out in time: press Sign out again.")
    except OSError as error:
        raise claude.Failed("Claude Code can't be started ({}). {}".format(error, claude.NOT_INSTALLED))
    said = await signin(fresh=True)
    if said["signed_in"]:
        raise claude.Failed("Claude Code is still signed in ({}).".format(
            ran.stdout.decode("utf-8", "replace").strip()[:300] or "it said nothing"))
    return said
