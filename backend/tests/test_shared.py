"""What several app processes share through Redis (shared.py, redis_url), tested with fakeredis; and with it off, the
studio as it always was."""

import asyncio
import json

import fakeredis
import pytest

from scene import shared
from scene.security import LoginThrottle, RateLimit


def process(server):
    """One app process's view of Redis: its own clients, the same server."""
    return shared.RedisShared("redis://fake", client=fakeredis.FakeRedis(server=server, decode_responses=True),
                              async_client=fakeredis.FakeAsyncRedis(server=server, decode_responses=True))


def test_with_redis_off_everything_is_this_process_alone(client):
    state = client.app.state
    assert not state.shared.enabled and isinstance(state.limits, RateLimit) and isinstance(state.throttle, LoginThrottle)
    loads = []
    assert state.shared.cached("pricing", "w", lambda: loads.append(1) or 7) == 7
    assert state.shared.cached("pricing", "w", lambda: loads.append(1) or 7) == 7 and len(loads) == 2   # no cache


def test_a_cached_value_is_kept_until_something_of_its_name_changes():
    server = fakeredis.FakeServer()
    one, two = process(server), process(server)
    loads = []
    assert one.cached("pricing", "video/x", lambda: loads.append("a") or {"base": 10}) == {"base": 10}
    assert two.cached("pricing", "video/x", lambda: loads.append("b") or {"base": 99}) == {"base": 10}   # kept
    two.changed("pricing")                                                       # an admin changed a price there
    assert one.cached("pricing", "video/x", lambda: loads.append("c") or {"base": 12}) == {"base": 12}
    assert loads == ["a", "c"]
    assert one.cached("settings", "missing", lambda: None) is None               # a setting that is not there


def test_rate_limits_and_wrong_passwords_count_across_processes():
    server = fakeredis.FakeServer()
    one, two = shared.SharedRateLimit(process(server)), shared.SharedRateLimit(process(server))
    assert [one.allow("ip:1", 3, 60), two.allow("ip:1", 3, 60), one.allow("ip:1", 3, 60)] == [True, True, True]
    assert two.allow("ip:1", 3, 60) is False and one.allow("ip:1", 3, 60) is False    # the fourth, wherever it comes
    assert 1 <= two.retry_after("ip:1", 60) <= 61 and one.allow("ip:2", 3, 60)       # another key is its own
    throttle_one, throttle_two = shared.SharedLoginThrottle(process(server)), shared.SharedLoginThrottle(process(server))
    for _ in range(5):
        throttle_one.fail("ada@example.com|1.2.3.4")
    assert throttle_two.blocked("ada@example.com|1.2.3.4") and not throttle_two.blocked("eve@example.com|1.2.3.4")
    throttle_two.clear("ada@example.com|1.2.3.4")
    assert not throttle_one.blocked("ada@example.com|1.2.3.4")


class Page:
    """An open page's socket."""
    def __init__(self):
        self.got = []

    async def send_text(self, text):
        self.got.append(text)


def test_a_live_message_reaches_the_process_that_has_the_page_open():
    from scene.main import Hub

    async def run():
        server = fakeredis.FakeServer()
        hubs = []
        for _ in range(2):   # two processes, each with its own Hub, its own clients
            hub = Hub()
            hub.loop = asyncio.get_running_loop()
            hub.shared = process(server)
            hub.offload = lambda fn, *a: asyncio.to_thread(fn, *a)
            hubs.append(hub)
        listening = [asyncio.create_task(h.shared.listen(h.deliver)) for h in hubs]
        await asyncio.sleep(0.2)
        page, console = Page(), Page()
        hubs[1].add(5, page)                 # user 5's page is open on the second process
        hubs[1].watchers.add(console)        # and a console page
        changes = []
        hubs[1].shared.on_changed("settings", lambda: changes.append("reloaded"))
        hubs[0].send(5, json.dumps({"jobs": []}))   # the first process has news for user 5
        hubs[0].tell({"online_users": 3})
        hubs[0].shared.changed("settings")
        for _ in range(50):
            await asyncio.sleep(0.05)
            if page.got and len(console.got) >= 2 and changes:
                break
        for task in listening:
            task.cancel()
        return page.got, console.got, changes

    page, console, changes = asyncio.run(run())
    assert page == [json.dumps({"jobs": []})]
    assert json.dumps({"online_users": 3}) in console and changes == ["reloaded"]


@pytest.fixture
def on_redis(monkeypatch):
    """The app with Redis on (fakeredis behind it)."""
    server = fakeredis.FakeServer()
    monkeypatch.setattr(shared, "open_shared", lambda url: process(server))
    return server


def test_the_app_on_redis_caches_settings_and_shares_its_limits(on_redis, client):
    state = client.app.state
    assert state.shared.enabled and isinstance(state.limits, shared.SharedRateLimit)
    state.db.set_setting("announcement", "first")
    assert state.db.setting("announcement") == "first"
    state.db.run("UPDATE settings SET value = 'changed underneath' WHERE key = 'announcement'")
    assert state.db.setting("announcement") == "first"            # from the cache
    state.db.set_setting("announcement", "second")                 # a change through the app drops it everywhere
    assert state.db.setting("announcement") == "second"
    answers = [client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"}).status_code
               for _ in range(7)]
    assert answers[:5] == [401] * 5 and 429 in answers[5:]         # the throttle, counted in Redis
