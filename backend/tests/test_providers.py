"""The provider registry (migration 0015, providers/registry.py), the router (providers/router.py) and the console's
Servers & APIs → Providers (api/providers.py). The v1 adapter and a job made through it: test_provider_v1.py."""

import asyncio
import contextlib
import importlib.util
import json
import time
from pathlib import Path

import pytest

from fake_v1 import FakeV1
from scene import vault
from scene.providers import registry, router as router_module
from scene.providers.base import KeyProblem, ProviderProblem, RequestProblem
from scene.providers.router import NoProvider, Router
from test_api import console, register

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def migration(name="0015_providers.py"):
    spec = importlib.util.spec_from_file_location("migration_" + name[:4], VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def bridge_kind_allowed(db):
    """The test database is at the newest migration, where 0017 took the LUFI bridge's provider kind away and 0019
    ComfyUI's: they are allowed again while a test replays 0015's copy (which makes them from the old settings and
    servers), then taken away."""
    then = migration("0018_local_tools.py").KINDS   # the kinds allowed before ComfyUI went
    newest = migration("0019_drop_comfyui.py").KINDS   # the kinds the newest migration allows
    db.run("ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_kind_known")
    db.run("ALTER TABLE providers ADD CONSTRAINT providers_kind_known CHECK (kind IN {})".format(then[:-1] + ", 'claude_bridge')"))
    try:
        yield
    finally:
        db.run("DELETE FROM providers WHERE kind IN ('claude_bridge', 'comfyui')")
        db.run("ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_kind_known")
        db.run("ALTER TABLE providers ADD CONSTRAINT providers_kind_known CHECK (kind IN {})".format(newest))


# ---------------------------------------------------------------- the migration's copy

def test_the_migration_copies_the_servers_and_the_claude_connection_once(database):
    db = database
    db.run("INSERT INTO endpoints (kind, name, url, api_key, models, slots, active, created) VALUES "
           "('comfy', 'Zoro', 'http://100.64.0.30:8188', '', '', 1, 1, ?), "
           "('comfy', 'Generation server', 'http://100.64.0.30:8189', ?, 'generation_*', 4, 1, ?), "
           "('langfuse', 'Langfuse', 'http://127.0.0.1:3000', 'pk:sk', '', 1, 1, ?)",
           (time.time(), vault.seal("gen-key-123456"), time.time(), time.time()))
    for key, value in (("claude_connection", "lufi_bridge"), ("claude_bridge_url", "http://100.64.0.7:8765"),
                       ("claude_bridge_key", vault.seal("bridge-key-abcdef")), ("anthropic_api_key", vault.seal("sk-ant-xyz98765"))):
        db.set_setting(key, value)
    copy = migration().COPY
    with bridge_kind_allowed(db):
        for _ in range(2):   # re-runnable: the second run adds nothing
            for statement in copy:
                db.run(statement)
        the_copy_of_0015(db)


def the_copy_of_0015(db):
    providers = db.all("SELECT * FROM providers ORDER BY id")
    assert [(p["kind"], p["name"], p["base_url"], p["legacy"]) for p in providers] == [
        ("comfyui", "Zoro", "http://100.64.0.30:8188", "endpoints:1"),
        ("comfyui", "Generation server", "http://100.64.0.30:8189", "endpoints:2"),
        ("anthropic", "Anthropic", "", "claude:anthropic"),
        ("claude_bridge", "LUFI bridge", "http://100.64.0.7:8765", "claude:bridge")]   # Langfuse stays in endpoints
    keys = db.all("SELECT * FROM provider_keys ORDER BY id")
    assert [(k["provider_id"], k["label"], k["max_concurrent"]) for k in keys] == [
        (1, "Server", 1), (2, "Server", 4), (3, "API key", None), (4, "Bridge key", None)]
    assert vault.reveal(keys[1]["secret"]) == "gen-key-123456" and vault.reveal(keys[3]["secret"]) == "bridge-key-abcdef"
    assert all(k["secret"] == "" or k["secret"].startswith(vault.MARK) for k in keys)   # still sealed
    assert db.setting("agent_provider") == "4"   # the bridge was the connection picked
    assert db.one("SELECT COUNT(*) AS n FROM endpoints")["n"] == 3   # nothing taken out
    from scene.config import Settings
    registry.seed(db, Settings())   # at start: the last 4 the migration could not read
    # (and On this PC's one key, with no secret: migration 0018's, made by the seed on an emptied test database)
    assert [k["last4"] for k in db.all("SELECT last4 FROM provider_keys ORDER BY id")] == ["", "3456", "8765", "cdef", ""]
    found = registry.claude_values(db, Settings())   # the code of now: the bridge is not one of its providers
    assert found == {"claude_connection": "this_pc", "anthropic_api_key": "sk-ant-xyz98765"}


def test_an_installation_without_a_claude_connection_gets_anthropic_for_the_agent(database):
    for statement in migration().COPY:
        database.run(statement)
    assert [p["kind"] for p in database.all("SELECT kind FROM providers")] == ["anthropic"]
    assert database.setting("agent_provider") == "1"


# ---------------------------------------------------------------- the router

def a_v1(db, name="Generation server", priority=0, keys=1, model="seedance_2_5", **key_fields):
    provider_id = registry.add_provider(db, "scene_provider_v1", name, "http://100.64.0.30:8189", priority)
    made = []
    for n in range(keys):
        key_id = registry.add_key(db, provider_id, "sa_live_{}{:08d}".format(name[:3].lower(), n), "key {}".format(n + 1), **key_fields)
        registry.save_models(db, provider_id, key_id, [{"id": model, "name": "Seedance 2.5", "capability": "text_to_video"}])
        made.append(key_id)
    return provider_id, made


def test_the_router_picks_the_least_busy_healthy_key(database):
    _, (a, b) = a_v1(database, keys=2, max_concurrent=2)
    router = Router(database)
    first, problem = router.pick("seedance_2_5")
    assert problem == "" and first["key"]["id"] == a   # a tie: the first key
    router.take(first, "job1")
    assert router.pick("seedance_2_5")[0]["key"]["id"] == b   # a is half busy, b is free
    router.take(router.pick("seedance_2_5")[0], "job2")
    router.take(router.pick("seedance_2_5")[0], "job3")   # 1 of 2 each: a again, by the tie
    router.take(router.pick("seedance_2_5")[0], "job4")
    assert router.pick("seedance_2_5") == (None, "")   # both full: the job waits


def test_the_router_skips_cooled_down_full_and_over_cap_keys(database):
    _, (a, b, c) = a_v1(database, keys=3)
    database.run("UPDATE provider_keys SET cooldown_until = ? WHERE id = ?", (time.time() + 60, a))
    database.run("UPDATE provider_keys SET daily_cap = 100 WHERE id = ?", (b,))
    database.run("INSERT INTO users (id, email, name, password_hash, created) VALUES (1, 'a@x', 'A', 'x', ?)", (time.time(),))
    database.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, status, cost, provider_key, created, started) "
                 "VALUES ('j1', 1, 'j', 'video/@seedance_2_5', 'video', '{}', 'done', 120, ?, ?, ?)", (b, time.time(), time.time()))
    router = Router(database)
    choice, _ = router.pick("seedance_2_5")
    assert choice["key"]["id"] == c and router.why_not(router.candidates("seedance_2_5")[1]) == "over its daily cap"
    router.take(choice, "job1")   # c is full now (1 at once)
    assert router.pick("seedance_2_5") == (None, "")
    database.run("UPDATE provider_keys SET status = 'invalid' WHERE id IN (?, ?, ?)", (a, b, c))
    router.forget()
    choice, problem = router.pick("seedance_2_5")
    assert choice is None and problem == "No provider has a key for Seedance 2.5: add one in Servers & APIs → Providers."


def test_a_key_problem_tries_the_next_key_once_and_cools_the_key(database):
    _, (a, b, c) = a_v1(database, keys=3)
    router, tried = Router(database), []

    async def attempt(choice):
        tried.append(choice["key"]["id"])
        assert choice["secret"].startswith("sa_live_")   # the call has the key; nothing else does
        if choice["key"]["id"] == a:
            raise KeyProblem("Too many jobs at once.", "rate_limited", 30)
        return "started"

    result, choice = asyncio.run(router.run("seedance_2_5", attempt, job_id="job1"))
    assert (result, choice["key"]["id"], tried) == ("started", b, [a, b])
    cooled = registry.key(database, a)
    assert cooled["status"] == "rate_limited" and 25 < cooled["cooldown_until"] - time.time() <= 31
    assert router.running == {b: {"job1"}}   # the failed key was let go; the caller lets go of b when the job ends

    tried.clear()
    router.running.clear()   # job1 ended: b is free again (a still rests)

    async def every_key_out(choice):
        tried.append(choice["key"]["id"])
        raise KeyProblem("Out of credit.", "no_credit")
    with pytest.raises(KeyProblem):
        asyncio.run(router.run("seedance_2_5", every_key_out, job_id="job2"))
    assert len(tried) == 2   # one key, then the next once
    assert registry.key(database, tried[0])["cooldown_until"] - time.time() > 3500   # an hour for no credit
    assert "job2" not in set().union(*router.running.values())


def test_a_provider_problem_tries_the_next_provider_once_and_a_request_problem_never(database):
    first, _ = a_v1(database, "Generation server", priority=0)
    second, _ = a_v1(database, "Backup", priority=1)
    router, tried = Router(database), []

    async def down(choice):
        tried.append(choice["provider"]["id"])
        if choice["provider"]["id"] == first:
            raise ProviderProblem("The model is down.")
        return "ok"
    assert asyncio.run(router.run("seedance_2_5", down))[0] == "ok" and tried == [first, second]

    tried.clear()

    async def refused(choice):
        tried.append(choice["provider"]["id"])
        raise RequestProblem("Content refused.")
    with pytest.raises(RequestProblem):
        asyncio.run(router.run("seedance_2_5", refused))
    assert tried == [first]   # never retried

    with pytest.raises(NoProvider, match="No provider has a key for kling_4_0"):
        asyncio.run(router.run("kling_4_0", refused))


def test_an_invalid_key_rests_until_fixed(database):
    _, (a, b) = a_v1(database, keys=2)
    router = Router(database)

    async def revoked(choice):
        if choice["key"]["id"] == a:
            raise KeyProblem("This key was revoked.", "invalid")
        return "ok"
    asyncio.run(router.run("seedance_2_5", revoked))
    row = registry.key(database, a)
    assert row["status"] == "invalid" and row["cooldown_until"] is None and "revoked" in row["last_error"]
    assert [c["key"]["id"] for c in router.candidates("seedance_2_5")] == [b]   # left out for good


# ---------------------------------------------------------------- the console

@pytest.mark.no_models
def test_adding_a_key_checks_it_first_and_never_gives_it_back(client, monkeypatch):
    fake = FakeV1()
    monkeypatch.setattr(router_module, "V1", lambda base_url: __import__("scene.providers.v1", fromlist=["V1"]).V1(base_url, http=fake.client()))
    register(client)
    desk = console(client)
    listed = desk.get("/api/admin/providers").json()
    assert "router" not in listed and [p["kind"] for p in listed["providers"]] == ["claude_local", "anthropic", "local_tools"]
    bad = desk.post("/api/admin/providers/keys", json={"kind": "scene_provider_v1", "base_url": "http://fake-v1",
                                                       "secret": "sa_live_wrong0000"}).json()
    assert bad["saved"] is False and "not known" in bad["check"]["error"]
    assert len(bad["providers"]) == 3   # nothing saved, not even the provider (On this PC is the third)
    good = desk.post("/api/admin/providers/keys", json={"kind": "scene_provider_v1", "base_url": "fake-v1", "name": "Zoro",
                                                        "secret": "sa_live_alpha1234", "label": "studio A"}).json()
    assert good["saved"] and good["check"]["ok"] and good["check"]["models"] == 2 and good["check"]["credits"] == 91296
    provider = next(p for p in good["providers"] if p["kind"] == "scene_provider_v1")
    assert provider["base_url"] == "http://fake-v1" and provider["models"] == 2
    key = provider["keys"][0]
    assert (key["label"], key["last4"], key["status"], key["credits"]["available"]) == ("studio A", "1234", "ok", 91296)
    for answer in (good, desk.get("/api/admin/providers").json()):
        assert "sa_live_alpha1234" not in json.dumps(answer)   # never sent back
    stored = client.app.state.db.one("SELECT secret FROM provider_keys WHERE id = ?", (key["id"],))["secret"]
    assert stored.startswith(vault.MARK) and "alpha" not in stored
    anyway = desk.post("/api/admin/providers/keys", json={"provider_id": provider["id"], "secret": "sa_live_wrong0000",
                                                          "save_anyway": True}).json()
    assert anyway["saved"] and next(p for p in anyway["providers"] if p["id"] == provider["id"])["keys"][1]["status"] == "invalid"
    changed = desk.put("/api/admin/providers/keys/%d" % key["id"], json={"max_concurrent": 3, "daily_cap": 5000, "active": False}).json()
    shown = next(p for p in changed["providers"] if p["id"] == provider["id"])["keys"][0]
    assert (shown["max_concurrent"], shown["daily_cap"], shown["active"]) == (3, 5000, False)
    fake.revoked.add("sa_live_alpha1234")
    tested = desk.post("/api/admin/providers/keys/%d/test" % key["id"]).json()
    assert tested["check"]["ok"] is False and tested["check"]["status"] == "invalid"
    desk.delete("/api/admin/providers/keys/%d" % key["id"])
    assert len(next(p for p in desk.get("/api/admin/providers").json()["providers"] if p["id"] == provider["id"])["keys"]) == 1
    assert [e["action"] for e in desk.get("/api/admin/audit").json()["entries"]][:2] == [
        "Removed a provider key", "Changed a provider key"]


def test_what_makes_what_lists_each_kind_of_work_and_its_models(client):
    """GET .../capabilities (registry.coverage): each kind of work with the models that make it and their keys. Video to
    video, outpaint and character animation are made by the video models that edit a reference video (Seedance)."""
    register(client)
    rows = {r["capability"]: r for r in console(client).get("/api/admin/providers/capabilities").json()["capabilities"]}
    models = lambda capability: [m["id"] for m in rows[capability]["models"]]
    assert sorted(models("text_to_video")) == ["kling_4_0", "seedance_2_5"] and rows["text_to_video"]["words"] == "Video"
    assert rows["text_to_video"]["state"] == "provider" and rows["text_to_video"]["live"] is True
    for edit in ("video_to_video", "outpaint", "animate"):
        assert models(edit) == ["seedance_2_5"] and rows[edit]["state"] == "provider", edit   # Kling edits no clip
    assert models("speech") == ["speech"] and models("lip_sync") == ["lip_sync"]
    assert rows["control_map"]["state"] == "none" and rows["control_map"]["models"] == [] and rows["control_map"]["live"] is False


def test_the_agents_provider_is_picked_and_the_personal_subscription_rules_hold(client):
    from scene import claude, claude_connection
    register(client)
    desk = console(client)
    listed = desk.get("/api/admin/providers").json()
    anthropic = next(p for p in listed["providers"] if p["kind"] == "anthropic")
    local = next(p for p in listed["providers"] if p["kind"] == "claude_local")
    assert listed["agent_provider"] == anthropic["id"] and local["keyless"] is True   # the tests' studio: config.json's api_key
    db, settings = client.app.state.db, client.app.state.settings
    picked = desk.put("/api/admin/providers/agent", json={"provider_id": local["id"]}).json()
    assert picked["agent_provider"] == local["id"] and picked["testing"] == claude_connection.TESTING
    assert claude.CONNECTION == {"mode": claude.LOCAL_SIGNIN, "api_key": ""}   # no key, ever
    assert db.setting("claude_connection") == "this_pc"   # the old card's setting, kept beside it
    assert claude_connection.testing()   # sign-up closed and the agent for admins only (claude_connection.guard_for)
    assert desk.delete("/api/admin/providers/%d" % local["id"]).status_code == 400   # the agent uses it
    desk.put("/api/admin/providers/agent", json={"provider_id": anthropic["id"]})
    assert claude.CONNECTION["mode"] == claude.API_KEY and not claude_connection.testing()
    assert desk.put("/api/admin/providers/agent", json={"provider_id": 999}).status_code == 400


def test_the_old_claude_card_writes_the_registry(client):
    from scene import claude, claude_connection
    register(client)
    db, settings = client.app.state.db, client.app.state.settings
    claude_connection.save(db, settings, {"mode": "api_key", "api_key": "sk-ant-abcdefgh"})
    anthropic = next(p for p in registry.providers(db) if p["kind"] == "anthropic")
    assert registry.keys(db, anthropic["id"])[0]["last4"] == "efgh" and registry.agent_provider_id(db) == anthropic["id"]
    assert claude.CONNECTION == {"mode": claude.API_KEY, "api_key": "sk-ant-abcdefgh"}
    claude_connection.save(db, settings, {"mode": "this_pc"})
    local = next(p for p in registry.providers(db) if p["kind"] == "claude_local")
    assert registry.agent_provider_id(db) == local["id"] and claude.CONNECTION == {"mode": claude.LOCAL_SIGNIN, "api_key": "sk-ant-abcdefgh"}
