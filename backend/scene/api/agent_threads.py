"""An agent tab's conversation with Claude: its thread (the Claude Code session it goes on in, kept in the run's
state), the session's row and story (sessions.py), compacting it, and forgetting it when the tab is deleted. Moved out
of api/workspace.py as it was; workspace imports these names back, so `workspace._thread` and the rest still work."""

import asyncio
import hashlib
import threading

from fastapi import HTTPException

from .. import agent, claude, runs, sessions
from ..db import as_everyone, offload


def _said(reply):
    return hashlib.sha1(str(reply or "").encode("utf-8")).hexdigest()[:16]


def _thread_run(body):
    run = str(body.get("run") or "main")
    return run if runs.RUN.match(run) else None


def _hosted_claude(state):
    return (getattr(state.agent, "services", None) or {}).get("claude")


def _thread(state, user, project, body, model, system):
    """The thread of this conversation with Claude ({"id", "sent", "seen", "full", "system", "last", "size"}, see
    Agent.chat), or None for a model that does not keep one. A conversation is its run's (a tab of the agent panel),
    with one thread in each project whatever the Claude model, kept in the run's state so it goes on across days and
    restarts of the studio. A change of Claude model, or of the system prompt (a long skill came or went), goes on in
    the same session. Turns Claude's session did not answer are in "missed": they go to the session with the next
    message. It starts again (no session id) only when the
    conversation the browser sent does not hold the reply the thread gave last: a new chat, or one cleared. A session
    that grows near its context window is compacted, not let go (sessions.COMPACT)."""
    run = _thread_run(body)
    if not run or not state.agent.keeps_threads(model):
        return None
    history = [t for t in body.get("history") or [] if isinstance(t, dict)] if isinstance(body.get("history"), list) else []
    signature = hashlib.sha1(system.encode("utf-8")).hexdigest()[:16]
    thread = runs.kept_thread(state.db, user["id"], run, project)
    said = [_said(turn.get("reply")) for turn in history]
    missed = []
    if thread and thread.get("id") and thread.get("last") in said:
        missed = history[len(said) - said[::-1].index(thread["last"]):]   # the turns after Claude's last reply
    else:
        thread = {"id": None, "sent": 1, "seen": {}, "full": "", "last": None}
    thread.update(system=signature, missed=missed)
    thread["key"] = "{}:{}:{}".format(user["id"], run, project or 0)   # its live session (claude.converse)
    return thread


def _keep_thread(state, user, project, body, model, thread, reply):
    """Remember the thread once its message is answered: the next one goes on with it while the conversation holds
    `reply`. When Claude did not give this answer (another model stood in for it), the thread stays as it was: the
    session does not hold this turn, and the next message sends it along as missed."""
    if thread.get("stood_in"):
        return
    kept = {k: v for k, v in thread.items() if k not in THREAD_NOT_KEPT}   # the whole message is made anew each time
    kept["last"] = _said(reply)
    if thread.get("skills"):   # a skill sent to a session that was new in this message: that session is the thread's now
        kept["skills"] = {k: [v[0] or thread.get("id"), v[1]] for k, v in thread["skills"].items()}
    runs.keep_thread(state.db, user["id"], _thread_run(body), project, kept)


THREAD_NOT_KEPT = ("full", "stood_in", "key", "record", "row", "missed")


def _skill_sent(thread, skill_id):
    """Whether this conversation's Claude session holds the skill already: read_skill sent it whole to this session,
    and the session has not been compacted since (a summary keeps no skill word for word)."""
    if not thread or not thread.get("id"):
        return False
    return (thread.get("skills") or {}).get(skill_id) == [thread["id"], thread.get("compacted") or 0]


def _skill_sending(thread, skill_id):
    """Note in the thread that read_skill sends the skill to its session. A new session has no id yet: _keep_thread
    fills it in."""
    if thread is not None:
        thread.setdefault("skills", {})[skill_id] = [thread.get("id"), thread.get("compacted") or 0]


def _session_of(state, user, project, body, model, thread):
    """The tab's session row (sessions.py), and the thread made to tell it what happens: thread["record"]."""
    hosted = _hosted_claude(state) or {}
    row = sessions.open_row(state.db, user["id"], project, _thread_run(body), model, hosted.get("window"))
    db, row_id = state.db, row["id"]
    waiting, writing = [], threading.Lock()   # the events not written yet, in the order they happened

    def write_waiting():
        with writing:   # one writer at a time, oldest first: the story stays in order
            while waiting:
                kind, text, data = waiting[0]
                sessions.record(db, row_id, kind, text, data)
                if kind == "compact":
                    sessions.update(db, row_id, compacts=1, context_tokens=(data or {}).get("post_tokens"))
                waiting.pop(0)

    def record(kind, text="", data=None):
        """Keep an event. Called on the event loop (Claude's stream, claude.py) it is written on the database's threads,
        never waiting there; called on a thread it is written at once, after every event that came before it."""
        waiting.append((kind, text, data))
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return write_waiting()
        asyncio.ensure_future(offload(write_waiting))
    thread.update(record=record, row=row_id)
    return row


def _missed_text(missed):
    """The turns another model answered while the session was away, as the next message carries them."""
    turns = agent.past_turns(missed)
    if not turns:
        return ""
    return ("While you were away, another model answered these turns of this conversation. They are not in your "
            "session; read them as part of it:\n" + "\n".join("[{}] {}".format(t["role"], t["content"]) for t in turns))


def row_model(state, user, project, run):
    """The Claude model a tab's session last used ("" when it has none yet)."""
    with as_everyone():
        row = state.db.one("SELECT model FROM claude_sessions WHERE user_id = ? AND run = ? AND project_id IS NOT DISTINCT FROM NULLIF(?, 0)", (user["id"], run, int(project or 0)))
    return row["model"] if row else ""


async def compact(state, user, body, project):
    """Compact the tab's Claude session now (POST /api/agent/session/compact): {"context"} as a plan gives it."""
    run, hosted = _thread_run(body), _hosted_claude(state)
    thread = await offload(runs.kept_thread, state.db, user["id"], run, project) if run else None
    if not hosted or not thread or not thread.get("id"):
        raise HTTPException(400, "This conversation has no Claude session to compact yet.")
    thread["key"] = "{}:{}:{}".format(user["id"], run, project or 0)
    row = await offload(_session_of, state, user, project, body, await offload(row_model, state, user, project, run), thread)
    thread["record"]("note", "Compact asked by the user, at {}% full".format(
        round(100 * sessions.fullness(thread.get("size") or 0, hosted["window"]))))
    try:
        await claude.compact(hosted, thread)
    except claude.Busy as error:
        raise HTTPException(429, str(error))
    except claude.Lost:
        raise HTTPException(400, "This conversation's Claude session is gone: the next message starts a new one.")
    except claude.Failed as error:
        thread["record"]("error", str(error))
        raise HTTPException(502, str(error))
    await offload(runs.keep_thread, state.db, user["id"], run, project, {k: v for k, v in thread.items() if k not in THREAD_NOT_KEPT})
    await offload(sessions.update, state.db, row["id"], context_tokens=thread.get("size") or 0)
    return {"context": sessions.context(thread.get("size") or 0, hosted["window"])}


async def forget_sessions(state, user, run):
    """An agent tab deleted (DELETE /api/boards/agent-...): its live Claude programs closed, its threads forgotten,
    and its sessions marked deleted. Their story stays, for admins."""
    await claude.close_all("{}:{}:".format(user["id"], run))
    hosted = _hosted_claude(state)
    for thread in await offload(runs.threads_of, state.db, user["id"], run):
        await asyncio.to_thread(claude.forget, hosted, thread.get("id"))
    await offload(runs.delete, state.db, user["id"], run, runs.THREADS, trusted=True)
    with as_everyone():
        rows = await state.db.aall("SELECT id FROM claude_sessions WHERE user_id = ? AND run = ?", (user["id"], run))
    for row in rows:
        await offload(sessions.record, state.db, row["id"], "note", "The tab was deleted")
        await offload(sessions.update, state.db, row["id"], status="deleted")
