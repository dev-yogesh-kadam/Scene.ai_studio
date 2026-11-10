"""A copy's row counts (scene_<date>.counts.json, what the weekly restore test checks a restored copy against) are
counted in the very snapshot pg_dump copies: a row written while the copy is made is in both or in neither, so a
busy studio's restore test does not fail for rows that came a moment late (backup.make, db.Database.backup)."""

import json
import time

import psycopg

from conftest import POSTGRES
from scene import backup
from scene import db as storage


def test_a_row_written_while_the_copy_is_made_does_not_fail_the_restore_test(database, tmp_path, monkeypatch):
    db = database
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', ?)", (time.time(),))
    run = storage.subprocess.run

    def busy(args, **kwargs):
        if "pg_dump" in str(args[0]):   # the studio goes on writing as pg_dump starts
            with psycopg.connect(POSTGRES, autocommit=True) as conn:
                conn.execute("SELECT set_config('app.user_id', 'all', false)")
                conn.execute("INSERT INTO credit_events (user_id, amount, reason, created) VALUES (%s, 5, 'grant', now())", (user,))
        return run(args, **kwargs)
    monkeypatch.setattr(storage.subprocess, "run", busy)
    made = backup.make(db, tmp_path / "copies", keep=2)
    counts = json.loads(made.with_name(made.stem + ".counts.json").read_text(encoding="utf-8"))
    assert counts["users"] == 1
    monkeypatch.setattr(storage.subprocess, "run", run)
    found = backup.restore_test(db, tmp_path / "copies", POSTGRES)
    assert found["ok"], found
    assert db.one("SELECT COUNT(*) AS n FROM credit_events")["n"] == 1   # the row is kept, just not in this copy
