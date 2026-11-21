"""python -m scene.manage: the first admin made from the command line (Docker, a proxy: no browser on the studio's
machine), and the agent switched to the Anthropic API key."""

import pytest

from scene import audit, manage
from scene.config import Settings
from scene.providers import registry
from scene.security import verify_password


def test_the_first_admin_is_made_once_and_written_in_the_audit_log(database):
    user_id = manage.create_admin(database, " Owner@Example.com ", "", "a long password")
    user = database.one("SELECT * FROM users WHERE id = ?", (user_id,))
    assert (user["email"], user["name"], user["role"]) == ("owner@example.com", "owner", "admin")
    assert verify_password("a long password", user["password_hash"])
    entry = database.one("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1")
    assert (entry["action"], entry["target"], entry["ip"]) == ("Created account", "owner@example.com", "command line")
    assert audit.verify(database)["ok"]
    with pytest.raises(SystemExit, match="accounts already"):
        manage.create_admin(database, "second@example.com", "Second", "another long password")
    assert database.one("SELECT COUNT(*) AS n FROM users")["n"] == 1


@pytest.mark.parametrize("email, password, said", [("not an email", "a long password", "valid email"),
                                                   ("owner@example.com", "short", "at least")])
def test_a_bad_email_or_password_makes_nothing(database, email, password, said):
    with pytest.raises(SystemExit, match=said):
        manage.create_admin(database, email, "", password)
    assert database.one("SELECT 1 FROM users") is None


def test_the_agent_moves_from_claude_on_this_pc_to_the_api_key(database):
    # A fresh database, as the migrations leave it: Claude on this PC is the only Claude provider, and the agent's.
    database.run("INSERT INTO providers (kind, name, base_url, active, priority, legacy) "
                 "VALUES ('claude_local', 'Claude on this PC', '', 1, 0, 'claude:local')")
    assert registry.agent_choice(database, Settings())["kind"] == "claude_local"
    manage.agent_uses_api_key(database)
    assert registry.agent_choice(database, Settings())["kind"] == "anthropic"
    assert registry.claude_values(database, Settings()) == {"claude_connection": "api_key", "anthropic_api_key": ""}
    manage.agent_uses_api_key(database)   # again: still one Anthropic provider
    assert database.one("SELECT COUNT(*) AS n FROM providers WHERE kind = 'anthropic'")["n"] == 1
