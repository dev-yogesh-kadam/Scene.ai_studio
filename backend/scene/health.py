"""Whether the studio is well: its database, its render server (ComfyUI), the agent's model (Claude, through Claude Code
by the connection in use: the API key works, or the LUFI bridge answers and is signed in; claude_connection.py), the
programs it renders and edits with (FFmpeg, HyperFrames for motion graphics), its disk, its backups, its queue and the
sending of the agent's calls to Langfuse (`langfuse`).

`problems` says what is wrong right now; the admin console's Overview lists it. The `Watcher` asks it every minute
while the app runs, so nobody has to have the console open: a problem found twice in a row becomes an alert (the
`alerts` table), which is sent to the admins' phones (phone.py), and is closed, and said so, once it is gone.

A database that does not answer can keep no alert, nor say where the phones are: the Watcher then sends it with the
phone settings it read last, and keeps the alert (already ended) once the database is back.
"""

import asyncio
import json
import shutil
import time

import httpx

from . import backup, claude, claude_connection, langfuse_trace, media, motion, phone, retention, versions
from .db import offload

CHECK_EVERY = 60     # seconds between checks
FIRST_CHECK = 30     # after the app starts: it settles first (the render server may take a moment to be reached)
CONFIRM = 2          # checks in a row a problem must be found in before it is sent: a moment's hiccup is not
DAY = 86400

# What is said when a problem is gone, by its key.
RESOLVED = {
    "database": "The database answers again",
    "render": "The render server answers again",
    "model": "Claude is set up for the agent again",
    "disk": "There is enough disk space again",
    "backup": "The database has been backed up",
    "backup_check": "The newest backup reads back whole",
    "waiting": "No job has been waiting for over an hour",
    "slow": "The slow job is no longer running",
    "failures": "Jobs have stopped failing",
    "langfuse": "Langfuse takes the agent's calls again",
    "ffmpeg": "FFmpeg is there again",
    "motion": "Motion graphics can be rendered again",
}
LANGFUSE_DOWN = 300  # seconds Langfuse may not take the calls before it is a problem (a restart of it takes a minute or two)
DATABASE_WAIT = 10   # seconds the database has to answer `SELECT 1`


def clock(timestamp):
    """A time of day, with the date when it was not today: "14:02", or "9 Oct 14:02"."""
    when = time.localtime(timestamp)
    return time.strftime("%H:%M" if time.strftime("%Y-%m-%d", when) == time.strftime("%Y-%m-%d") else "%d %b %H:%M", when).lstrip("0")


def minutes(seconds):
    return "{} min".format(max(1, round(seconds / 60))) if seconds < 5400 else "{:.1f} h".format(seconds / 3600)


# What each server check last found, so a page of the console does not wait on a server that does not answer (a wait
# of seconds): a check younger than FRESH is used as it is, an older one is shown at once while it is made again behind.
FRESH = 15
_checked = {}    # (app, what) -> (when, found)
_checking = {}   # (app, what) -> the check being made again now


async def remembered(state, what, check, fresh=False):
    """`check()`'s answer, from the last FRESH seconds or made now; `fresh` asks it now whatever was found before."""
    key, now = (id(state), what), time.time()
    hit = _checked.get(key)
    if hit and not fresh:
        if now - hit[0] >= FRESH and key not in _checking:
            _checking[key] = asyncio.ensure_future(_check(key, check))
        return hit[1]
    return await _check(key, check)


async def _check(key, check):
    try:
        found = await check()
        _checked[key] = (time.time(), found)
        return found
    finally:
        _checking.pop(key, None)


def forget(state, what):
    """Drop what a check found, so the next one is made now (after its server was changed)."""
    _checked.pop((id(state), what), None)


def _mark(seen, online):
    """Note whether a server answered, and since when that has been so."""
    if seen["online"] is not online:
        seen.update(online=online, since=time.time())


async def render_server(state, fresh=False):
    """The render server (ComfyUI): whether it answers, since when as far as this app has seen, and what it reports."""
    return dict(await remembered(state, "render:" + state.comfy.url, lambda: _render_server(state), fresh))


async def _render_server(state):
    try:
        stats = await state.comfy.stats()
        state.saw_server(True)
        found = dict(stats, online=True, url=state.comfy.url)
    except (httpx.HTTPError, ValueError):
        state.saw_server(False)
        found = {"online": False, "url": state.comfy.url}
    found["since"] = state.server_seen["since"]   # no earlier than the app's start
    return found


async def database(state):
    """Whether the database answers: {"online", "seconds": how long `SELECT 1` took, "detail": why not}."""
    started = time.time()
    try:
        await asyncio.wait_for(state.db.aone("SELECT 1 AS ok"), DATABASE_WAIT)
        return {"online": True, "seconds": round(time.time() - started, 3), "detail": ""}
    except asyncio.TimeoutError:
        return {"online": False, "seconds": round(time.time() - started, 3),
                "detail": "it did not answer within {} seconds".format(DATABASE_WAIT)}
    except Exception as error:   # whatever the driver or the pool raises: the check says so, it never fails
        said = str(error).splitlines()[0] if str(error) else type(error).__name__
        return {"online": False, "seconds": round(time.time() - started, 3), "detail": langfuse_trace.redact(said)[:300]}


def programs(state):
    """The programs the studio renders and edits with: {"ffmpeg": {"ready", "detail"}, "motion": {"ready", "detail"}}
    (motion: Node.js and HyperFrames, for motion graphics). Sync: it looks at files."""
    try:
        media.ffmpeg_path()
        ffmpeg = {"ready": True, "detail": ""}
    except media.MediaError as error:
        ffmpeg = {"ready": False, "detail": str(error)}
    try:
        hyperframes = motion.status(getattr(state.settings, "node_path", ""))
    except OSError as error:
        hyperframes = {"ready": False, "detail": str(error)}
    return {"ffmpeg": ffmpeg, "motion": hyperframes}


async def checks(state):
    """Every check in one answer, for the console's System section: {"database", "render", "model", "programs",
    "disk": {"folder", "free", "total"}, "backup": {"folder", "last", "check", "restore_test"}, "langfuse", "creative"}."""
    alive = await database(state)
    render, model = await asyncio.gather(render_server(state), model_server(state))
    state.output_dir.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(state.output_dir)
    found = {"database": alive, "render": render, "model": model, "programs": await asyncio.to_thread(programs, state),
             "disk": {"folder": str(state.output_dir), "free": disk.free, "total": disk.total},
             "backup": {"folder": str(state.backup_dir), "last": backup.newest(state.backup_dir), "check": None, "restore_test": None},
             "langfuse": None}
    if alive["online"]:
        found["backup"].update(check=await offload(backup.last_check, state.db), restore_test=await offload(backup.last_restore_test, state.db))
        found["langfuse"] = await langfuse(state)
        found["creative"] = await offload(creative, state)
    return found


def creative(state):
    """The creative director's checks of each plan: the content check's mode and when it last could not run (it fails
    open), and the quality gates (hints to the model, never blocks). Sync: it reads a setting."""
    from . import content_check
    failed = content_check.status()
    return {"content_check": {"mode": content_check.mode(state.db), "failed_at": failed.get("at"), "error": failed.get("error", "")},
            "gates": ["continuity", "shot variety", "a hook for social video", "no words asked of a video model"]}


async def model_server(state, fresh=False):
    """The agent's model: Claude, through Claude Code by the connection in use. claude_connection.status() ({"mode",
    "online", "detail", "claude_version", "signed_in", "key_works", "running", "limit", ...}) with "url": where Claude
    Code runs (the bridge's address, or the claude program here), "models", "limits": its usage as last reported,
    "since"."""
    return dict(await remembered(state, "model", lambda: _model_server(state), fresh))


async def _model_server(state):
    agent = state.agent
    s = agent.services.get("claude")
    if s and s.get("models"):
        found = await claude_connection.status()
    else:
        found = {"mode": claude.CONNECTION.get("mode"), "online": False, "detail": "claude_models is empty in config.json: the agent has no model."}
    _mark(state.model_seen, found["online"])
    where = claude.CONNECTION.get("bridge_url") if found["mode"] == claude.LUFI_BRIDGE else claude.find()
    return dict(found, url=where or "", models=["claude/" + m for m in (s or {}).get("models", [])], limits=agent.claude_limits,
                since=state.model_seen["since"])


async def langfuse(state):
    """How the sending of the agent's calls to Langfuse goes, for the console: {"in_use": whether a Langfuse is set and
    on, "url", "backlog": calls and scores waiting, "keep": the most kept waiting, "sent", "dropped": lost because more
    than keep waited (since the studio started), "refused": what Langfuse would never take, "last_sent", "down_since",
    "last_error", "owns_words": whether the words are kept in Langfuse only (langfuse_owns_words)}."""
    sender = getattr(getattr(state, "traces", None), "langfuse", None)
    if sender is None:
        return {"in_use": False, "url": "", "backlog": 0, "keep": langfuse_trace.KEEP, "sent": 0, "dropped": 0, "refused": 0,
                "last_sent": None, "down_since": None, "last_error": "", "owns_words": False}
    target = await offload(sender.target)
    owns = await offload(langfuse_trace.owns_words, state.db)
    return dict(sender.status(), in_use=target is not None, url=target[0] if target else "", owns_words=bool(owns and target))


def problem(key, level, text, tab):
    """`level`: critical, serious or warning. `tab`: the console's section that deals with it."""
    return {"key": key, "level": level, "text": text, "tab": tab}


async def problems(state, render=None, model=None):
    """What is wrong now with the servers, the disk, the backups and the queue, the worst first. `render` and `model`
    are what render_server and model_server found, when the caller has asked already."""
    db, now = state.db, time.time()
    alive = await database(state)
    if not alive["online"]:   # nothing below can be asked of it
        return [problem("database", "critical", "The database does not answer ({}). Nobody can sign in, and no job is "
                        "started or finished.".format(alive["detail"]), "system")]
    render = render or await render_server(state)
    model = model or await model_server(state)
    found = []
    if not render["online"]:
        found.append(problem("render", "critical", "The render server has not answered at {} since {}. No renders can run.".format(
            render["url"], clock(render["since"])), "system"))
    if model["online"] is False:
        found.append(problem("model", "serious", "{} The agent can't plan and image prompts get no captions.".format(
            model["detail"]), "system"))
    tools = await asyncio.to_thread(programs, state)
    if not tools["ffmpeg"]["ready"]:
        found.append(problem("ffmpeg", "serious", "FFmpeg is missing: {} Edits, posters and the films' cuts fail.".format(
            tools["ffmpeg"]["detail"]), "system"))
    if not tools["motion"]["ready"]:
        found.append(problem("motion", "warning", "Motion graphics can't be rendered: {}".format(tools["motion"]["detail"]), "system"))
    state.output_dir.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(state.output_dir)   # finished work is what fills a disk
    if disk.free < 10 * 1024 ** 3:
        found.append(problem("disk", "serious", "Only {:.1f} GB of disk space is left for storage.".format(disk.free / 1024 ** 3), "system"))
    saved = backup.newest(state.backup_dir)
    if state.settings.backup_keep > 0 and (saved is None or saved < now - 2 * DAY):
        found.append(problem("backup", "serious", "The database has not been backed up for two days. Check the folder {}.".format(
            state.backup_dir), "system"))
    checked = await offload(backup.last_check, db)
    if state.settings.backup_keep > 0 and checked and checked.get("copy") and not checked.get("ok"):
        found.append(problem("backup_check", "serious", "The newest backup, {}, can't be read back: {}".format(
            checked["copy"], checked.get("detail", "")), "system"))
    burst = (await db.aone("SELECT COUNT(*) n FROM jobs WHERE status = 'failed' AND finished > ?", (now - 900,)))["n"]
    if burst >= 3:
        found.append(problem("failures", "serious", "{} jobs failed in the last 15 minutes.".format(burst), "jobs"))
    if not await offload(state.jobs.paused):   # paused, they wait on purpose
        stuck = (await db.aone("SELECT COUNT(*) n FROM jobs WHERE status = 'queued' AND created < ?", (now - 3600,)))["n"]
        if stuck:
            found.append(problem("waiting", "warning", "{} job{} been waiting for over an hour.".format(
                stuck, " has" if stuck == 1 else "s have"), "jobs"))
    tracing = await langfuse(state)
    if tracing["in_use"] and tracing["down_since"] and now - tracing["down_since"] >= LANGFUSE_DOWN:
        found.append(problem("langfuse", "warning", "Langfuse at {} has not taken the agent's calls since {} ({}). {} wait for it; "
                             "at most {:,} are kept, the oldest go first{}. Users' answers are not affected.".format(
                                 tracing["url"], clock(tracing["down_since"]), tracing["last_error"] or "no answer",
                                 tracing["backlog"], tracing["keep"],
                                 "; {:,} lost so far".format(tracing["dropped"]) if tracing["dropped"] else ""), "endpoints"))
    for job in await db.aall("SELECT name, started, est_seconds FROM jobs WHERE status = 'running' AND started IS NOT NULL"):
        if now - job["started"] > max(1800, 3 * (job["est_seconds"] or 0)):
            found.append(problem("slow", "warning", "\"{}\" has been running for {}, far longer than it should.".format(
                job["name"], minutes(now - job["started"])), "jobs"))
            break
    return found


class _Remembered:
    """The phone settings read last, standing in for the database while it does not answer (phone.config reads them)."""

    def __init__(self, phones):
        self.phones = phones

    def setting(self, key, default=None):
        return self.phones if key == "phone_alerts" else default


def maintenance(db):
    """Maintenance mode, while it is on: {text, since}. New jobs are refused (jobs.JobManager.add); the waiting ones
    still run, and the studio shows its message."""
    try:
        found = json.loads(db.setting("maintenance", "") or "{}")
    except ValueError:
        return None
    return found if found.get("since") else None


class Watcher:
    """Checks every minute, opens an alert for a problem found CONFIRM checks in a row, closes one no longer found, and
    sends each change to the admins' phones and the console's open pages."""

    def __init__(self, state):
        self.state = state
        self.streak = {}   # problem key -> checks in a row it was found in
        self.phones = None   # the phone settings as last read (phone_alerts), for when the database does not answer
        self.down = None     # the database's outage being told: {"started", "text", "sent"}
        self.http = httpx.AsyncClient(timeout=10)
        self.moved = 0.0   # when the Claude sessions' old events were last moved to Langfuse (retention.move_events)

    async def step(self, found, now=None):
        """One check's problems in; the messages it sent out, as (level, text)."""
        if any(p["key"] == "database" for p in found):
            return await self.database_down(found[0], now)
        db, now = self.state.db, now or time.time()
        messages = await self.database_back(now)
        self.phones = await db.asetting("phone_alerts", "")
        current = {p["key"]: p for p in found}
        self.streak = {key: self.streak.get(key, 0) + 1 for key in current}
        opened = {a["key"]: a for a in await db.aall("SELECT * FROM alerts WHERE ended IS NULL")}
        for key, p in current.items():
            if key in opened:
                await db.arun("UPDATE alerts SET text = ? WHERE id = ?", (p["text"], opened[key]["id"]))   # its numbers move on
            elif self.streak[key] >= CONFIRM:
                await db.arun("INSERT INTO alerts (key, level, text, tab, started) VALUES (?, ?, ?, ?, ?)",
                       (key, p["level"], p["text"], p["tab"], now))
                messages.append((p["level"], p["text"]))
        for key, a in opened.items():
            if key not in current:
                await db.arun("UPDATE alerts SET ended = ? WHERE id = ?", (now, a["id"]))
                messages.append(("resolved", "{} (after {}).".format(RESOLVED.get(key, "Resolved: " + a["text"]), minutes(now - a["started"]))))
        for level, text in messages:
            await phone.send(self.http, db, level, text)
        if messages:
            self.state.hub.tell({"alerts": len(await db.aall("SELECT id FROM alerts WHERE ended IS NULL")),
                                 "news": [{"level": level, "text": text} for level, text in messages]})
        return messages

    async def database_down(self, p, now=None):
        """The database does not answer: nothing can be kept in it, so the alert is held here and sent with the phone
        settings read last, once it was found CONFIRM checks in a row."""
        now = now or time.time()
        self.streak = {"database": self.streak.get("database", 0) + 1}
        if self.down is None:
            self.down = {"started": now, "text": p["text"], "sent": False}
            print(p["text"])
        if self.down["sent"] or self.streak["database"] < CONFIRM:
            return []
        self.down["sent"] = True
        if self.phones is not None:
            await phone.send(self.http, _Remembered(self.phones), p["level"], p["text"])
        return [(p["level"], p["text"])]

    async def database_back(self, now):
        """The database answers again after it did not: its alert is kept (started and ended), and the phones told."""
        down, self.down = self.down, None
        if not down or not down["sent"]:
            return []
        db = self.state.db
        try:
            await db.arun("INSERT INTO alerts (key, level, text, tab, started, ended) VALUES (?, ?, ?, ?, ?, ?)",
                          ("database", "critical", down["text"], "system", down["started"], now))
        except Exception as error:   # the alert is a record: its loss must not stop the checks
            print("The database's outage could not be kept as an alert: {}".format(error))
        return [("resolved", "{} (after {}).".format(RESOLVED["database"], minutes(now - down["started"])))]

    async def workflows(self, found):
        """Note what the render PC changed in the workflow files, and fetch its node list again when it answers and the
        one in hand is old: the console's Workflows section compares the workflows with it."""
        await offload(versions.look, self.state)
        await offload(self.state.traces.prune, None, getattr(self.state.settings, "retention_days", 0))
        if time.time() - self.moved >= retention.MOVE_EVERY and getattr(self.state.traces, "langfuse", None) is not None:
            self.moved = time.time()
            try:
                moved = await asyncio.to_thread(retention.move_events, self.state.db, self.state.traces.langfuse)
                if moved:
                    print("{:,} old event(s) of the Claude sessions moved to Langfuse (langfuse_owns_words).".format(moved))
            except (httpx.HTTPError, OSError) as error:   # Langfuse down: they stay whole, and go the next time
                print("The Claude sessions' old events were not moved to Langfuse: {}".format(error))
        checked = await offload(backup.last_check, self.state.db)
        if self.state.settings.backup_keep > 0 and (not checked or checked["when"] < time.time() - DAY):   # once a day
            await asyncio.to_thread(backup.check, self.state.db, self.state.backup_dir)
        catalog = self.state.catalog
        saved = catalog.nodes_saved()
        if not any(p["key"] == "render" for p in found) and (saved is None or time.time() - saved > versions.NODES_STALE):
            try:
                await catalog.refresh_nodes()
            except (httpx.HTTPError, ValueError, OSError):
                pass

    async def run_forever(self):
        await asyncio.sleep(FIRST_CHECK)
        try:
            while True:
                try:
                    alive = await database(self.state)
                    if alive["online"]:
                        found = await problems(self.state, await render_server(self.state, fresh=True),   # asked now: alerts
                                               await model_server(self.state, fresh=True))
                    else:
                        found = await problems(self.state)   # the database's problem alone
                    await self.step(found)
                    if alive["online"]:
                        await self.workflows(found)
                except Exception as error:   # a check that fails must not stop the next one
                    print("The health check failed: {}".format(error))
                await asyncio.sleep(CHECK_EVERY)
        finally:
            await self.http.aclose()
