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
    takes it out, as the app's start did, then checks that only known kinds come in. 0019 takes the ComfyUI servers
    out, and the ComfyUI providers with their keys and models, and the settings that switched to them."""
    schema.upgrade(scratch, "0007")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        conn.execute("INSERT INTO endpoints (kind, name, url, created) VALUES ('openai', 'Kimi', 'https://x', now()), "
                     "('comfy', 'Zoro', 'http://zoro:8188', now()), ('langfuse', 'Langfuse', 'http://x', now())")
    schema.upgrade(scratch, "0018")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        assert [r[0] for r in conn.execute("SELECT kind FROM endpoints ORDER BY id")] == ["comfy", "langfuse"]
        conn.execute("INSERT INTO providers (kind, name) VALUES ('comfyui', 'ComfyUI'), ('scene_provider_v1', 'Generation server')")
        conn.execute("INSERT INTO settings (key, value) VALUES ('provider_router', 'on'), ('comfy_url', 'http://zoro:8188'), "
                     "('allow_signup', '1')")
    schema.upgrade(scratch)
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        assert [r[0] for r in conn.execute("SELECT kind FROM endpoints ORDER BY id")] == ["langfuse"]
        kinds = {r[1]: r[0] for r in conn.execute("SELECT kind, name FROM providers")}
        assert "comfyui" not in kinds.values() and kinds["Generation server"] == "scene_provider_v1"
        assert [r[0] for r in conn.execute("SELECT key FROM settings ORDER BY key")] == ["allow_signup"]
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("INSERT INTO providers (kind, name) VALUES ('comfyui', 'ComfyUI')")


def test_0020_deletes_the_old_memory_and_keys_it_by_module(scratch):
    """The agent's memory of a user was one for all their projects; 0020 deletes it and keys what comes after by module."""
    schema.upgrade(scratch, "0019")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        user = conn.execute("INSERT INTO users (email, name, password_hash, created) VALUES ('a@x', 'A', 'x', now()) RETURNING id").fetchone()[0]
        conn.execute("INSERT INTO user_memory (user_id, key, value, updated) VALUES (%s, 'pref.shape', 'portrait', now())", (user,))
    schema.upgrade(scratch)
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        assert conn.execute("SELECT COUNT(*) FROM user_memory").fetchone()[0] == 0
        key = [r[0] for r in conn.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = 'user_memory'::regclass AND i.indisprimary")]
        assert sorted(key) == ["key", "project_id", "user_id"]
        with pytest.raises(psycopg.errors.NotNullViolation):
            conn.execute("INSERT INTO user_memory (user_id, key, value, updated) VALUES (%s, 'pref.x', 'y', now())", (user,))


# Tables with a user_id that have no row rule, on purpose for now (docs/database.md lists the ruled ones): read only by
# admins (agent_calls, moderation), shared across users (project_members), or always filtered by user_id in its SQL
# (claude_sessions). A new user table is ruled, or added here with its reason.
UNRULED = {"agent_calls", "claude_sessions", "moderation", "project_members"}


def test_every_table_of_a_users_rows_has_its_row_rule(database):
    rows = database.all(
        "SELECT c.relname AS name, c.relrowsecurity AS rls, c.relforcerowsecurity AS forced, "
        "EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname AND p.policyname = 'own_rows') AS own, "
        "EXISTS (SELECT 1 FROM information_schema.columns k WHERE k.table_schema = 'public' AND k.table_name = c.relname "
        "AND k.column_name = 'user_id') AS has_user "
        "FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'")
    ruled = {r["name"] for r in rows if r["rls"] and r["forced"] and r["own"]}
    users_tables = {r["name"] for r in rows if r["has_user"]} | {"users"}
    assert users_tables - ruled == UNRULED
    assert not ruled - users_tables


def test_the_query_indexes_of_0012_come_and_go_with_it(scratch):
    def indexes():
        with psycopg.connect(scratch) as conn:
            return {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
    schema.upgrade(scratch, "0012")
    assert {"projects_user", "alerts_open"} <= indexes()
    schema.downgrade(scratch, "0011")
    assert not {"projects_user", "alerts_open"} & indexes()
