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


# Set to a PostgreSQL database that may be emptied (postgresql://scene_test:...@localhost:5432/scene_test) to run the
# tests against PostgreSQL instead of SQLite. Every test starts with that database empty.
POSTGRES = os.environ.get("SCENE_TEST_DATABASE_URL", "")


def empty_postgres():
    import psycopg
    with psycopg.connect(POSTGRES, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


TEST_CLAUDE = {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": ["sonnet", "haiku"], "only": "",
               "cli": str(ROOT / "no-such-claude.exe"), "timeout": 30, "fast": "", "home": "", "window": 1_000_000}


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


@pytest.fixture
def client(tmp_path):
    """The app with empty storage and a render server address nothing listens on."""
    if POSTGRES:
        empty_postgres()
    # Claude Code is never run by a test: the real one is switched off, and the agent is given a Claude of its own
    # whose program does not exist (a test that reaches it fails), as faked by each test (fake_claude, hosted, model).
    settings = Settings(database_url=POSTGRES, hold_queue_offline=False, comfy_url="http://127.0.0.1:9", claude_models="off",
                        storage_dir=str(tmp_path), signup_credits=500, first_account_local=False,
                        workflows_dir=str(ROOT / "workflows"), frontend_dir=str(ROOT / "frontend"))
    with TestClient(create_app(settings)) as test_client:
        with_claude(test_client.app.state.agent)
        # The video workflow is a normal ComfyUI save: it is read with the node definitions a real server gave.
        test_client.app.state.catalog.saved = json.loads((BACKEND / "tests" / "fixtures" / "node_definitions.json").read_text(encoding="utf-8"))
        # The admin console: a site of its own beside the studio, with its own sign-in and cookie (test_api.console).
        test_client.console = TestClient(test_client.app.state.console)
        yield test_client
