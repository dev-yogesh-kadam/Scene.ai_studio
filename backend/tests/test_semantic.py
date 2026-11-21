"""Search by meaning (semantic.py, migration 0011): on a PostgreSQL with pgvector, named by SCENE_TEST_VECTOR_URL (a
superuser's address: the extension is not a trusted one), e.g. the pgvector/pgvector:pg18 image; skipped, saying so,
where there is none. The vectors come from the fake embedder (words hashed), so no API is called."""

import json
import os
import secrets
import time
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from scene import schema, semantic
from scene.db import Database, as_everyone

VECTOR = os.environ.get("SCENE_TEST_VECTOR_URL", "")


@pytest.fixture
def vector_db():
    if not VECTOR:
        pytest.skip("No PostgreSQL with pgvector (set SCENE_TEST_VECTOR_URL to a superuser's address on one): "
                    "the search-by-meaning tests did not run")
    name = "scene_vec_" + secrets.token_hex(4)
    parts = urlsplit(VECTOR)
    with psycopg.connect(VECTOR, autocommit=True) as conn:
        conn.execute('CREATE DATABASE "{}"'.format(name))
    url = urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION vector")   # as a superuser
    schema.upgrade(url)
    yield url
    with psycopg.connect(VECTOR, autocommit=True) as conn:
        conn.execute('DROP DATABASE IF EXISTS "{}" WITH (FORCE)'.format(name))


def test_without_pgvector_the_migration_makes_nothing_and_the_rest_goes_on():
    """The tests' own database is on LUFI's PostgreSQL 18, which has no pgvector: 0011 made no table there."""
    from conftest import POSTGRES, empty_postgres
    empty_postgres()
    with psycopg.connect(POSTGRES) as conn:
        assert schema.version_of(conn) == schema.head()
        has_vector = conn.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'").fetchone()
        assert bool(conn.execute("SELECT to_regclass('public.embeddings')").fetchone()[0]) == bool(
            has_vector and conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone())


def test_items_are_found_by_what_they_are_about(vector_db):
    db = Database(vector_db, loop_guard="off")
    assert semantic.available(db)
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', ?)", (time.time(),))
    items = {}
    for name, prompt, about in [
            ("Shot 1", "an old chai seller lights his stove at dawn", "A tea stall in a Mumbai lane, steam rising"),
            ("Shot 2", "a cyclist climbs a hill in the rain", "A man on a bicycle, wet road, grey sky"),
            ("Shot 3", "neon signs reflected on a wet street at night", "A city street at night, pink and blue light")]:
        items[name] = db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, about, created) "
                             "VALUES (?, 'image/x', 'image', ?, ?, ?, '{}', ?, ?)",
                             (user, name, name + ".png", json.dumps({"prompt": prompt}), about, time.time()))
    db.run("INSERT INTO assets (user_id, name, tag, kind, filename, about, created) VALUES (?, 'Raju', 'character', 'image', "
           "'raju.png', 'An old tea seller with a grey moustache', ?)", (user, time.time()))
    embedder = semantic.Embedder("fake")
    with as_everyone():
        assert semantic.fill(db, embedder) == 4 and semantic.fill(db, embedder) == 0        # once, then nothing new
        db.run("UPDATE generations SET about = 'A tea stall at sunrise' WHERE id = ?", (items["Shot 1"],))
        assert semantic.fill(db, embedder) == 1                                             # its words changed
        ids = list(items.values())
        assert semantic.nearest(db, embedder, "tea stall", "g.id = ANY(?)", [ids])[0] == items["Shot 1"]
        assert semantic.nearest(db, embedder, "bicycle in the rain", "g.id = ANY(?)", [ids])[0] == items["Shot 2"]
        assert semantic.nearest(db, embedder, "city lights at night", "g.id = ANY(?)", [ids])[0] == items["Shot 3"]
        db.run("DELETE FROM generations WHERE id = ?", (items["Shot 2"],))
        assert db.one("SELECT COUNT(*) AS n FROM embeddings WHERE generation_id IS NOT NULL")["n"] == 2   # went with it
    db.close()


def test_the_library_route_searches_by_meaning_when_asked(vector_db, tmp_path):
    from fastapi.testclient import TestClient
    from conftest import built
    from scene.config import Settings
    from scene.main import create_app
    from test_api import register
    settings = Settings(database_url=vector_db, claude_models="off",
                        storage_dir=str(tmp_path), first_account_local=False,
                        web_dist_dir=str(built(tmp_path / "web")), semantic_search=True, embedding_provider="fake")
    with TestClient(create_app(settings)) as client:
        me = register(client)
        db = client.app.state.db
        for name, about in [("Chai", "a tea stall at dawn"), ("Ride", "a bicycle on a wet road")]:
            db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, about, created) "
                   "VALUES (?, 'image/x', 'image', ?, ?, '{}', '{}', ?, ?)", (me["id"], name, name + ".png", about, time.time()))
        with as_everyone():
            semantic.fill(db, client.app.state.embedder)
        by_meaning = client.get("/api/library", params={"q": "wet bicycle", "meaning": 1}).json()
        assert [i["name"] for i in by_meaning["items"]][0] == "Ride"
        assert client.get("/api/library", params={"q": "wet bicycle"}).json()["items"] == []   # by words: the description is not searched
