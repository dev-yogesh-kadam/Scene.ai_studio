"""What is kept of the agent's work, and archived once (docs/observability.md)."""

import gzip
import time

import pytest

from scene import retention
from test_api import register


def test_with_retention_set_the_calls_are_left_to_it_so_none_is_deleted_unarchived(client):
    register(client)
    recorder = client.app.state.traces
    old = recorder.record("caption", "m", None, time.time() - 40 * 86400, [{"role": "user", "content": "x"}], "json", content={})
    recorder.prune(retention_days=90)
    assert client.app.state.db.one("SELECT id FROM agent_calls WHERE id = ?", (old,))
    recorder.prune()   # retention off: a month, as always
    assert not client.app.state.db.one("SELECT id FROM agent_calls WHERE id = ?", (old,))


def test_rows_archived_twice_by_a_crash_are_read_once(database, tmp_path, monkeypatch):
    db = database
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', ?)", (time.time(),))
    old = time.time() - 120 * 86400
    db.run("INSERT INTO agent_calls (run, user_id, started) VALUES ('r', ?, ?)", (user, old))
    real = db.run

    def crash(sql, params=()):
        if sql.startswith("DELETE FROM agent_calls"):
            raise RuntimeError("the power went")
        return real(sql, params)
    monkeypatch.setattr(db, "run", crash)
    with pytest.raises(RuntimeError):
        retention.archive(db, tmp_path, days=90)
    monkeypatch.setattr(db, "run", real)
    assert retention.archive(db, tmp_path, days=90)["agent_calls"] == 1
    path = tmp_path / "archive" / "agent_calls_{}.jsonl.gz".format(time.strftime("%Y-%m", time.gmtime(old)))
    assert len([l for l in gzip.open(path, "rt", encoding="utf-8") if l.strip()]) == 2   # written twice
    assert len(retention.read(path)) == 1                                              # read once
