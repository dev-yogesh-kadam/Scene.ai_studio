"""The Claude sessions of the agent's tabs, kept for good for admins to watch (the console's Sessions page).

Each tab of the agent panel (a run) in a project has one Claude session. It goes on across days, studio restarts and
changes of Claude model; when it grows near its model's context window it is compacted, still the same session.
Here is its row (claude_sessions: whose, which tab, which Claude Code session, how full its context is) and
everything that happened in it (claude_events, in order). Nothing here is ever deleted."""

import json
import time

from . import refs
from .db import as_everyone

TEXT = 200_000   # characters of one event's text kept (a whole message to Claude is long, but not this long)
DATA = 20_000    # characters of one event's data, as JSON
OFFER = 0.8      # how full the context is when the user is offered to compact it now
COMPACT = 0.9    # how full it is when it is compacted on its own

# What an event is: what the user asked, what was sent to Claude (the studio's whole message), what Claude thought and
# wrote, a tool it called and what the tool gave back, its answer, a compaction, a change of model, an error, a note.
KINDS = ("user", "prompt", "thinking", "text", "tool_call", "tool_result", "answer", "compact", "model", "error", "note")


def agent_ref(run):
    """The id an agent tab shows in links: AGT and its run."""
    return refs.AGENT + str(run or "")


def open_row(db, user_id, project_id, run, model, window):
    """The session row of this tab in this project, made the first time. Returns it as a dict."""
    project_id = int(project_id or 0)
    with as_everyone():
        row = db.one("SELECT * FROM claude_sessions WHERE user_id = ? AND run = ? AND project_id IS NOT DISTINCT FROM NULLIF(?, 0)", (user_id, run, project_id))
        if row is None:
            now = time.time()
            db.run("INSERT INTO claude_sessions (ref, user_id, project_id, run, agent, model, context_window, status, started, active) "
                   "VALUES (?, ?, NULLIF(?, 0), ?, ?, ?, ?, 'idle', ?, ?) ON CONFLICT DO NOTHING",   # another request made it first
                   (refs.new(refs.SESSION), user_id, project_id, run, agent_ref(run), model, int(window or 0), now, now))
            row = db.one("SELECT * FROM claude_sessions WHERE user_id = ? AND run = ? AND project_id IS NOT DISTINCT FROM NULLIF(?, 0)", (user_id, run, project_id))
    return row


def record(db, session_id, kind, text="", data=None):
    """Add one event to a session's story."""
    with as_everyone():
        db.run("INSERT INTO claude_events (session_id, at, kind, text, data) VALUES (?, ?, ?, ?, ?)",
               (session_id, time.time(), kind if kind in KINDS else "note", str(text or "")[:TEXT],
                json.dumps(data, ensure_ascii=False, default=str)[:DATA] if data is not None else ""))
        db.run("UPDATE claude_sessions SET active = ? WHERE id = ?", (time.time(), session_id))


def update(db, session_id, **fields):
    """Change a session row's fields: claude_id, model, context_tokens, context_window, title, status; messages=1 and
    compacts=1 add one."""
    sets, params = ["active = ?"], [time.time()]
    for name in ("claude_id", "model", "context_tokens", "context_window", "title", "status"):
        if fields.get(name) is not None:
            sets.append(name + " = ?")
            params.append(fields[name])
    for name in ("messages", "compacts"):
        if fields.get(name):
            sets.append("{0} = {0} + ?".format(name))
            params.append(int(fields[name]))
    with as_everyone():
        db.run("UPDATE claude_sessions SET " + ", ".join(sets) + " WHERE id = ?", (*params, session_id))


def fullness(tokens, window):
    """How full a context is, from 0 to 1 (0 when the window is not known)."""
    return min(1.0, max(0.0, tokens / window)) if window and tokens else 0.0


def context(tokens, window):
    """What the agent panel is told of a session's context after a message: {"tokens", "window", "percent",
    "offer"} (offer: it is past OFFER, so the user may compact it now; at COMPACT it is compacted on its own)."""
    full = fullness(tokens, window)
    return {"tokens": int(tokens or 0), "window": int(window or 0), "percent": round(full * 100), "offer": full >= OFFER}


# ---------------------------------------------------------------- what admins see

def listing(db, q="", status="", limit=200):
    """Every session, the most recently active first, with who and where: for the console's Sessions page. q finds a
    session by its id, its tab's, its Claude session's, a project's id or name, or its user's name or email."""
    where, params = [], []
    if status:
        where.append("s.status = ?")
        params.append(status)
    if q.strip():
        like = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(s.ref = ? OR s.agent = ? OR s.claude_id = ? OR p.ref = ? OR pp.ref = ? OR LOWER(s.title) LIKE ? ESCAPE '\\' "
                     "OR LOWER(u.name) LIKE ? ESCAPE '\\' OR LOWER(u.email) LIKE ? ESCAPE '\\' OR LOWER(p.name) LIKE ? ESCAPE '\\' "
                     "OR LOWER(pp.name) LIKE ? ESCAPE '\\')")
        params += [q.strip()] * 5 + [like] * 5
    with as_everyone():
        return db.all(
            "SELECT s.*, COALESCE(s.project_id, 0) AS project_id, "   # 0 for no project, as the console has always been told
            "u.name AS user_name, u.email AS user_email, p.name AS project_name, p.ref AS project_ref, "
            "pp.name AS parent_name, pp.ref AS parent_ref, "
            "(SELECT COUNT(*) FROM claude_events e WHERE e.session_id = s.id) AS events "
            "FROM claude_sessions s JOIN users u ON u.id = s.user_id LEFT JOIN projects p ON p.id = s.project_id "
            "LEFT JOIN projects pp ON pp.id = p.parent_id" + (" WHERE " + " AND ".join(where) if where else "") +
            " ORDER BY s.active DESC LIMIT ?", (*params, int(limit)))


def one(db, ref):
    with as_everyone():
        return db.one(
            "SELECT s.*, COALESCE(s.project_id, 0) AS project_id, "   # 0 for no project, as the console has always been told
            "u.name AS user_name, u.email AS user_email, p.name AS project_name, p.ref AS project_ref, "
            "pp.name AS parent_name, pp.ref AS parent_ref FROM claude_sessions s JOIN users u ON u.id = s.user_id "
            "LEFT JOIN projects p ON p.id = s.project_id LEFT JOIN projects pp ON pp.id = p.parent_id WHERE s.ref = ?", (ref,))


def events(db, session_id, after=0, limit=500):
    """A session's events after the event `after`, oldest first, at most `limit`."""
    with as_everyone():
        rows = db.all("SELECT id, at, kind, text, data FROM claude_events WHERE session_id = ? AND id > ? ORDER BY id LIMIT ?",
                      (session_id, int(after or 0), int(limit)))
    for row in rows:
        try:
            row["data"] = json.loads(row["data"]) if row["data"] else None
        except ValueError:
            row["data"] = None
    return rows


def title(tab, project, user):
    """What a session is called in Claude Code (and so in VS Code's list of sessions): Studio · tab · project · user."""
    return " · ".join(part for part in ("Studio", str(tab or "Agent").strip()[:40], str(project or "All work").strip()[:60],
                                        str(user or "").strip()[:40]) if part)
