"""The hardening of 10 November 2026: sign-up closed until an admin opens it, the limits of the expensive paths, the admin
console kept off the studio's (public) port, and an audit log whose seals hold when entries are written together."""

import json
import threading
from types import SimpleNamespace

from scene import audit, security
from scene.config import ROOT, Settings, load_settings


def account(client, email="ada@example.com", password="correct horse", **extra):
    client.cookies.clear()
    return client.post("/api/auth/register", json={"email": email, "password": password, **extra})


# ---------------------------------------------------------------- sign-up

def test_a_fresh_installation_keeps_sign_up_closed_and_gives_no_free_credits(tmp_path):
    defaults = Settings()
    assert defaults.allow_signup is False and defaults.signup_credits == 0 and defaults.signup_invite == ""
    # A config.json made from the example does not open it either; nor does a config.json that says nothing.
    example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    assert example.get("allow_signup") is False and not example.get("signup_credits")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert load_settings(tmp_path / "config.json").allow_signup is False


def test_only_the_first_account_is_made_while_sign_up_is_closed(client):
    client.app.state.settings.allow_signup = False     # as on a fresh installation (the tests' own setting opens it)
    assert client.get("/api/auth/state").json() == {"first_run": True, "signup_open": True}
    assert account(client).status_code == 200            # the first account, the admin
    assert client.get("/api/auth/state").json() == {"first_run": False, "signup_open": False}
    refused = account(client, "eve@example.com")
    assert refused.status_code == 403 and "closed" in refused.json()["detail"]
    # An admin opens it in the console's Settings, which wins over config.json.
    client.app.state.db.set_setting("allow_signup", "1")
    assert account(client, "eve@example.com").status_code == 200


def test_an_invite_code_is_asked_for_when_one_is_set(client):
    client.app.state.settings.signup_invite = "seven-ravens"
    assert account(client).status_code == 200            # the first account needs none
    assert client.get("/api/auth/state").json() == {"first_run": False, "signup_open": True, "invite_required": True}
    assert account(client, "eve@example.com").status_code == 403
    assert account(client, "eve@example.com", invite="seven-crows").status_code == 403
    assert account(client, "eve@example.com", invite=" seven-ravens ").status_code == 200
    entries = client.app.state.db.all("SELECT action, detail FROM audit_log WHERE action = 'Refused a new account'")
    assert len(entries) == 2 and all("invite" in e["detail"] for e in entries)


def test_a_new_account_starts_with_the_credits_the_studio_gives(client):
    assert account(client).json()["credits"] == 500      # the tests' signup_credits
    client.app.state.settings.signup_credits = 0
    assert account(client, "eve@example.com").json()["credits"] == 0


# ---------------------------------------------------------------- rate limits

def test_the_expensive_paths_are_limited_per_user(client):
    account(client)
    limit = security.LIMITS
    for path, name in (("/api/library/import", "import"), ("/api/agent/plans", "plan"), ("/api/edit/film", "render")):
        answers = [client.post(path, json={}).status_code for _ in range(limit[name][0] + 1)]
        assert 429 not in answers[:-1] and answers[-1] == 429, (path, answers[-3:])
    over = client.post("/api/edit/film", json={})
    assert over.status_code == 429 and int(over.headers["retry-after"]) >= 1
    # Another user has counts of their own.
    account(client, "eve@example.com")
    assert client.post("/api/edit/film", json={}).status_code != 429


def test_an_agent_tool_can_ask_whether_its_user_is_over_the_limit(client):
    import asyncio
    from scene.api.deps import allowed
    state = client.app.state
    most = security.LIMITS["page_build"][0]

    async def ask(user_id, times):
        return [await allowed(state, "page_build", user_id) for _ in range(times)]
    answers = asyncio.run(ask(1, most + 1))
    assert all(answers[:-1]) and answers[-1] is False
    assert asyncio.run(ask(2, 1)) == [True]
