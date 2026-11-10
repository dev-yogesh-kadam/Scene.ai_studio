"""Where the app's seconds and JSON text meet PostgreSQL's timestamptz and JSONB (edge.py)."""

import pytest

from scene.edge import JSON, TIME, Ambiguous, with_times

COLUMNS = {"jobs": {"created": TIME, "finished": TIME, "status": "", "id": "", "user_id": "", "settings": JSON},
           "audit_log": {"created": "", "action": ""},   # sealed entries keep their seconds
           "generations": {"created": TIME, "id": "", "project_id": "", "review": JSON},
           "projects": {"created": TIME, "id": ""},
           "endpoints": {"active": ""},                       # a flag here...
           "claude_sessions": {"active": TIME, "id": ""}}     # ...a time here


@pytest.mark.parametrize("sql, expected", [
    ("INSERT INTO jobs (id, user_id, status, created) VALUES (?, ?, 'queued', ?)",
     "INSERT INTO jobs (id, user_id, status, created) VALUES (?, ?, 'queued', to_timestamp(?))"),
    ("INSERT INTO jobs (id, status, created) VALUES (?, 'done', 0)",
     "INSERT INTO jobs (id, status, created) VALUES (?, 'done', to_timestamp(0))"),
    ("INSERT INTO jobs (id, created) VALUES (?, ?), (?, ?)",
     "INSERT INTO jobs (id, created) VALUES (?, to_timestamp(?)), (?, to_timestamp(?))"),
    ("UPDATE jobs SET status = 'done', finished = ? WHERE id = ?",
     "UPDATE jobs SET status = 'done', finished = to_timestamp(?) WHERE id = ?"),
    ("SELECT * FROM jobs WHERE user_id = ? AND (finished > ? OR status IN ('queued'))",
     "SELECT * FROM jobs WHERE user_id = ? AND (finished > to_timestamp(?) OR status IN ('queued'))"),
    ("SELECT g.* FROM generations g JOIN projects p ON p.id = g.project_id WHERE g.created < ? OR (g.created = ? AND g.id < ?)",
     "SELECT g.* FROM generations g JOIN projects p ON p.id = g.project_id "
     "WHERE g.created < to_timestamp(?) OR (g.created = to_timestamp(?) AND g.id < ?)"),
    ("SELECT * FROM jobs WHERE created BETWEEN ? AND ? AND note = 'created > ?'",
     "SELECT * FROM jobs WHERE created BETWEEN to_timestamp(?) AND to_timestamp(?) AND note = 'created > ?'"),
    ("SELECT * FROM jobs WHERE ? < finished", "SELECT * FROM jobs WHERE to_timestamp(?) < finished"),
    ("UPDATE claude_sessions SET active = ? WHERE id = ?", "UPDATE claude_sessions SET active = to_timestamp(?) WHERE id = ?"),
    ("UPDATE generations SET review = ? WHERE id = ?", "UPDATE generations SET review = NULLIF(?, '')::jsonb WHERE id = ?"),
    ("INSERT INTO jobs (id, settings, created) VALUES (?, ?, ?)",
     "INSERT INTO jobs (id, settings, created) VALUES (?, NULLIF(?, '')::jsonb, to_timestamp(?))"),
    ("UPDATE jobs SET finished = COALESCE(finished, ?) WHERE id = ?",
     "UPDATE jobs SET finished = COALESCE(finished, to_timestamp(?)) WHERE id = ?"),
    ("UPDATE jobs SET status = 'failed', finished = 1, error = ? WHERE id = ?",
     "UPDATE jobs SET status = 'failed', finished = to_timestamp(1), error = ? WHERE id = ?"),
    ("SELECT 1 FROM endpoints WHERE active = ?", "SELECT 1 FROM endpoints WHERE active = ?"),
    ("SELECT 1 FROM endpoints WHERE active = 1", "SELECT 1 FROM endpoints WHERE active = 1"),
    ("SELECT COUNT(*) FROM audit_log WHERE action = ? AND created > ?",
     "SELECT COUNT(*) FROM audit_log WHERE action = ? AND created > ?"),
])
def test_a_value_for_a_time_column_is_turned_into_a_time(sql, expected):
    assert with_times(sql, COLUMNS) == expected


def test_a_name_that_is_a_time_in_one_table_and_not_another_must_be_qualified():
    with pytest.raises(Ambiguous):
        with_times("SELECT * FROM jobs j JOIN audit_log a ON 1 = 1 WHERE created > ?", COLUMNS)
    assert with_times("SELECT * FROM jobs j JOIN audit_log a ON 1 = 1 WHERE j.created > ?", COLUMNS).endswith(
        "j.created > to_timestamp(?)")


def test_seconds_and_json_text_come_back_as_the_app_had_them(database):
    """Read through the app's own connections: a timestamptz as seconds, JSONB as its text, an empty JSONB as ''."""
    user = database.run("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', ?)", (1762700000.25,))
    row = database.one("SELECT created, mfa_recovery FROM users WHERE id = ?", (user,))
    assert row["created"] == 1762700000.25 and row["mfa_recovery"] == "[]"
    database.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                 "VALUES (?, 'w', 'image', 'n', 'f.png', ?, '{}', ?)", (user, '{"b": 1, "a": [1, 2]}', 1762700001))
    item = database.one("SELECT settings, review, created FROM generations")
    assert item["review"] == "" and item["created"] == 1762700001.0
    assert __import__("json").loads(item["settings"]) == {"a": [1, 2], "b": 1}
    assert database.one("SELECT COUNT(*) AS n FROM generations WHERE created > ?", (1762700000,))["n"] == 1
