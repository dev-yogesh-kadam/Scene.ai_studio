"""What the agent's models were asked and how they did: one row per call (agent.Agent.chat) in `agent_calls`, for the
admin console's Agent section, and the whole exchange (the messages sent and the answer) kept for a week in
storage/agent_calls/<id>.json.gz, to read it again or replay it with another model.

The calls of one turn of the agent (its rounds of tool calls) share a run: `RUN` is set for the turn and every call
in it carries the same one. Who asked is the user the request acts for (db.ACTING). SESSION is the conversation the
calls are for (an Agent tab of a project), for Langfuse. TURN is what the turn is, for Langfuse as well: its name
("Agent turn", "Film run"), its tags (the skills it used) and what else is known of it (the project, the skills).

Each call is also handed to Langfuse when one is set in the console (langfuse_trace.py).
"""

import contextvars
import gzip
import json
import time
import uuid
from pathlib import Path

from .db import ACTING, EVERYONE

RUN = contextvars.ContextVar("agent_run", default="")
SESSION = contextvars.ContextVar("agent_session", default="")
TURN = contextvars.ContextVar("agent_turn", default=None)   # {"name", "tags", "metadata"} while the agent works on a turn
KEEP_CALLS = 30 * 86400       # the rows: what was asked of which model, how long it took, what it cost
KEEP_EXCHANGES = 7 * 86400    # the words themselves, which can be long (a skill) and are the users' own


def new_run():
    """Start a run for the calls that follow in this task (one turn of the agent). Returns the token to end it."""
    return RUN.set(uuid.uuid4().hex[:12])


def mark():
    """What a job queued now keeps of the turn it belongs to, so its render joins that turn's trace in Langfuse later:
    {"run", "name"}. A job queued by the agent is part of its turn; any other is a "Render" of its own."""
    turn = TURN.get() or {}
    return {"run": RUN.get() or uuid.uuid4().hex[:12], "name": turn.get("name") or "Render"}


class Recorder:
    def __init__(self, db, folder):
        self.db, self.folder = db, Path(folder)
        self.langfuse = None   # sends each call to Langfuse as well (langfuse_trace.Sender; main.py sets it)

    def record(self, purpose, model, asked, started, messages, answer_format, content=None, usage=None, error=None, tool=None):
        acting = ACTING.get()
        usage = usage or {}
        user_id = int(acting) if acting not in (EVERYONE, None) and str(acting).isdigit() else None
        ended = time.time()
        call_id = self.db.run(
            "INSERT INTO agent_calls (run, user_id, purpose, model, asked, started, seconds, prompt_tokens, cached_tokens, "
            "answer_tokens, tool, error, chars) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (RUN.get(), user_id, purpose, model or "", asked or "", started, round(ended - started, 3),
             int(usage.get("prompt") or 0), int(usage.get("cached") or 0), int(usage.get("answer") or 0), str(tool or "")[:60], str(error or "")[:500],
             sum(len(str(m.get("content") or "")) for m in messages)))
        shown = [{k: (len(v) if k == "images" else v) for k, v in m.items()} for m in messages]   # a picture's size, not itself
        if self.langfuse is not None:
            try:
                self.langfuse.add(purpose, model, asked, started, ended, shown, content, usage, error, tool,
                                  RUN.get(), SESSION.get(), user_id, TURN.get())
            except Exception as problem:   # Langfuse is a help: the call is written down here all the same
                print("The agent's call could not be readied for Langfuse: {}".format(problem))
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            kept = {"messages": shown, "format": answer_format, "answer": content}
            (self.folder / "{}.json.gz".format(call_id)).write_bytes(gzip.compress(json.dumps(kept, ensure_ascii=False).encode("utf-8")))
        except (OSError, TypeError, ValueError):
            pass   # the row is what counts; the words are a help
        return call_id

    def exchange(self, call_id):
        try:
            return json.loads(gzip.decompress((self.folder / "{}.json.gz".format(int(call_id))).read_bytes()))
        except (OSError, ValueError, EOFError):
            return None

    def prune(self, now=None, retention_days=0):
        """Forget rows older than a month and words older than a week. With retention_days (config.json, retention.py)
        set, the rows are left to it: it archives them before it deletes them, monthly, so none is deleted unarchived."""
        now = now or time.time()
        if not retention_days or retention_days <= 0:
            self.db.run("DELETE FROM agent_calls WHERE started < ?", (now - KEEP_CALLS,))
        if self.folder.is_dir():
            for path in self.folder.glob("*.json.gz"):
                try:
                    if path.stat().st_mtime < now - KEEP_EXCHANGES:
                        path.unlink()
                except OSError:
                    pass
