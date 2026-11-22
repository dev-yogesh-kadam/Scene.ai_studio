"""The router: given a model (and its capability), which provider and key runs it.

1. The providers that offer the model (their keys' cached /v1/models), switched on, and their keys switched on and not
   found invalid. None at all: the job fails at once, saying so ("No provider has a key for Seedance 2.5: add one in
   Servers & APIs → Providers"), and its credits come back.
2. Of those, leave out keys in cooldown, at their most at once (max_concurrent, else what whoami said, else 1) and over
   their daily cap (studio credits of today's jobs on that key).
3. A key that is ready first: its last check found it well (status "ok"), and for On this PC its tool was found
   installed. So when On this PC and a Scene provider both offer a model (transcribe, separate_voice), the one that can
   run it is picked. On this PC is not a candidate at all where it is not offered (local.offered: no Python there, as on
   Zoro, or SCENE_LOCAL_TOOLS=off).
4. Then the least busy (running ÷ allowed); ties by the provider's priority, then the key's (lower first), then age.

What a call's problem means (base.py):
- KeyProblem: the key is marked (status, cooldown_until: retry_after else 60 s; 1 h for no_credit; until fixed for
  invalid) and the next key is tried, once.
- ProviderProblem: the next provider offering the same model is tried, once.
- RequestProblem: never retried; the job fails with the provider's words.

Every job of a model runs this way: the Scene providers (v1.py) and On this PC (local.py) are the only places models
come from."""

import asyncio
import time

from ..db import as_everyone, offload
from . import registry
from .anthropic_api import Anthropic
from .base import KeyProblem, ProviderProblem, RequestProblem
from . import local
from .local import LocalTools
from .v1 import V1

COOL_DEFAULT = 60          # seconds a rate-limited key rests when the provider did not say
COOL_NO_CREDIT = 3600      # an hour for a key out of credit
FRESH = 5                  # seconds the candidates of a model are kept between looks
SPEND_FRESH = 10           # seconds a key's spend today is kept
REFRESH_EVERY = 600        # seconds between two reads of each key's models (registry.save_models)
FIRST_WAIT = 30            # seconds after the start before the first read
VOICES_FRESH = 600         # seconds a provider's voice list is kept
SPEECH = "speech"          # the voiceover model's id at a Scene provider (its capability as its id)


def local_tools(settings):
    """The tools on this PC (local.py), with the Python, work folder and model folder the settings give."""
    if settings is None:
        return LocalTools()
    storage = settings.path("storage_dir")
    return LocalTools(python=str(settings.path("local_tools_python")), work_dir=str(storage / "cache" / "local_tools"),
                      models_dir=str(storage / "models"), switch=getattr(settings, "local_tools", "auto"))


class NoProvider(Exception):
    """No provider could ever run it (no key at all, or only broken ones): the job fails at once with these words."""


class Choice(dict):
    """{"provider": row, "key": row, "model": row, "secret"}: what runs one call. The secret never leaves the call."""

    @property
    def label(self):
        return "{} · {}".format(self["provider"]["name"], self["key"]["label"])

    def described(self):
        """What a job's log and Langfuse may carry: names and labels, never the key."""
        return {"provider": self["provider"]["name"], "provider_id": self["provider"]["id"], "kind": self["provider"]["kind"],
                "model": self["model"]["model_id"], "key": self["key"]["label"], "key_id": self["key"]["id"]}


class Router:
    def __init__(self, db, settings=None):
        self.db = db
        self.settings = settings
        self.running = {}          # key id -> the ids of the studio's jobs running with it now
        self._candidates = {}      # model id -> (when, [Choice without secret])
        self._spend = {}           # key id -> (when, credits today)
        self.adapters = {}         # tests put adapters here: provider id -> Adapter
        self._voices = {}          # (q, language) -> (when, voices, words)

    # ------------------------------------------------------------ adapters

    def adapter(self, provider):
        if provider["id"] in self.adapters:
            return self.adapters[provider["id"]]
        kind = provider["kind"]
        if kind == "scene_provider_v1":
            return V1(provider["base_url"])
        if kind == "anthropic":
            return Anthropic(provider["base_url"])
        if kind == LocalTools.kind:
            return local_tools(self.settings)
        raise ValueError("No adapter for providers of kind {}.".format(kind))

    # ------------------------------------------------------------ what can run a model

    def forget(self):
        """The registry changed (a key added, a model list read): look again."""
        self._candidates.clear()

    def candidates(self, model_id):
        """Every (provider, key, model) that could ever run this model: switched on, not invalid, and not On this PC
        where it is not offered (its models may still be cached from a database made elsewhere). Kept FRESH seconds."""
        kept = self._candidates.get(model_id)
        if kept and time.time() - kept[0] < FRESH:
            return kept[1]
        here = local.offered_by(self.settings)
        with as_everyone():
            rows = self.db.all(
                "SELECT m.model_id, m.name AS model_name, m.capability, m.typical_seconds, m.can_cancel, "
                "p.id AS p_id, p.kind AS p_kind, p.name AS p_name, p.base_url AS p_url, p.priority AS p_priority, "
                "k.id AS k_id, k.label AS k_label, k.priority AS k_priority, k.max_concurrent, k.daily_cap, k.status, "
                "k.cooldown_until, k.info FROM provider_models m JOIN provider_keys k ON k.id = m.key_id "
                "JOIN providers p ON p.id = m.provider_id WHERE m.model_id = ? AND p.active = 1 AND k.active = 1 "
                "AND k.status <> 'invalid' ORDER BY p.priority, p.id, k.priority, k.id", (str(model_id),))
        found = []
        for r in rows:
            if r["p_kind"] == LocalTools.kind and not here:
                continue
            found.append(Choice(
                provider={"id": r["p_id"], "kind": r["p_kind"], "name": r["p_name"], "base_url": r["p_url"], "priority": r["p_priority"]},
                key={"id": r["k_id"], "label": r["k_label"], "priority": r["k_priority"], "max_concurrent": r["max_concurrent"],
                     "daily_cap": r["daily_cap"], "status": r["status"], "cooldown_until": r["cooldown_until"],
                     "info": registry._json(r["info"]) or {}},
                model={"model_id": r["model_id"], "name": r["model_name"], "capability": r["capability"],
                       "typical_seconds": r["typical_seconds"], "can_cancel": bool(r["can_cancel"])}))
        self._candidates[model_id] = (time.time(), found)
        return found

    def name_of(self, model_id):
        with as_everyone():
            row = self.db.one("SELECT name FROM provider_models WHERE model_id = ? ORDER BY seen_at DESC LIMIT 1", (str(model_id),))
        return (row or {}).get("name") or str(model_id)

    def allowed(self, key):
        """How many of the studio's jobs one key runs at once: its max_concurrent, else what whoami said, else 1."""
        said = (key.get("info") or {}).get("key") or {}
        for value in (key.get("max_concurrent"), said.get("max_concurrent")):
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
        return 1

    def busy(self, key_id):
        return len(self.running.get(key_id) or ())

    def spent_today(self, key_id):
        """Studio credits of today's jobs (since local midnight) that ran with this key, kept SPEND_FRESH seconds."""
        kept = self._spend.get(key_id)
        if kept and time.time() - kept[0] < SPEND_FRESH:
            return kept[1]
        midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        with as_everyone():
            row = self.db.one("SELECT COALESCE(SUM(cost), 0) AS n FROM jobs WHERE provider_key = ? AND started >= ? "
                              "AND status IN ('running', 'done')", (int(key_id), midnight))
        spent = (row or {}).get("n") or 0
        self._spend[key_id] = (time.time(), spent)
        return spent

    def why_not(self, choice, now=None):
        """Why this key can't take a job now, or "": cooling down, full, or over its daily cap."""
        now = now or time.time()
        key = choice["key"]
        if key.get("cooldown_until") and key["cooldown_until"] > now:
            return "cooling down"
        if self.busy(key["id"]) >= self.allowed(key):
            return "full"
        if key.get("daily_cap") is not None and self.spent_today(key["id"]) >= key["daily_cap"]:
            return "over its daily cap"
        return ""

    def ready(self, choice):
        """Whether this key is ready to run its model: its last check found it well (status "ok": a key not checked yet
        is "unknown"), and for On this PC its tool was found installed at the last look (local.ready_now)."""
        if choice["key"].get("status") != "ok":
            return False
        if choice["provider"]["kind"] == LocalTools.kind:
            python = str(self.settings.path("local_tools_python")) if self.settings is not None else ""
            return local.ready_now(python, choice["model"]["model_id"])
        return True

    def pick(self, model_id, skip_keys=(), skip_providers=()):
        """(Choice or None, problem). A Choice when a key can run it now; (None, "") when every key that could is busy,
        cooling down or over its cap (the job waits); (None, words) when none ever could (the job fails)."""
        every = self.candidates(model_id)
        if not every:
            return None, NO_KEY.format(name=self.name_of(model_id))
        now = time.time()
        free = [c for c in every if c["key"]["id"] not in skip_keys and c["provider"]["id"] not in skip_providers
                and not self.why_not(c, now)]
        if not free:
            return None, ""
        free.sort(key=lambda c: (not self.ready(c), self.busy(c["key"]["id"]) / self.allowed(c["key"]), c["provider"]["priority"],
                                 c["provider"]["id"], c["key"]["priority"], c["key"]["id"]))
        return free[0], ""

    def with_secret(self, choice):
        """The Choice with its key's secret, read just before the call."""
        row = registry.key(self.db, choice["key"]["id"])
        return Choice(choice, secret=registry.secret_of(row) if row else "")

    # ------------------------------------------------------------ while a job runs

    def take(self, choice, job_id):
        self.running.setdefault(choice["key"]["id"], set()).add(job_id)
        self._spend.pop(choice["key"]["id"], None)

    def release(self, choice, job_id):
        held = self.running.get(choice["key"]["id"])
        if held is not None:
            held.discard(job_id)
            if not held:
                self.running.pop(choice["key"]["id"], None)

    def cool(self, choice, problem):
        """A KeyProblem's key marked: its status and how long it rests. Its error in words, never the key."""
        status = problem.status
        if status == "invalid":
            until = None   # until it is fixed (a new key pasted, or Test finds it works)
        elif status == "no_credit":
            until = time.time() + max(COOL_NO_CREDIT, problem.retry_after or 0)
        elif status == "rate_limited":
            until = time.time() + (problem.retry_after if problem.retry_after else COOL_DEFAULT)
        else:   # not allowed this model: the key is fine, only not for this
            registry.mark(self.db, choice["key"]["id"], error=str(problem), checked=False)
            return
        registry.mark(self.db, choice["key"]["id"], status=status, cooldown_until=until, error=str(problem))
        self.forget()

    async def run(self, model_id, attempt, job_id=None, first=None):
        """Run `attempt(choice)` (an async call to the provider with the Choice, its secret in it) on the key the router
        picks, failing over as the problem says: a KeyProblem tries the next key once, a ProviderProblem the next
        provider once, a RequestProblem never. Returns (result, the Choice that ran it, still taken for `job_id`: the
        caller releases it when the job ends). Raises NoProvider when nothing could ever run it, ProviderProblem when the
        keys that could are all busy after a failover, and the last problem when the failover did not help; a key taken
        for a call that failed is released here. `first`: a Choice already picked (and taken) by the queue."""
        skip_keys, skip_providers, key_tried, provider_tried = set(), set(), False, False
        choice = first
        while True:
            if choice is None:
                choice, problem = await offload(self.pick, model_id, skip_keys, skip_providers)
                if problem:
                    raise NoProvider(problem)
                if choice is None:
                    raise ProviderProblem("Every key that can make {} is busy or resting: try again in a moment.".format(
                        await offload(self.name_of, model_id)))
                if job_id is not None:
                    self.take(choice, job_id)
            try:
                armed = await offload(self.with_secret, choice)
                result = await attempt(armed)
            except (KeyProblem, ProviderProblem, RequestProblem) as problem:
                if job_id is not None:
                    self.release(choice, job_id)
                if isinstance(problem, KeyProblem):
                    await offload(self.cool, choice, problem)
                    if key_tried:
                        raise
                    key_tried = True
                    skip_keys.add(choice["key"]["id"])
                elif isinstance(problem, ProviderProblem):
                    if provider_tried:
                        raise
                    provider_tried = True
                    skip_providers.add(choice["provider"]["id"])
                else:
                    raise
                choice = None
                continue
            except BaseException:   # cancelled, or anything else: the key is not held
                if job_id is not None:
                    self.release(choice, job_id)
                raise
            healed = {"status": "ok", "cooldown_until": None, "error": ""} if choice["key"]["status"] != "ok" else {}
            await offload(registry.mark, self.db, choice["key"]["id"], used=True, **healed)
            if healed:
                self.forget()
            return result, armed   # with its secret: the caller follows the job with the same key

    # ------------------------------------------------------------ the voices of the speech model

    async def voices(self, q="", language=""):
        """(voices, words): the voice library of a provider whose key has the speech model ("speech"), asked with the
        first key that has it, kept VOICES_FRESH seconds per question. Words say why there are none: no key has speech,
        or its provider has no voice list yet."""
        wanted = (str(q or "").strip()[:100], str(language or "").strip()[:20])
        kept = self._voices.get(wanted)
        if kept and time.time() - kept[0] < VOICES_FRESH:
            return kept[1], kept[2]
        every = [c for c in await offload(self.candidates, SPEECH) if c["provider"]["kind"] == "scene_provider_v1"]
        if not every:
            return [], "No provider key has the voiceover model yet: add one in Servers & APIs → Providers."
        words, found = "", None
        for choice in every[:2]:   # a second key if the first is refused
            try:
                armed = await offload(self.with_secret, choice)
                found = await (await offload(self.adapter, choice["provider"])).voices(armed["secret"], *wanted)
                break
            except (KeyProblem, ProviderProblem, RequestProblem) as problem:
                words = "The voices could not be read: {}".format(problem)
        if found is None and not words:
            words = "{} has no voice list yet: type a voice id.".format(every[0]["provider"]["name"])
        found = found or []
        if found or not words.startswith("The voices could not"):
            self._voices[wanted] = (time.time(), found, words)
        return found, words

    # ------------------------------------------------------------ the models each key unlocks

    async def check_key(self, provider, key_row, secret=None):
        """Ask a provider about one key now: whoami and its models. Saves what was learned (status, models, whoami)
        and returns {"ok", "models", "credits", "alerts", "error", "status"}."""
        adapter = await offload(self.adapter, provider)
        secret = registry.secret_of(key_row) if secret is None else secret
        try:
            said = await adapter.whoami(secret)
            found = await adapter.models(secret)
        except KeyProblem as problem:
            status = problem.status or "unknown"
            await offload(registry.mark, self.db, key_row["id"], status=status,
                                    cooldown_until=None if status in ("invalid", "unknown") else time.time() + (problem.retry_after or COOL_DEFAULT),
                                    error=str(problem))
            self.forget()
            return {"ok": False, "status": status, "error": str(problem), "models": 0}
        except (ProviderProblem, RequestProblem) as problem:
            await offload(registry.mark, self.db, key_row["id"], error=str(problem))
            return {"ok": False, "status": key_row.get("status") or "unknown", "error": str(problem), "models": 0}
        await offload(registry.mark, self.db, key_row["id"], status="ok", cooldown_until=None, error="", info=said)
        await offload(registry.save_models, self.db, provider["id"], key_row["id"], found)
        self.forget()
        return {"ok": True, "status": "ok", "error": "", "models": len(found),
                "credits": (said.get("credits") or {}).get("available") if isinstance(said.get("credits"), dict) else None,
                "alerts": said.get("alerts") or []}

    async def refresh(self):
        """Every active key of every active provider asked again (its whoami and models). A key that can't be read keeps
        its last good list."""
        rows = await offload(registry.providers, self.db, True)
        for provider in rows:
            for key_row in await offload(registry.keys, self.db, provider["id"]):
                if not key_row["active"]:
                    continue
                try:
                    await self.check_key(provider, key_row)
                except Exception as error:   # one provider never stops the others being read
                    print("Provider {} key {}: its models could not be read ({}).".format(provider["name"], key_row["label"], error))

    async def run_forever(self, first_wait=FIRST_WAIT):
        await asyncio.sleep(first_wait)   # the app starts first; the console's Test asks at once
        while True:
            try:
                await self.refresh()
            except Exception as error:
                print("The providers' models could not be read: {}".format(error))
            await asyncio.sleep(REFRESH_EVERY)


NO_KEY = "No provider has a key for {name}: add one in Servers & APIs → Providers."
