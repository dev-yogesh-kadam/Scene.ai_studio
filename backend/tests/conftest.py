import json
import os
import sys
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
               "cli": str(ROOT / "no-such-claude.exe"), "timeout": 30, "fast": "", "home": "", "window": 1_000_000}


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
    # whose program does not exist (a test that reaches it fails), as faked by each test (fake_claude, hosted, model).
    settings = Settings(database_url=POSTGRES, database_loop_guard=LOOP_GUARD, hold_queue_offline=False, comfy_url="http://127.0.0.1:9", claude_models="off",
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
