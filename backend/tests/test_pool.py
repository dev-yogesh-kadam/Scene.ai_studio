"""The database's connections are pooled (db.py): every statement says whose rows it is for on the connection it takes
(when that connection last showed someone else's), so a request never sees another user's rows through a connection
another request used. And the event loop never waits for the database."""

import asyncio
import threading

import pytest

from conftest import POSTGRES, empty_postgres
from scene import db as storage


@pytest.fixture
def small_pool():
    """Two connections for many users: every connection is used by several of them, one after another."""
    empty_postgres()
    db = storage.Database(POSTGRES, pool_size=2, loop_guard="raise")
    users = [db.run("INSERT INTO users (email, name, password_hash, created) VALUES (?, ?, 'x', 0)",
                    ("u{}@example.com".format(n), "U{}".format(n))) for n in range(6)]
    for user in users:
        for n in range(3):
            db.run("INSERT INTO projects (user_id, name, created) VALUES (?, ?, 0)", (user, "{}-{}".format(user, n)))
    yield db, users
    db.close()


def test_a_pooled_connection_never_shows_one_users_rows_to_another(small_pool):
    db, users = small_pool
    wrong, done = [], []

    def request(user):
        """What a signed-in request does: act for its user, then read with SQL that forgot to ask for one user."""
        storage.act_for(user)
        for _ in range(30):
            owners = {r["user_id"] for r in db.all("SELECT user_id FROM projects")}
            if owners != {user}:
                wrong.append((user, owners))
        done.append(user)

    threads = [threading.Thread(target=lambda u=u: __import__("contextvars").copy_context().run(request, u))
               for u in users + users[:2]]   # eight requests at once over two connections
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(done) == 8 and not wrong


def test_a_connection_another_user_used_shows_only_the_rows_of_the_user_now_asking(small_pool):
    """A connection keeps the last user it was told (db.Database._execute): the next statement on it, for anyone else,
    says whose rows it is for before it runs."""
    db, users = small_pool
    for user in users:   # every connection of the pool used for every user, one after another
        storage.act_for(user)
        try:
            assert {r["user_id"] for r in db.all("SELECT user_id FROM projects")} == {user}
        finally:
            storage.act_for_everyone()
    assert len(db.all("SELECT id FROM projects")) == 3 * len(users)   # everyone's, for work of no one request
    with db.pool.connection() as conn:   # a connection without the app's word for whose rows shows none
        conn.execute("RESET app.user_id")
        assert conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"] == 0
        conn.acting = None


def test_async_code_awaits_the_database_and_keeps_whose_rows(small_pool):
    db, users = small_pool
    db.serving = True   # as while the app serves requests: a plain call on the loop is refused

    async def as_user(user):
        storage.act_for(user)
        rows = await db.aall("SELECT user_id FROM projects")
        return {r["user_id"] for r in rows}

    async def everything():
        with pytest.raises(RuntimeError, match="on the event loop"):
            db.all("SELECT 1")
        return await asyncio.gather(*(as_user(u) for u in users))

    assert asyncio.run(everything()) == [{u} for u in users]


def test_a_result_kept_on_a_database_thread_still_gets_its_poster(client):
    """JobManager._record runs on a database thread (db.offload): the poster it starts is made on the app's loop."""
    import time
    from PIL import Image
    from scene import media
    db = client.app.state.db
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('p@example.com', 'P', 'x', ?)", (time.time(),))
    db.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, status, created) "
           "VALUES ('jposter', ?, 'Made', 'image/x', 'image', '{}', 'running', ?)", (user, time.time()))
    folder = client.app.state.outputs.folder(user)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "made.png"
    Image.new("RGB", (64, 40), "red").save(target)
    job = {"user_id": user, "id": "jposter", "project_id": None, "workflow": "image/x", "name": "Made", "summary": "",
           "settings": {}, "started": time.time()}
    client.app.state.jobs._record(job, "image", target, {})   # this test's thread is not the loop's, as a database thread
    kept = folder / db.one("SELECT filename FROM generations WHERE job_id = 'jposter'")["filename"]   # where it was filed
    until = time.time() + 10
    while not media.poster_path(kept).is_file():
        assert time.time() < until, "no poster was made"
        time.sleep(0.05)
