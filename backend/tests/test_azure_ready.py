"""What running on Azure needs of the app: health answers for the platform, JSON logs, connection strings with their
TLS parameters taken whole by every tool, and nothing that needs a superuser."""

import io
import json

import psycopg

from conftest import POSTGRES, empty_postgres
from scene import backup, schema
from scene.db import Database
from scene.logs import JsonLines


def test_liveness_and_readiness(client, monkeypatch):
    assert client.get("/healthz").json() == {"ok": True}
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json() == {"database": True, "storage": True}

    def unreachable():
        raise OSError("the container did not answer")
    monkeypatch.setattr(client.app.state.storage, "ready", unreachable)
    ready = client.get("/readyz")
    assert ready.status_code == 503 and ready.json()["storage"] is False and ready.json()["storage_error"] == "OSError"


def test_each_line_written_becomes_one_json_object():
    out = io.StringIO()
    stream = JsonLines(out, "info")
    stream.write("Scene.ai is running at http://localhost:8080\nThe admin con")
    stream.write("sole is at http://localhost:8090\n")
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [line["message"] for line in lines] == ["Scene.ai is running at http://localhost:8080",
                                                   "The admin console is at http://localhost:8090"]
    assert {"time", "level", "process"} <= set(lines[0]) and lines[0]["level"] == "info"


def test_a_connection_string_with_its_parameters_works_for_the_app_its_copies_and_its_migrations(tmp_path):
    """Azure's PostgreSQL wants sslmode=verify-full&sslrootcert=...: the pool, pg_dump and the migrations take the
    address as it is given (here with parameters this server takes: no TLS on LUFI)."""
    empty_postgres()
    with_parameters = POSTGRES + ("&" if "?" in POSTGRES else "?") + "sslmode=prefer&application_name=scene-test&connect_timeout=10"
    schema.upgrade(with_parameters)   # SQLAlchemy's address keeps them
    db = Database(with_parameters, loop_guard="off")
    assert db.one("SELECT current_setting('application_name') AS name")["name"] == "scene-test"
    target = tmp_path / "copy.dump"
    db.backup(target)   # pg_dump is given the same address
    assert target.stat().st_size > 0
    db.close()


def test_the_migrations_need_no_superuser():
    """The tests' account owns its database and nothing more: every migration ran as it."""
    empty_postgres()
    with psycopg.connect(POSTGRES) as conn:
        assert conn.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0] is False
        assert schema.version_of(conn) == schema.head()
    assert backup  # (the module the copies use is importable without its old SQLite parts)
