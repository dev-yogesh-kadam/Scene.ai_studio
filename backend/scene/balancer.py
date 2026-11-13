"""The load balancer of the renders: which render server each waiting job goes to, and when.

Each server of the console's Servers section (endpoints.py) has
- what it can do:
  - "Workflows" (endpoints.models): patterns of the workflow ids it takes, fnmatch style, matched against the whole id
    (video/generation_video) and the file's name (generation_video), e.g. "generation_*". A server with patterns
    takes only the workflows they match; what the admin typed is all it can do (the generation server runs only its
    own nodes). A workflow that some server's patterns claim goes only to the servers that claim it.
  - A server left without patterns whose nodes turn out to be only the generation server's (Generation…) is taken as
    one with GENERATION_ONLY: the generation server, added without its Workflows. Otherwise the nodes of its workflows'
    pages (PrimitiveInt…) it never runs would rule it out, and its renders would wait for another server for ever.
  - A server without patterns takes every workflow no server claims, when it has the nodes the workflow uses. Its node
    definitions (/object_info) are read the first time a render could go there, and again every NODES_FRESH
    seconds; while they are not known (the server did not answer, or has no /object_info) it is taken to have them.
- how much it runs at once: "Jobs at once" (endpoints.slots). A ComfyUI server renders one at a time (1); the
  generation server takes several, as it spreads them over its provider accounts itself.

The queue's worker (jobs.py) goes through the waiting renders in queue order and gives each one, of the servers that
can do it, the least busy one with a slot free (running / slots, the main server first on a tie) that answers. A render
no free server can do now waits, but never holds up the renders behind it that another server can do. A render no
server in use could ever do fails at once, saying why, instead of waiting for ever.
"""

import asyncio
import fnmatch
import time

import httpx

from .comfy.client import Comfy

NODES_FRESH = 1800   # seconds a server's node definitions are trusted before they are read again
NODES_RETRY = 60     # seconds before asking again a server whose node definitions could not be read
NODES_WAIT = 20      # seconds a placement waits for node definitions; past it the server is taken to have the nodes
# Nodes of the ComfyUI page that never reach a server's graph: never asked of a server.
FRONTEND_ONLY = frozenset({"Note", "MarkdownNote", "Reroute", "PrimitiveNode"})
GENERATION_ONLY = ["generation_*"]   # what a server with only the generation server's nodes takes, when no one said


def patterns_of(models):
    """The patterns of an endpoints row's `models` ("generation_*, video/x"): lower case, empty ones left out."""
    return [p.strip().lower() for p in str(models or "").replace("\n", ",").split(",") if p.strip()]


def matches(patterns, workflow_id):
    """Whether one of the patterns takes the workflow: against its whole id or the file's name."""
    whole = str(workflow_id or "").lower()
    name = whole.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(whole, p) or fnmatch.fnmatchcase(name, p) for p in patterns)


def needs_of(wf):
    """The node classes a loaded workflow (catalog.load) runs: muted, bypassed and page-only nodes left out."""
    info = wf.get("info") or {}
    found = set()
    for nid, node in (wf.get("nodes") or {}).items():
        meta = info.get(nid) or {}
        if isinstance(node, dict) and node.get("class_type") and meta.get("mode", 0) == 0 and not meta.get("virtual"):
            found.add(str(node["class_type"]))
    return frozenset(found - FRONTEND_ONLY)


def _slots(value):
    try:
        return max(1, min(16, int(value)))   # endpoints.MOST_SLOTS
    except (TypeError, ValueError):
        return 1


class ComfyPool:
    """The render servers, what each can do, and the studio's renders running on each now."""

    def __init__(self, db, fallback):
        self.db = db
        self.fallback = fallback.rstrip("/") if fallback else ""   # config.json's, while none is in the table
        self.main = Comfy(self.main_url)   # the main server (app.state.comfy)
        self.clients = {}
        self.busy = {}    # url -> the ids of the studio's jobs running there
        self.nodes = {}   # url -> (frozenset of its node classes, or None while not known, when it was asked)
        self.reading = {}  # url -> the task reading its node definitions now
        # The comfy rows of the endpoints table, read at start and again after each change (reload): the address is
        # asked for on every request to the render server, which must not wait for the database.
        self.rows = self._read()

    def _read(self):
        from .endpoints import listed   # endpoints imports this module
        return listed(self.db, "comfy")

    def reload(self):
        """Read the servers again after the console changed them (a database thread). Their nodes are asked again."""
        self.rows = self._read()
        self.nodes = {}

    # ------------------------------------------------------------ the servers

    def servers(self):
        """[{"name", "url", "patterns", "slots"}] of the servers a render may go to now, the main one first."""
        rows = self.rows
        if not rows:
            return [{"name": "", "url": self.fallback, "patterns": [], "slots": 1}] if self.fallback else []
        return [{"name": r["name"], "url": r["url"], "patterns": self.patterns(r), "slots": _slots(r.get("slots"))}
                for r in rows if r["active"] and r["url"]]

    def patterns(self, row):
        """The workflows a server row takes: its Workflows, or GENERATION_ONLY for the generation server left without."""
        given = patterns_of(row.get("models"))
        if given:
            return given
        known = (self.nodes.get(row["url"]) or (None, 0))[0]
        return list(GENERATION_ONLY) if known and all(n.startswith("Generation") for n in known) else []

    def main_url(self):
        every = self.servers() or [{"url": r["url"]} for r in self.rows[:1]]
        return every[0]["url"] if every else self.fallback

    def client(self, url):
        """The client of one server: the main one is app.state.comfy itself."""
        if url == self.main.url:
            return self.main
        if url not in self.clients:
            self.clients[url] = Comfy(lambda: url)
        return self.clients[url]

    def capacity(self):
        """How many renders the servers in use run at once, all together."""
        return sum(s["slots"] for s in self.servers()) or 1

    def running(self, url):
        return len(self.busy.get(url) or ())

    def take(self, url, job_id):
        self.busy.setdefault(url, set()).add(job_id)

    def release(self, url, job_id):
        held = self.busy.get(url)
        if held is not None:
            held.discard(job_id)
            if not held:
                self.busy.pop(url, None)

    # ------------------------------------------------------------ what each can do

    def lacks(self, url, needs):
        """The node classes of `needs` the server is known not to have (none while its nodes are not known)."""
        known = (self.nodes.get(url) or (None, 0))[0]
        return frozenset() if known is None else frozenset(needs) - known

    async def learn(self, urls):
        """Read the node definitions of these servers where they are not known or are old, all at once, waiting at
        most NODES_WAIT seconds. A server that does not answer is asked again after NODES_RETRY seconds."""
        now = time.time()
        due = []
        for url in dict.fromkeys(urls):
            known, when = self.nodes.get(url) or (None, 0)
            if now - when > (NODES_FRESH if known is not None else NODES_RETRY) or url not in self.nodes:
                if url not in self.reading:
                    self.reading[url] = asyncio.ensure_future(self._read_nodes(url))
                due.append(self.reading[url])
        if due:
            await asyncio.wait(due, timeout=NODES_WAIT)

    async def _read_nodes(self, url):
        try:
            info = await self.client(url).object_info()
            self.nodes[url] = (frozenset(info) if isinstance(info, dict) and info else None, time.time())
        except (httpx.HTTPError, ValueError):
            self.nodes[url] = (None, time.time())
        finally:
            self.reading.pop(url, None)

    def route(self, workflow_id, needs=frozenset()):
        """(the servers in use that can do the workflow, busy or not; why none can, or ""). Node definitions are taken
        as they are known now (learn reads them)."""
        every = [r for r in self.rows if r["url"]]
        live = self.servers()
        claimers = [r for r in every if matches(self.patterns(r), workflow_id)]
        if claimers:
            can = [s for s in live if matches(s["patterns"], workflow_id)]
            if can:
                return can, ""
            return [], "{} is made only on {}, which is switched off in the console (Servers & APIs).".format(
                workflow_id, " or ".join(r["name"] for r in claimers))
        can = [s for s in live if not s["patterns"]]
        if not can:
            return [], ("No render server takes {}: every server in use takes only the workflows its \"Workflows\" "
                        "names. Add the workflow there, or a server that takes any, in the console (Servers & APIs).").format(workflow_id)
        has = [s for s in can if not self.lacks(s["url"], needs)]
        if has:
            return has, ""
        missing = sorted(frozenset.intersection(*(self.lacks(s["url"], needs) for s in can)) or
                         frozenset.union(*(self.lacks(s["url"], needs) for s in can)))
        if any(m.startswith("Generation") for m in missing):
            return [], ("No render server takes generation workflows: add the generation server in the admin console "
                        "(Servers & APIs) with Workflows = generation_*.")
        return [], "No render server in use has the nodes {} needs: {}.".format(workflow_id, ", ".join(missing))

    async def place(self, workflow_id, needs=frozenset(), answers=None, asked=None):
        """Where one waiting render goes now: (server or None, whether one that can do it answers or runs a render,
        why no server could ever do it, or ""). `answers`: async function(url) -> bool; without it a free server is
        taken without asking it. `asked`: url -> its answer, shared by the placements of one look at the queue."""
        if needs:
            await self.learn(s["url"] for s in self.servers() if not s["patterns"])
        can, problem = self.route(workflow_id, needs)
        if problem:
            return None, False, problem
        asked = {} if asked is None else asked
        alive = any(self.running(s["url"]) for s in can)
        order = {s["url"]: i for i, s in enumerate(can)}
        free = sorted((s for s in can if self.running(s["url"]) < s["slots"]),
                      key=lambda s: (self.running(s["url"]) / s["slots"], order[s["url"]]))
        for s in free:
            if answers is not None:
                if s["url"] not in asked:
                    asked[s["url"]] = await answers(s["url"])
                if not asked[s["url"]]:
                    continue
            return s, True, ""
        return None, alive or bool(free and answers is None), ""

    async def answers(self, url):
        try:
            await self.client(url).stats()
            return True
        except (httpx.HTTPError, ValueError):
            return False

    async def close(self):
        for task in list(self.reading.values()):
            task.cancel()
        for c in [self.main, *self.clients.values()]:
            await c.http.aclose()
