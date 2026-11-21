"""The conversation of each agent tab (migration 0010): a row in `conversations` (its own keys: direction, folded,
workflows) and one row per turn in `conversation_messages`. The pages still read and write it as the JSON board
"agent-<tab>" ({"runs": [...turns], "direction", ...}) through /api/boards (api/workspace.py); this builds that JSON
from the rows and keeps it in them. Sync (it queries): called through db.offload from async code."""

import json
import threading
import time

# The same tab as its board was found: by the user, the project (0 or None for all work, in no project) and the tab id.
WHERE = "user_id = ? AND project_id IS NOT DISTINCT FROM NULLIF(?, 0) AND tab = ?"

# One write of a conversation at a time in this process. write() is one statement, and its DELETE sees the turns as
# they were when it began: a second save of the same tab that waited for the first (two windows, the phone and the
# studio) would not see the first one's turns and keep both, the conversation twice over. More than one process
# would need it in the database too: the conversation's row locked first, in a transaction of its own.
_writing, _locks = {}, threading.Lock()


def _one_at_a_time(user_id, project_id, tab):
    key = (int(user_id), int(project_id or 0), str(tab))
    with _locks:
        return _writing.setdefault(key, threading.Lock())


def read(db, user_id, project_id, tab):
    """The conversation as its board's JSON (a dict), or None when the tab has none yet."""
    row = db.one("SELECT id, meta, has_runs FROM conversations WHERE " + WHERE, (user_id, project_id or 0, tab))
    if row is None:
        return None
    data = json.loads(row["meta"] or "{}")
    if row["has_runs"]:
        data["runs"] = [json.loads(m["data"]) for m in db.all(
            "SELECT data FROM conversation_messages WHERE conversation_id = ? ORDER BY position", (row["id"],))]
    return data


def write(db, user_id, project_id, tab, data):
    """Keep the conversation the page sent (its whole JSON), in one statement: its own keys, and its turns in place of
    the ones before. A page reading at the same moment sees the one before or this one, never half of each."""
    with _one_at_a_time(user_id, project_id, tab):
        _write(db, user_id, project_id, tab, data)


def _write(db, user_id, project_id, tab, data):
    runs = data.get("runs")
    has_runs = isinstance(runs, list)
    meta = {k: v for k, v in data.items() if k != "runs"} if has_runs else data
    db.run("""
        WITH kept AS (
            INSERT INTO conversations (user_id, project_id, tab, meta, has_runs, updated)
            VALUES (?, NULLIF(?, 0), ?, CAST(? AS jsonb), ?, to_timestamp(?))
            ON CONFLICT (user_id, project_id, tab)
            DO UPDATE SET meta = excluded.meta, has_runs = excluded.has_runs, updated = excluded.updated
            RETURNING id, user_id),
        gone AS (DELETE FROM conversation_messages WHERE conversation_id = (SELECT id FROM kept))
        INSERT INTO conversation_messages (conversation_id, user_id, position, data)
        SELECT kept.id, kept.user_id, turn.place - 1, turn.value
        FROM kept, jsonb_array_elements(CAST(? AS jsonb)) WITH ORDINALITY AS turn(value, place)""",
           (user_id, project_id or 0, tab, json.dumps(meta), has_runs, time.time(),
            json.dumps(runs if has_runs else [])))


def delete(db, user_id, project_id, tab):
    """Forget a tab's conversation (its turns go with it)."""
    with _one_at_a_time(user_id, project_id, tab):
        db.run("DELETE FROM conversations WHERE " + WHERE, (user_id, project_id or 0, tab))


def waiting(db, user_id, most=30):
    """The newest turn waiting for approval ("proposed") of each conversation that has one, newest conversation first:
    [{"project_id", "tab", "run", "updated"}]."""
    rows = db.all(
        "SELECT DISTINCT ON (c.id) c.id, c.project_id, c.tab, c.updated, m.data FROM conversation_messages m "
        "JOIN conversations c ON c.id = m.conversation_id WHERE m.user_id = ? AND m.state = 'proposed' "
        "ORDER BY c.id, m.position DESC", (user_id,))
    rows.sort(key=lambda r: r["updated"], reverse=True)
    return [{"project_id": r["project_id"], "tab": r["tab"], "run": json.loads(r["data"]), "updated": r["updated"]}
            for r in rows[:most]]
