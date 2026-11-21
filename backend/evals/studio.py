"""A studio for the evals, as the tests make one (tests/conftest.py): an emptied test database, the tests' fake Scene
provider for its models (tests/studio_models.py), and Claude either played by the case's recorded answers (replay) or the
real Claude Code (live)."""

import contextlib
import importlib.util
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"


def test_support():
    """tests/conftest.py, loaded once under a name of its own: the test database's checks (never `scene`, one run at a
    time), empty_postgres, the built web app, with_claude and chat_session. Needs SCENE_TEST_DATABASE_URL."""
    mine = (TESTS / "conftest.py").resolve()
    found = next((m for m in list(sys.modules.values())   # under pytest, the conftest it loaded: one lock on the database
                  if getattr(m, "__file__", None) and Path(m.__file__).resolve() == mine), None)
    if found is None:
        sys.path.insert(0, str(BACKEND))
        spec = importlib.util.spec_from_file_location("scene_test_support", TESTS / "conftest.py")
        found = importlib.util.module_from_spec(spec)
        sys.modules["scene_test_support"] = found
        spec.loader.exec_module(found)
    return found


@contextlib.contextmanager
def studio(folder, live=False):
    """A TestClient of the app on an emptied test database. live: Claude Code on this machine answers (claude_models
    as the studio's default); otherwise the agent's model is the tests' Claude, whose answers each case plays."""
    from fastapi.testclient import TestClient
    from scene.config import Settings
    from scene.main import create_app
    from scene import claude
    support = test_support()
    support.empty_postgres()
    web = folder / "web"
    if not web.exists():
        support.built(web)
    # As the tests' studio (conftest.client): replay reaches Claude by an API key it never uses; live, Claude Code here.
    connection = {} if live else {"claude_connection": "api_key"}
    settings = Settings(database_url=support.POSTGRES, database_loop_guard=support.LOOP_GUARD,
                        claude_models="sonnet" if live else "off", storage_dir=str(folder / "storage"),
                        allow_signup=True, signup_credits=500, first_account_local=False, web_dist_dir=str(web),
                        local_tools_python=str(folder / "no-local-tools" / "python.exe"), **connection)
    real = claude.converse
    with TestClient(create_app(settings)) as client:
        # The models: the tests' fake Scene provider (tests/studio_models.py), as Studio_automation's would be.
        if str(TESTS) not in sys.path:
            sys.path.insert(0, str(TESTS))
        import studio_models
        client.provider = studio_models.install(client.app.state)
        if not live:
            support.with_claude(client.app.state.agent)
            claude.converse = support.chat_session(client.app.state.agent)
        try:
            yield client
        finally:
            claude.converse = real
