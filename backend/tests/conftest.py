import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from scene.config import Settings  # noqa: E402
from scene import security  # noqa: E402
from scene.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def quick_hashes(monkeypatch):
    """Passwords hashed at a small fraction of the real strength: the tests make many accounts."""
    monkeypatch.setattr(security, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1, "dklen": 32})


from scene import claude as _claude, claude_connection as _claude_connection  # noqa: E402

# What claude.py keeps between calls, as it is when no test has run: each test starts from it, and it is put back after
# each test, so one file's tests never meet another's (a test that swaps the live loop or the program's runner, a live
# session, a semaphore made in another test's event loop). Run in either order, test_claude_sdk.py and test_claude.py
# must both pass (test_harness.py checks it).
_CLAUDE_FUNCTIONS = {name: getattr(_claude, name) for name in ("converse", "ask", "_run", "_open", "forget", "find", "sdk")}
_CLAUDE_CONNECTION = dict(_claude.CONNECTION)


def _claude_fresh():
    for name, value in _CLAUDE_FUNCTIONS.items():
        if getattr(_claude, name) is not value:
            setattr(_claude, name, value)
    # No test runs this machine's own `claude`, nor asks Anthropic's API for its key: there is none on PATH here, and
    # the connection is Claude on this PC (test_claude_connection.py puts a fake `claude` in its place).
    _claude.find = lambda: ""
    _claude.RUN_WITH = ()
    _claude.CONNECTION = dict(_CLAUDE_CONNECTION)
    _claude.GUARD = None
    _claude.RUNNING.clear()
    _claude_connection._versions.clear()
    _claude_connection._signins.clear()
    _claude.LIMITS.clear()
    _claude.ON_LIMITS = None
    _claude.live.clear()
    _claude.held.clear()
    _claude._slots_of.clear()
    _claude.gate = None   # made again inside the next test's own event loop


@pytest.fixture(autouse=True)
def fresh_claude():
    _claude_fresh()
    yield
    _claude_fresh()


@pytest.fixture(autouse=True)
def secret_key(monkeypatch):
    """A secret key of the test's own (vault.py), so no test writes secret.key into the project."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SCENE_SECRET_KEY", Fernet.generate_key().decode("ascii"))


# The tests run on PostgreSQL, the studio's only database: a database they may empty, named by SCENE_TEST_DATABASE_URL
# (postgresql://scene_test:<password>@localhost:5432/scene_test, see docs/database.md). Its tables are made once per run
# by the migrations, and emptied before each test.
POSTGRES = os.environ.get("SCENE_TEST_DATABASE_URL", "")
if not POSTGRES:
    raise pytest.UsageError("The tests run on PostgreSQL: set SCENE_TEST_DATABASE_URL to a database they may empty, "
                            "postgresql://scene_test:<password>@localhost:5432/scene_test (docs/database.md).")


def _database_name(url):
    from urllib.parse import urlsplit
    return urlsplit(url).path.lstrip("/").split("?")[0]


# Never the studio's own database: the tests empty every table they find (the URL itself is never printed).
if _database_name(POSTGRES) in ("", "scene"):
    raise pytest.UsageError("SCENE_TEST_DATABASE_URL names the studio's live database (or none): the tests empty every "
                            "table. Point it at a test database, scene_test_<name> (docs/database.md).")
# One run at a time on a database: two runs on one database drop and empty each other's tables in the middle of a
# test (the schema made again under a running test_schema, a job's rows gone). A lock of PostgreSQL's own, held by a
# connection kept open for the whole run, so it goes with the process however that ends.
RUN_LOCK = 0x5CE7E57   # pg_advisory_lock key: "the test run on this database"
_run_lock = []


def hold_the_database():
    import psycopg
    if _run_lock:
        return
    conn = psycopg.connect(POSTGRES, autocommit=True)
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (RUN_LOCK,)).fetchone()[0]:
        conn.close()
        pytest.exit("Another test run is using the database {} right now: wait for it to end, or give this run a "
                    "database of its own (SCENE_TEST_DATABASE_URL).".format(_database_name(POSTGRES)), returncode=4)
    _run_lock.append(conn)


_migrated = []
# A database call that would block the app's event loop (db.Database.loop_guard): "raise" fails the test. "report"
# lets it pass and writes each place it happened (db.blocking_place) once to SCENE_TEST_LOOP_REPORT.
LOOP_GUARD = os.environ.get("SCENE_TEST_LOOP_GUARD", "raise")
if LOOP_GUARD == "report":
    from scene import db as _db

    def _report(self, sql, file=os.environ.get("SCENE_TEST_LOOP_REPORT", "loop-report.txt")):
        place = _db.blocking_place()
        if place not in self.warned:
            self.warned.add(place)
            with open(file, "a", encoding="utf-8") as out:
                out.write(place + "\n")
    _db.Database._on_loop = _report
    LOOP_GUARD = "warn"


def empty_postgres():
    """The test database at the newest migration, with no rows: made once per run, then emptied for each test."""
    import psycopg
    from scene import schema
    hold_the_database()
    if not _migrated:
        with psycopg.connect(POSTGRES, autocommit=True) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
        schema.upgrade(POSTGRES)
        _migrated.append(True)
    with psycopg.connect(POSTGRES, autocommit=True) as conn:
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                                             "AND tablename <> 'alembic_version'").fetchall()]
        conn.execute("TRUNCATE {} RESTART IDENTITY CASCADE".format(", ".join(tables)))


def a_job(db, job_id, user_id, workflow="image/x"):
    """The job a library item a test makes says it came from: generations.job_id is a key (migration 0007)."""
    import time
    db.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, status, created) "
           "VALUES (?, ?, ?, ?, ?, '{}', 'done', ?) ON CONFLICT (id) DO NOTHING",
           (job_id, user_id, job_id, workflow, workflow.split("/")[0], time.time()))


@pytest.fixture
def database():
    """The test database on its own, emptied, without the app (db.Database)."""
    from scene.db import Database
    empty_postgres()
    db = Database(POSTGRES)
    yield db
    db.close()


TEST_CLAUDE = {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": ["sonnet", "haiku"], "only": "",
               "cli": "claude", "timeout": 30, "fast": "", "home": str(Path(tempfile.gettempdir()) / "scene-claude-tests"),
               "window": 1_000_000}


CALLED_FIELDS = ("query", "item", "asset", "text", "path", "value", "against", "offset", "op", "settings")   # a call, as told back


def chat_session(agent):
    """claude.converse for the tests: Claude's live session played by agent.chat, which a test fakes (hosted, and the
    tests that fake chat themselves). Each answer of chat is a turn of the session: one that names a "tool" of the
    message is a call of that tool, run with the answer's fields, its result given back as the next message ("Result of
    <tool>:"); any other answer is Claude's answer to the message. What chat is given grows as a session does: the
    system prompt, the message, each call and result, and each message after (a plan sent back to be fixed)."""
    told = {}   # a thread's id() -> (the thread, what its session was told)

    async def converse(s, model, system, text, schema, thread, tools, about, finish_now, max_turns, result_chars=8000, web=False):
        from scene import agent as agent_module
        kept = told.get(id(thread))
        if kept is None or kept[0] is not thread:
            kept = told[id(thread)] = (thread, [{"role": "system", "content": system}])
        messages, called, tokens = kept[1], [], {}
        messages.append({"role": "user", "content": text})
        for _ in range(max_turns):
            asked = await agent.chat(list(messages), schema, model=model, thread=thread, **({"web": True} if web else {}))
            agent_module.add_tokens(tokens, asked.get("_usage"))
            name = asked.get("tool")
            if name not in tools:   # an answer, not a call
                messages.append({"role": "assistant", "content": json.dumps(asked, ensure_ascii=False)})
                return json.dumps(asked, ensure_ascii=False), tokens, None, called
            try:
                result = await tools[name](dict(asked))
            except (KeyError, ValueError, TypeError):
                result = "That call could not be run. Check its fields."
            called.append(name)
            call = {k: asked[k] for k in CALLED_FIELDS if asked.get(k) not in ("", 0, None)}
            if name == "check_shots":
                call["steps"] = asked.get("steps") if isinstance(asked.get("steps"), list) else []
            chars = result_chars(name) if callable(result_chars) else result_chars
            messages += [{"role": "assistant", "content": json.dumps(dict(call, tool=name), ensure_ascii=False)},
                         {"role": "user", "content": "Result of {}:\n{}".format(name, agent_module.fit_result(result, chars, name))}]
        # its turns ran out while it was still working: it is asked to answer now
        asked = await agent.chat(messages + [{"role": "user", "content": finish_now}], schema, model=model, thread=thread)
        agent_module.add_tokens(tokens, asked.get("_usage"))
        return json.dumps(asked, ensure_ascii=False), tokens, None, called
    return converse


def with_claude(agent):
    """The agent with TEST_CLAUDE as its model. A test that fakes ask() stands for Claude answering the whole message in
    one call, with no tool calls: ask_with_tools hands the message to it."""
    agent.services = {"claude": dict(TEST_CLAUDE, models=list(TEST_CLAUDE["models"]))}
    looping = agent.ask_with_tools

    async def ask_with_tools(system, message, workflow_ids, tools, finishing=None, **kwargs):
        if "ask" in vars(agent):
            return await agent.ask(system, message, workflow_ids, **({"model": kwargs["model"]} if kwargs.get("model") else {}))
        return await looping(system, message, workflow_ids, tools, finishing, **kwargs)
    agent.ask_with_tools = ask_with_tools
    return agent


# The web app's build as `npm run build -w apps/web` writes it, for the tests: dist/studio/ and dist/console/, each with
# its page, its hashed files under _app/, and the public files.
STUDIO_PAGE = '<!doctype html><html lang="en"><title>Scene.ai</title><script src="/theme.js"></script>' \
              '<script type="module" crossorigin src="/_app/studio-AbC123.js"></script><div id="app"></div>'
CONSOLE_PAGE = '<!doctype html><html lang="en"><title>Admin console</title><script src="/theme.js"></script>' \
               '<script type="module" crossorigin src="/_app/console-XyZ789.js"></script><div id="app"></div>'


def built(folder):
    for site, page in (("studio", STUDIO_PAGE), ("console", CONSOLE_PAGE)):
        (folder / site / "_app").mkdir(parents=True)
        (folder / site / "fonts").mkdir()
        (folder / site / "img").mkdir()
        (folder / site / (site + ".html")).write_text(page, encoding="utf-8")
        (folder / site / "theme.js").write_text("// theme", encoding="utf-8")
        (folder / site / "fonts" / "Archivo-latin.woff2").write_bytes(b"font")
        (folder / site / "img" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (folder / "studio" / "_app" / "studio-AbC123.js").write_text("console.log('studio')", encoding="utf-8")
    (folder / "console" / "_app" / "console-XyZ789.js").write_text("console.log('console')", encoding="utf-8")
    return folder


@pytest.fixture
def client(tmp_path):
    """The app with empty storage and a render server address nothing listens on."""
    empty_postgres()
    # Claude Code is never run by a test: the real one is switched off, and the agent is given a Claude of its own
    # with no `claude` to run (a test that reaches it fails, fresh_claude), as faked by each test (fake_claude, hosted,
    # model). It reaches Claude by an API key (with none): a studio open to other users, as most tests need (sign-up
    # open, the agent for everyone); Claude on this PC, a personal subscription, is test_claude_local.py's.
    settings = Settings(database_url=POSTGRES, database_loop_guard=LOOP_GUARD, hold_queue_offline=False, comfy_url="http://127.0.0.1:9", claude_models="off",
                        claude_connection="api_key",
                        storage_dir=str(tmp_path), allow_signup=True, signup_credits=500, first_account_local=False,
                        workflows_dir=str(ROOT / "workflows"), web_dist_dir=str(built(tmp_path / "web")))
    from scene import claude
    with TestClient(create_app(settings)) as test_client:
        with_claude(test_client.app.state.agent)
        # Claude's live session is played by the agent's chat, which each test fakes (chat_session)
        live, claude.converse = claude.converse, chat_session(test_client.app.state.agent)
        # The video workflow is a normal ComfyUI save: it is read with the node definitions a real server gave.
        test_client.app.state.catalog.saved = json.loads((BACKEND / "tests" / "fixtures" / "node_definitions.json").read_text(encoding="utf-8"))
        # The admin console: a site of its own beside the studio, with its own sign-in and cookie (test_api.console).
        test_client.console = TestClient(test_client.app.state.console)
        try:
            yield test_client
        finally:
            claude.converse = live
