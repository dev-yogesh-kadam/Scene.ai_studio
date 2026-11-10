"""Growth, secrets and backups: the agent's old records archived (retention.py), settings and secrets from the
environment (config.py), backups that can be switched off part by part, and the weekly restore test (backup.py)."""

import json
import time

from conftest import POSTGRES, empty_postgres
from scene import backup, retention
from scene.config import load_settings


def test_old_agent_records_go_to_monthly_archives_and_the_audit_log_stays(database, tmp_path):
    db = database
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', ?)", (time.time(),))
    session = db.run("INSERT INTO claude_sessions (ref, user_id, run, started, active) VALUES ('SES1', ?, 'r', ?, ?)",
                     (user, time.time(), time.time()))
    old, new = time.time() - 120 * 86400, time.time() - 86400
    for at, text in ((old, "long ago"), (old + 60, "long ago too"), (new, "yesterday")):
        db.run("INSERT INTO claude_events (session_id, at, kind, text) VALUES (?, ?, 'text', ?)", (session, at, text))
    db.run("INSERT INTO agent_calls (run, user_id, started) VALUES ('r', ?, ?)", (user, old))
    db.run("INSERT INTO audit_log (action, created) VALUES ('Signed in', ?)", (old,))
    assert retention.due(db)
    assert retention.archive(db, tmp_path, days=90) == {"claude_events": 2, "agent_calls": 1}
    assert [r["text"] for r in db.all("SELECT text FROM claude_events")] == ["yesterday"]
    files = sorted(p.name for p in (tmp_path / "archive").iterdir())
    month = time.strftime("%Y-%m", time.gmtime(old))
    assert "claude_events_{}.jsonl.gz".format(month) in files and "agent_calls_{}.jsonl.gz".format(month) in files
    kept = retention.read(tmp_path / "archive" / "claude_events_{}.jsonl.gz".format(month))
    assert sorted(r["text"] for r in kept) == ["long ago", "long ago too"]
    assert db.one("SELECT COUNT(*) AS n FROM audit_log")["n"] == 1     # never touched
    assert not retention.due(db)                                       # once a month


def test_settings_and_secrets_come_from_the_environment_and_config_json_ones_are_warned_of(tmp_path, monkeypatch):
    for name in ("SCENE_DATABASE_URL", "SCENE_ENV_FILE", "SCENE_PORT"):
        monkeypatch.delenv(name, raising=False)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"database_url": "postgresql://app:in-the-file@db/scene", "port": 8081}), encoding="utf-8")
    settings = load_settings(config)
    assert settings.database_url.endswith("in-the-file@db/scene") and settings.port == 8081
    assert len(settings.warnings) == 1 and "SCENE_DATABASE_URL" in settings.warnings[0]
    (tmp_path / "scene.env").write_text("# this machine's secrets\nSCENE_DATABASE_URL=postgresql://app:from-env-file@db/scene\n"
                                        "SCENE_PORT=9090\n", encoding="utf-8")
    settings = load_settings(config)
    assert settings.database_url.endswith("from-env-file@db/scene") and settings.port == 9090 and settings.warnings == []
    monkeypatch.setenv("SCENE_PORT", "7070")   # the real environment wins over the file
    assert load_settings(config).port == 7070


def test_backups_can_be_switched_off_part_by_part(tmp_path):
    from fastapi.testclient import TestClient
    from conftest import ROOT, built
    from scene.config import Settings
    from scene.main import create_app
    empty_postgres()
    settings = Settings(database_url=POSTGRES, hold_queue_offline=False, comfy_url="http://127.0.0.1:9", claude_models="off",
                        storage_dir=str(tmp_path / "storage"), first_account_local=False, workflows_dir=str(ROOT / "workflows"),
                        web_dist_dir=str(built(tmp_path / "web")), backup_database=False, backup_files=False)
    with TestClient(create_app(settings)) as client:
        time.sleep(0.3)
        folder = client.app.state.backup_dir
        assert not list(folder.glob("scene_*.dump")) and not (folder / "files").exists()


def test_the_newest_copy_restores_and_its_rows_are_counted(client, tmp_path):
    from test_api import console, register
    register(client)
    db = client.app.state.db
    folder = client.app.state.backup_dir
    made = backup.make(db, folder, keep=3)
    assert made.with_name(made.stem + ".counts.json").is_file()
    found = backup.restore_test(db, folder, POSTGRES)   # the tests' account may make databases
    assert found["ok"] and "every count as when the copy was made" in found["detail"] and found["tables"] > 20
    shown = console(client).get("/api/admin/system").json()
    assert shown["restore_test"]["ok"] and shown["retention_days"] == 0
    assert {"name", "rows", "bytes"} <= set(shown["tables"][0]) and any(t["name"] == "generations" for t in shown["tables"])
