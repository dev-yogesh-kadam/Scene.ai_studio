"""How long the agent's records stay in the database (`retention_days`, 0 = for good, the default): the Claude sessions'
events (claude_events) and the calls to the agent's models (agent_calls) grow with every message. Once a month the
ones older than that are written to compressed files in the backup folder, archive/<table>_<YYYY-MM>.jsonl.gz (one JSON
object per row, the month of its time), and only then deleted. The audit log is never touched: it is sealed (audit.py).

A crash between writing a month file and deleting its rows archives those rows again the next time: `read` gives
each row once (by its id), so an archive is never read with a row twice.

`move_events` is the other half of who keeps what (docs/observability.md): with the setting langfuse_owns_words on
(off by default), the events older than EVENTS_KEPT days are sent to Langfuse and, once it has taken them, kept here
as short rows (their kind, time, first SHORT characters and numbers, and where they are in Langfuse; `moved` says
when). Nothing is deleted by it, and while the setting is off it does nothing.

Sync: run on a database thread (backup.run_forever does, once a day; it archives at most once a month; health.Watcher
moves events at most every MOVE_EVERY seconds)."""

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import langfuse_trace
from .db import as_everyone

TABLES = {"claude_events": "at", "agent_calls": "started"}   # table: its time column
EVERY = 30 * 86400   # an archive at most this often
BATCH = 5000
EVENTS_KEPT = 30     # days an event of a Claude session stays whole here once Langfuse owns the words
SHORT = 300          # characters of a moved event's text kept here
MOVE_BATCH = 200     # events sent to Langfuse in one go
MOVE_MOST = 5000     # events moved in one run at most (the rest the next time)
MOVE_EVERY = 3600    # seconds between two runs (health.Watcher)


def due(db):
    return time.time() - float(db.setting("retention_last", "0") or 0) >= EVERY


def archive(db, folder, days, now=None):
    """Move the rows older than `days` days into the month files. Returns {table: rows archived}."""
    now = now or time.time()
    cutoff = now - days * 86400
    done = {}
    target = Path(folder) / "archive"
    target.mkdir(parents=True, exist_ok=True)
    with as_everyone():
        for table, column in TABLES.items():
            done[table] = 0
            while True:
                rows = db.all("SELECT * FROM {} WHERE {} < ? ORDER BY id LIMIT ?".format(table, column), (cutoff, BATCH))
                if not rows:
                    break
                months = {}
                for row in rows:
                    month = datetime.fromtimestamp(row[column], timezone.utc).strftime("%Y-%m")
                    months.setdefault(month, []).append(row)
                for month, kept in months.items():
                    # Appended: a month archived in two runs is two gzip members, which gzip reads as one file.
                    with gzip.open(target / "{}_{}.jsonl.gz".format(table, month), "at", encoding="utf-8") as f:
                        for row in kept:
                            f.write(json.dumps(row, default=str) + "\n")
                db.run("DELETE FROM {} WHERE id = ANY(?)".format(table), ([r["id"] for r in rows],))
                done[table] += len(rows)
        db.set_setting("retention_last", str(now))
    return done


def read(path):
    """The rows of one archive file (for looking at them again), each once: a row archived twice (a crash between the
    file and the delete) is given the first time it was written."""
    rows, seen = [], set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("id") is not None:
                if row["id"] in seen:
                    continue
                seen.add(row["id"])
            rows.append(row)
    return rows


def _short(row, trace, span):
    """What stays here of a moved event: (text, data), its first SHORT characters and the numbers of its data (the
    steps of an answer, the tokens of a compaction), with where the whole of it is in Langfuse."""
    text = row["text"] or ""
    if len(text) > SHORT:
        text = text[:SHORT] + "\n[… {:,} more characters in Langfuse]".format(len(text) - SHORT)
    try:
        data = json.loads(row["data"]) if row["data"] else {}
    except ValueError:
        data = {}
    kept = {k: v for k, v in data.items() if isinstance(v, (int, float, bool))} if isinstance(data, dict) else {}
    kept["langfuse"] = {"trace": trace, "observation": span}
    return text, json.dumps(kept)


def move_events(db, sender, now=None, days=EVENTS_KEPT, http=None, most=MOVE_MOST):
    """With langfuse_owns_words on, a Langfuse in use and langfuse_words on: send the events older than `days` days that
    are still whole to Langfuse, and once it has taken each batch keep them here as short rows. Returns how many were
    moved (0 when any of that is not so). A Langfuse that does not answer stops it with nothing changed (httpx errors
    are raised): those events stay whole and go the next time. sender: langfuse_trace.Sender (its user emails)."""
    if not langfuse_trace.owns_words(db) or not sender.words():
        return 0
    target = sender.target()
    if target is None:
        return 0
    cutoff = (now or time.time()) - days * 86400
    moved = 0
    with as_everyone():
        while moved < most:
            rows = db.all("SELECT e.id, e.at, e.kind, e.text, e.data, s.ref, s.user_id, s.run, COALESCE(s.project_id, 0) AS project_id "
                          "FROM claude_events e JOIN claude_sessions s ON s.id = e.session_id "
                          "WHERE e.moved IS NULL AND e.at < ? ORDER BY e.id LIMIT ?", (cutoff, min(MOVE_BATCH, most - moved)))
            if not rows:
                break
            spans = langfuse_trace.event_spans(sender, rows)
            langfuse_trace.post_spans(target, [span for _, span in spans], http)   # raises: nothing below happens
            at = time.time()
            for row, (_, span) in zip(rows, spans):
                text, data = _short(row, span["traceId"], span["spanId"])
                db.run("UPDATE claude_events SET text = ?, data = ?, moved = ? WHERE id = ? AND moved IS NULL", (text, data, at, row["id"]))
            moved += len(rows)
    return moved
