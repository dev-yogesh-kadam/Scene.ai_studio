"""The database's shape is the migrations' (backend/migrations/): the app refuses a database that is not at the newest,
every migration goes down and up again, and what the code assumes of the tables matches them."""

import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from conftest import POSTGRES, empty_postgres
from scene import db as storage, schema


@pytest.fixture
def scratch():
    """A database of the test's own beside the test database, empty, dropped after (the test account has CREATEDB)."""
    name = "scene_tmp_" + secrets.token_hex(6)
    parts = urlsplit(POSTGRES)
    with psycopg.connect(POSTGRES, autocommit=True) as conn:
        conn.execute('CREATE DATABASE "{}"'.format(name))
    yield urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))
    drop(name)


def drop(name):
    """Drop a database of the test's own. PostgreSQL's autovacuum may be at work in a new database for a moment, and
    only a superuser may stop it: tried again for a few seconds."""
    import time
    for attempt in range(30):
        try:
            with psycopg.connect(POSTGRES, autocommit=True) as conn:
                conn.execute('DROP DATABASE IF EXISTS "{}" WITH (FORCE)'.format(name))
            return
        except psycopg.errors.InsufficientPrivilege:
            if attempt == 29:
                raise
            time.sleep(0.2)


def test_every_table_numbered_by_id_returns_its_new_id(database):
    numbered = {r["table_name"] for r in database.all(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'id' "
        "AND is_identity = 'YES'")}
    assert numbered == storage.ID_TABLES


def test_the_app_refuses_a_database_behind_its_migrations(scratch):
    with pytest.raises(schema.SchemaError, match="never been migrated"):
        storage.Database(scratch)
    schema.upgrade(scratch, schema.BASELINE)
    if schema.head() != schema.BASELINE:
        with pytest.raises(schema.SchemaError, match="is at migration {}; this code needs".format(schema.BASELINE)):
            storage.Database(scratch)
    schema.upgrade(scratch)
    storage.Database(scratch).close()   # at the newest: it opens


def test_every_migration_goes_down_and_up_again(scratch):
    from alembic.script import ScriptDirectory
    schema.upgrade(scratch)
    revisions = [r.revision for r in ScriptDirectory.from_config(schema.alembic_config()).walk_revisions()]
    for revision in revisions[1:]:   # newest first: each one down, to the one before it
        schema.downgrade(scratch, revision)
    with psycopg.connect(scratch) as conn:
        assert schema.version_of(conn) == schema.BASELINE
    schema.upgrade(scratch)
    with psycopg.connect(scratch) as conn:
        assert schema.version_of(conn) == schema.head()


def test_a_database_made_before_migrations_is_stamped_or_completed(scratch):
    """The baseline only adds what an older database lacks; one that has all of it is stamped and nothing runs."""
    schema.upgrade(scratch, schema.BASELINE)
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("DROP TABLE alembic_version")
    assert schema.upgrade(scratch, schema.BASELINE)[0].startswith("An existing database at the baseline's shape: stamped")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("DROP TABLE alembic_version")
        conn.execute("DROP TABLE agent_plans")   # the live database was without it (log, 10 Nov 2026)
        conn.execute("ALTER TABLE jobs DROP COLUMN plan_id")
    said = schema.upgrade(scratch, schema.BASELINE)[0]
    assert "table agent_plans" in said and "column jobs.plan_id" in said
    with psycopg.connect(scratch) as conn:
        assert conn.execute("SELECT to_regclass('public.agent_plans') IS NOT NULL").fetchone()[0]


def test_going_below_the_baseline_has_to_be_asked_for(scratch):
    schema.upgrade(scratch, schema.BASELINE)
    with pytest.raises(SystemExit, match="drop_everything"):
        schema.downgrade(scratch, "base")


def test_the_tests_database_is_at_the_newest_migration():
    empty_postgres()
    with psycopg.connect(POSTGRES) as conn:
        assert schema.version_of(conn) == schema.head()


def test_servers_of_kinds_no_longer_used_are_taken_out_before_their_check(scratch):
    """A database that still has a model API of before (the agent is Claude's only since 31 Oct 2026) migrates: 0008
    takes it out, as the app's start did, then checks that only known kinds come in."""
    schema.upgrade(scratch, "0007")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        conn.execute("INSERT INTO endpoints (kind, name, url, created) VALUES ('openai', 'Kimi', 'https://x', now()), "
                     "('comfy', 'Zoro', 'http://zoro:8188', now())")
    schema.upgrade(scratch)
    with psycopg.connect(scratch) as conn:
        assert [r[0] for r in conn.execute("SELECT kind FROM endpoints ORDER BY id")] == ["comfy"]
