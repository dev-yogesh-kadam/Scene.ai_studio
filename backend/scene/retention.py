"""How long the agent's records stay in the database (`retention_days`, 0 = for good, the default): the Claude sessions'
events (claude_events) and the calls to the agent's models (agent_calls) grow with every message. Once a month the
ones older than that are written to compressed files in the backup folder, archive/<table>_<YYYY-MM>.jsonl.gz (one JSON
object per row, the month of its time), and only then deleted. The audit log is never touched: it is sealed (audit.py).

Sync: run on a database thread (backup.run_forever does, once a day; it archives at most once a month)."""

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .db import as_everyone

TABLES = {"claude_events": "at", "agent_calls": "started"}   # table: its time column
EVERY = 30 * 86400   # an archive at most this often
BATCH = 5000


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
    """The rows of one archive file (for looking at them again)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
