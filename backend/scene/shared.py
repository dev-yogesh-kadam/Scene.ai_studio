"""What the studio's processes share, when there is more than one process: Redis (`redis_url`,
off by default). With it off, everything here is what it always was, in this process alone.

- a cache with invalidation: settings (db.setting), pricing (credits.pricing), and any named list that changes rarely
  (`cached`); a change anywhere drops it everywhere (`changed`, which also tells every other process's listeners:
  `on_changed`, for what a process keeps in memory: the console's roles, the agent's models).
- live messages: what Hub sends to a user's open pages, or to the console's, reaches the process that has them open
  (pub/sub, one subscriber task per process).
- rate limits and sign-in throttles counted across processes (sorted sets, a sliding window).

Redis is a network call: the code calls it from the database's threads (db.offload), never on the event loop, but for
the subscriber, which is asyncio's own client. Memurai or Redis on this machine: `redis://127.0.0.1:6379/0`; a
`rediss://` URL is the same over TLS.
"""

import asyncio
import json
import time
import uuid

PREFIX = "scene:"
LIVE = PREFIX + "live"          # channel: {"user": id or None for the console, "text": message} and {"drop": id}
CHANGED = PREFIX + "changed"    # channel: the name of what changed ("pricing", "settings", "workflows", ...)


class Shared:
    """Nothing shared (`url` empty): this process only, as before."""

    enabled = False

    def __init__(self):
        self.listeners = {}   # name -> [functions told when it changes]

    def cached(self, name, key, loader, seconds=300):
        return loader()

    def changed(self, name):
        """Something of `name` changed in this process: with one process, nothing else is to be told."""

    def on_changed(self, name, fn):
        """`fn()` is called when another process changes something of `name` (what this process keeps in memory)."""
        self.listeners.setdefault(name, []).append(fn)

    def _told(self, name):
        for fn in self.listeners.get(name, ()):
            fn()

    def publish(self, message):
        raise RuntimeError("Nothing to publish to: redis_url is not set")

    async def listen(self, deliver):
        return None

    def close(self):
        pass


class RedisShared(Shared):
    enabled = True

    def __init__(self, url, client=None, async_client=None):
        super().__init__()
        import redis
        import redis.asyncio
        self.url = url
        # rediss:// is TLS: the server's certificate is checked, as redis-py does by default.
        self.redis = client or redis.Redis.from_url(url, decode_responses=True, health_check_interval=30)
        self.async_redis = async_client or redis.asyncio.Redis.from_url(url, decode_responses=True)
        self.me = uuid.uuid4().hex[:8]   # this process, so it knows its own news

    # ---------------------------------------------------------------- cache

    def _version(self, name):
        return self.redis.get(PREFIX + "v:" + name) or "0"

    def cached(self, name, key, loader, seconds=300):
        """`loader()` kept in Redis for `seconds`, under the name's current version: a change drops every key of it."""
        where = "{}c:{}:{}:{}".format(PREFIX, name, self._version(name), key)
        found = self.redis.get(where)
        if found is not None:
            return json.loads(found)
        value = loader()
        self.redis.set(where, json.dumps(value), ex=seconds)
        return value

    def changed(self, name):
        """Something of `name` changed: its cache is dropped (a new version) and every process's listeners are told."""
        self.redis.incr(PREFIX + "v:" + name)
        self.redis.publish(CHANGED, json.dumps({"name": name, "from": self.me}))   # this process changed it itself

    # ---------------------------------------------------------------- live messages

    def publish(self, message):
        self.redis.publish(LIVE, json.dumps(message))

    async def listen(self, deliver):
        """Run for as long as the app does: each live message to `deliver(message)`, each change to the listeners."""
        while True:
            try:
                pubsub = self.async_redis.pubsub()
                await pubsub.subscribe(LIVE, CHANGED)
                async for item in pubsub.listen():
                    if item.get("type") != "message":
                        continue
                    data = json.loads(item["data"])
                    if item["channel"] == CHANGED:
                        if data.get("from") != self.me:   # another process's change; its listeners read: off the loop
                            await asyncio.to_thread(self._told, data["name"])
                    else:
                        deliver(data)
            except asyncio.CancelledError:
                raise
            except Exception as error:   # Redis restarted, or the network blinked: listen again
                print("Live messages from Redis stopped ({}); listening again.".format(error))
                await asyncio.sleep(2)

    # ---------------------------------------------------------------- counting

    def hits(self, key, seconds, count=True, limit=None):
        """How many hits `key` had in the last `seconds` (a sorted set of times); with `count`, this one is added unless
        that makes more than `limit`. Returns (hits before this one, the oldest's time)."""
        now = time.time()
        where = PREFIX + "rate:" + key
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(where, 0, now - max(seconds, 3600))
        pipe.zrangebyscore(where, now - seconds, now, withscores=True)
        _, recent = pipe.execute()
        if count and (limit is None or len(recent) < limit):
            self.redis.zadd(where, {"{}:{}".format(now, uuid.uuid4().hex[:6]): now})
            self.redis.expire(where, max(seconds, 3600))
        return len(recent), (recent[0][1] if recent else now)

    def close(self):
        self.redis.close()


def open_shared(url):
    return RedisShared(url) if url else Shared()


class SharedRateLimit:
    """security.RateLimit, counted in Redis: the same answers, across processes. Sync: call it off the loop."""

    remote = True

    def __init__(self, shared):
        self.shared = shared

    def allow(self, key, limit, seconds):
        before, _ = self.shared.hits("limit:" + key, seconds, limit=limit)
        return before < limit

    def retry_after(self, key, seconds):
        _, oldest = self.shared.hits("limit:" + key, seconds, count=False)
        return max(1, int(oldest + seconds - time.time()) + 1)


class SharedLoginThrottle:
    """security.LoginThrottle, counted in Redis: five wrong passwords block a key on every process."""

    remote = True

    def __init__(self, shared):
        self.shared = shared

    def blocked(self, key, limit=None, seconds=None):
        from .security import LOCK_SECONDS, MAX_FAILURES
        limit, seconds = limit or MAX_FAILURES, seconds or LOCK_SECONDS
        before, _ = self.shared.hits("login:" + key, seconds, count=False)
        return before >= limit

    def fail(self, key):
        self.shared.hits("login:" + key, 900)

    def clear(self, key):
        self.shared.redis.delete(PREFIX + "rate:login:" + key)
