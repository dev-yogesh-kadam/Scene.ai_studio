"""Each call of the agent's models sent to Langfuse as well (docs/langfuse.md, docs/observability.md), when a Langfuse
server is set and in use in the console's Servers section: its address, and its project's two keys kept as
"public:secret", encrypted (vault.py).

traces.Recorder hands every call it writes down to `add`, which only puts it in a list: nothing here can slow or fail a
user's answer. `run_forever` sends what waits every few seconds, as OpenTelemetry spans (Langfuse 4 takes traces only
that way, at /api/public/otel/v1/traces). What one turn of the agent asked is one trace (traces.RUN), named for what it
was ("Agent turn", "Film run"), with the skills it used as tags and the versions of the system prompt and of those
skills (a short hash of their text) in its metadata; the Agent tab of a project is one session (traces.SESSION). Each
call is a generation named by its purpose, with its model, tokens, what Anthropic charges for them in dollars
(credits.CLAUDE_PRICES) and what that comes to in the studio's credits and rupees, the words sent and the answer. The
renders a turn made join its trace as spans (`span`, from jobs.py); a render nobody asked the agent for has a trace of
its own, "Render".

What the users think of a result (their thumbs, a still approved or made again) goes as a score (`score`), at
/api/public/ingestion, which in Langfuse 4 takes scores only. Saved agent turns go to a dataset, and an evaluation of
them to a dataset run (`push_dataset`, `dataset_run`, for backend/evals).

Nothing that looks like a key, a token or a password is sent: every word goes through `redact` first (emails are kept:
they say who a user is).

Settings, in the console's Settings: langfuse_words ("0": no words are sent, only names, models, numbers and times),
langfuse_grade_share (the share of turns, in percent, the fast model grades; see workspace.py) and langfuse_owns_words
("1": the words are kept in Langfuse only, once it has them; off by default, see `owns_words`).

With no Langfuse in use the calls are let go. While one does not answer, at most KEEP wait for it to come back (the
oldest go first, and how many went is counted: `status`, shown by health.py and the Servers card).
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import quote

import httpx

from . import endpoints, vault
from .credits import Credits
from .db import offload

EVERY = 3        # seconds between two sendings
BATCH = 100      # calls in one request at most
KEEP = 1000      # calls kept waiting at most while Langfuse does not answer; the oldest go first
PATH = "/api/public/otel/v1/traces"
SCORES = "/api/public/ingestion"   # Langfuse 4 takes only scores there
LONGEST = 50000  # characters of one message (or one answer) sent at most: a long skill is cut, so Langfuse stays small
NAMES = ("Agent turn", "Film run", "Render")   # what a trace can be called
LINK_KEPT = 300  # seconds the console's link to Langfuse (its address and project) is kept before it is asked again
REFUSED = (400, 413, 422)   # Langfuse will never take this batch as it is: let go (and counted), not tried for ever
VERSIONS_KEPT = 60          # seconds the hashes of the system prompt and the skills are kept before they are made again
WHO_KEPT = 300              # seconds a user's email is kept before it is read again (an email changed shows by then)
WORDS_OFF = "An error (its words are not sent to Langfuse: langfuse_words is off)."


def trace_id(run):
    """The Langfuse trace of a run (traces.RUN): the same run always gives the same trace, a new one each time without one."""
    return hashlib.sha256(run.encode("utf-8")).hexdigest()[:32] if run else os.urandom(16).hex()


def call_span(call_id):
    """The span (Langfuse's observation id) of one call of agent_calls: always the same for the same call, so its words
    can be read back from Langfuse (`Sender.exchange`) and a call sent twice is one observation."""
    return hashlib.sha256("call-{}".format(int(call_id)).encode("ascii")).hexdigest()[:16]


def event_span(event_id):
    """The span of one event of claude_events (retention.move_events): the same event sent again replaces itself."""
    return hashlib.sha256("event-{}".format(int(event_id)).encode("ascii")).hexdigest()[:16]


# ---------------------------------------------------------------- keys, tokens and passwords are never sent

REDACTED = "[redacted]"
_SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"(?<![A-Za-z0-9])(?:sk-ant-|sk-lf-|pk-lf-|sk-proj-|sk-|rk_live_|sk_live_|sk_test_)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"(?<![A-Za-z0-9])xox[abposr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?<![A-Za-z0-9])(?:hf|r8)_[A-Za-z0-9]{30,}"),
    re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),   # a JWT
    re.compile(r"(?i)(?<![A-Za-z0-9])AccountKey=[A-Za-z0-9+/=]{20,}"),   # an Azure storage connection string's
]
# The secret part of a pair: what follows "Bearer ", "user:password@" in an address, "password=", "api_key": ...
_PAIRS = [
    re.compile(r"(?i)(\b(?:bearer|basic)\s+)[A-Za-z0-9._~+/\-]{16,}=*"),
    re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^\s/:@\"'\\]+:)[^\s@/\"'\\]+(?=@)"),
    re.compile(r"(?i)((?<![A-Za-z0-9])(?:password|passwd|pwd|passphrase|secret|secret[_\-]?key|client[_\-]?secret|api[_\-]?key|apikey|"
               r"access[_\-]?key|access[_\-]?token|auth[_\-]?token|refresh[_\-]?token|private[_\-]?key|token|sig|signature)"
               r"(?![A-Za-z0-9])\\?[\"']?\s*[:=]\s*\\?[\"']?)(?!\d+(?![^\s\"'\\,;&}]))[^\s\"'\\,;&}]{6,}"),
    re.compile(r"(?i)(\bpassword\s+(?:is|was)\s+)\S{4,}"),
]


def redact(text):
    """The text with whatever looks like a key, a token or a password in it replaced by [redacted]: API keys of the
    known kinds (Anthropic, Langfuse, OpenAI, GitHub, Slack, AWS, Google, Hugging Face, Replicate), JWTs, private keys,
    bearer and basic credentials, the password of an address (scheme://user:password@host) and the value after a
    word such as password, secret, api_key or token followed by : or =. Emails are kept. Works on JSON as well."""
    text = str(text)
    for pattern in _SECRETS:
        text = pattern.sub(REDACTED, text)
    for pattern in _PAIRS:
        text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
    return text


def scrub(value):
    """A JSON-like value with every string in it redacted (a dataset's items)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def _text(key, value):
    return {"key": key, "value": {"stringValue": redact(value)}}


def _cut(text):
    """The text, or its first LONGEST characters and a word on what was left out."""
    text = str(text)
    if len(text) <= LONGEST:
        return text
    return text[:LONGEST] + "\n[… {:,} more characters not sent to Langfuse]".format(len(text) - LONGEST)


def _messages(messages):
    """The messages, each one's words cut at LONGEST."""
    return [dict(m, content=_cut(m["content"])) if isinstance(m, dict) and isinstance(m.get("content"), str) else m
            for m in messages or []]


def _usage(model, usage):
    """(tokens, dollars) as Langfuse names them, from the counts claude.judged makes ({"prompt", "cached", "written",
    "answer"}; "prompt" holds the other two)."""
    count = lambda key: max(0, int((usage or {}).get(key) or 0))
    read, written = count("cached"), count("written")
    tokens = {"input": max(0, count("prompt") - read - written), "output": count("answer"),
              "cache_read_input_tokens": read, "cache_creation_input_tokens": written}
    prices = Credits.token_prices(model)
    if not prices:
        return tokens, None
    dollars = {name: round(tokens[name] * price / 1e6, 8) for name, price in zip(tokens, prices)}
    dollars["total"] = round(sum(dollars.values()), 8)   # Langfuse does not add the cache's parts up itself
    return tokens, dollars


# ---------------------------------------------------------------- versions of the system prompt and the skills

_versions = {"at": 0.0, "system": "", "skills": {}}
_versions_lock = threading.Lock()


def version_of(text):
    """A short hash of a prompt's text: the same text, the same version; any change, a new one."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:12]


def prompt_versions():
    """{"system": the agent's SYSTEM prompt's version, "skills": {skill id: its version}}, made again at most every
    VERSIONS_KEPT seconds (a skill saved in the console shows within a minute)."""
    with _versions_lock:
        if time.time() - _versions["at"] >= VERSIONS_KEPT:
            from . import agent, skills   # here, not at the top: agent.py is large and imports much
            try:
                found = {s["id"]: version_of(s["text"]) for s in skills.load()}
            except (OSError, ValueError):
                found = _versions["skills"]
            _versions.update(at=time.time(), system=version_of(agent.SYSTEM), skills=found)
        return {"system": _versions["system"], "skills": dict(_versions["skills"])}


def _trace(turn, fallback, generation=False):
    """The attributes that say what the whole trace is: its name, its tags and what is known of it (traces.TURN); for a
    call to a model, the versions of the prompts it was given as well (`langfuse.version`, which Langfuse compares)."""
    turn = turn or {}
    found = [_text("langfuse.trace.name", turn.get("name") or fallback)]
    if turn.get("tags"):
        found.append(_text("langfuse.trace.tags", json.dumps([str(t) for t in turn["tags"]])))
    metadata = turn.get("metadata") or {}
    for key, value in metadata.items():
        if value not in (None, "", []):
            found.append(_text("langfuse.trace.metadata." + key, json.dumps(value) if isinstance(value, (list, dict)) else value))
    if generation:
        versions = prompt_versions()
        used = [str(s) for s in [*(metadata.get("skills") or []), *(turn.get("tags") or [])]]
        skills = {s: versions["skills"][s] for s in dict.fromkeys(used) if s in versions["skills"]}
        found += [_text("langfuse.version", versions["system"]), _text("langfuse.trace.metadata.system_prompt", versions["system"]),
                  _text("langfuse.observation.metadata.system_prompt", versions["system"])]
        if skills:
            found += [_text("langfuse.trace.metadata.skill_versions", json.dumps(skills)),
                      _text("langfuse.observation.metadata.skill_versions", json.dumps(skills))]
    return found


def _body(spans):
    return {"resourceSpans": [{"resource": {"attributes": [_text("service.name", "scene-studio")]},
                               "scopeSpans": [{"scope": {"name": "scene.traces"}, "spans": spans}]}]}


def _auth(public, secret):
    return "Basic " + base64.b64encode("{}:{}".format(public, secret).encode("utf-8")).decode("ascii")


def owns_words(db):
    """Whether Langfuse is the one place the words of the agent's calls and sessions are kept (setting
    langfuse_owns_words "1"; off, "0", by default: they are kept here as well, as always). It takes effect only while
    a Langfuse is in use and langfuse_words is on, so the words always have somewhere to be."""
    return db is not None and db.setting("langfuse_owns_words", "0") == "1"


class Sender:
    def __init__(self, db, credits=None):
        self.db = db
        self.credits = credits   # what a call's tokens come to in credits and rupees (credits.Credits; none in some tests)
        self.lock = threading.Lock()   # `add` runs on the database's threads, `send` on the event loop
        self.waiting = []   # the spans not sent yet
        self.scores = []    # the scores not sent yet
        self.calls = {}     # span id -> the agent_calls id whose words it carries (on_delivered is told once it went)
        self.on_delivered = None   # function([call ids]) run on a database thread once Langfuse took those calls' words
        self._link = (0, None)   # (when it was asked, {"url", "project"} or None): the console's link to Langfuse
        self._emails = {}   # user id -> (when read, email)
        # How the sending goes, for health.py and the Servers card: what went, what was lost and why it is waiting.
        self.health = {"sent": 0, "dropped": 0, "refused": 0, "last_sent": None, "down_since": None, "last_error": ""}

    def target(self):
        """(address, Authorization header) of the first Langfuse in use that has its keys, or None."""
        for row in endpoints.listed(self.db, "langfuse", active_only=True):
            keys = vault.reveal(row["api_key"])
            if row["url"] and ":" in keys:
                return row["url"], "Basic " + base64.b64encode(keys.encode("utf-8")).decode("ascii")
        return None

    def _who(self, user):
        """The user's email, as Langfuse lists them; the id when there is none (or no database, in some tests). The same
        user is the same email everywhere: agent_calls.user_id and the trace's metadata user_id give the number."""
        hit = self._emails.get(user)
        if hit is None or time.time() - hit[0] >= WHO_KEPT:
            row = self.db.one("SELECT email FROM users WHERE id = ?", (user,)) if self.db is not None else None
            hit = self._emails[user] = (time.time(), (row or {}).get("email") or str(user))
        return hit[1]

    def words(self):
        """Whether the words (what was asked, the answers, a grade's reasons, errors) are sent, or only names and numbers."""
        return self.db is None or self.db.setting("langfuse_words", "1") != "0"

    def add(self, purpose, model, asked, started, ended, messages, content=None, usage=None, error=None, tool=None,
            run="", session="", user=None, turn=None, call=None, answer_format=None):
        """One call, as traces.Recorder wrote it down, made into a generation waiting to be sent. turn: what the turn
        it was made in is (traces.TURN): its name, tags and metadata. call: its agent_calls id (its span is then always
        the same, call_span); answer_format is sent with it when Langfuse keeps the words alone (owns_words), for a
        replay read back from there."""
        tokens, dollars = _usage(model or asked, usage)
        words = self.words()
        attributes = [_text("gen_ai.request.model", model or asked or ""),
                      _text("langfuse.observation.usage_details", json.dumps(tokens))]
        if words:
            attributes.append(_text("langfuse.observation.input", json.dumps(_messages(messages), ensure_ascii=False, default=str)))
            if content is not None:
                attributes.append(_text("langfuse.observation.output", _cut(json.dumps(content, ensure_ascii=False, default=str))))
            if call is not None and answer_format is not None and owns_words(self.db):
                attributes.append(_text("langfuse.observation.metadata.answer_format", _cut(json.dumps(answer_format, default=str))))
        if dollars:
            attributes.append(_text("langfuse.observation.cost_details", json.dumps(dollars)))
            if self.credits is not None:   # the same tokens in the studio's money: what a turn charges a user is made of these
                worth = self.credits.token_cost(model or asked, usage)
                attributes += [_text("langfuse.observation.metadata.credits", worth),
                               _text("langfuse.observation.metadata.rupees", round(worth * self.credits.inr_per_1000 / 1000, 2)),
                               _text("langfuse.observation.metadata.inr_per_usd", self.credits.inr_per_usd)]
        if tool:
            attributes.append(_text("langfuse.observation.metadata.tool", tool))
        if asked and asked != model:
            attributes.append(_text("langfuse.observation.metadata.asked", asked))
        if call is not None:
            attributes.append(_text("langfuse.observation.metadata.call", call))
        span = self._build("generation", purpose, started, ended, attributes, run, session, user, turn, purpose, error, words,
                           span_id=call_span(call) if call is not None else None)
        self._append(self.waiting, span, call if words and call is not None else None)

    def span(self, name, started, ended, run="", turn=None, metadata=None, user=None, session="", error=None, fallback="Render"):
        """Something other than a call to a model (a render, an edit) as a span of the trace of `run`. metadata: names
        and numbers only, so it is sent whatever langfuse_words says (an error only when it is on)."""
        attributes = [_text("langfuse.observation.metadata." + key, json.dumps(value) if isinstance(value, (list, dict)) else value)
                      for key, value in (metadata or {}).items() if value not in (None, "")]
        self._append(self.waiting, self._build("span", name, started, ended, attributes, run, session, user, turn, fallback, error,
                                               self.words()))

    def _build(self, kind, name, started, ended, attributes, run, session, user, turn, fallback, error, words, span_id=None, trace=None):
        attributes = [_text("langfuse.observation.type", kind), *_trace(turn, fallback, kind == "generation"), *attributes]
        if user is not None:   # shown by email, easier to tell apart than a number; the number stays in the metadata
            attributes += [_text("user.id", self._who(user)), _text("langfuse.trace.metadata.user_id", user)]
        if session:
            attributes.append(_text("session.id", session))
        if error:
            error = redact(_cut(error)) if words else WORDS_OFF
            attributes += [_text("langfuse.observation.level", "ERROR"), _text("langfuse.observation.status_message", error)]
        return {"traceId": trace or trace_id(run), "spanId": span_id or os.urandom(8).hex(), "name": redact(name), "kind": 1,
                "startTimeUnixNano": str(int(started * 1e9)), "endTimeUnixNano": str(int(ended * 1e9)),
                "attributes": attributes, "status": {"code": 2, "message": error} if error else {}}

    def _append(self, queue, item, call=None):
        """Put one span or score in its queue; past KEEP the oldest go, and are counted as lost."""
        with self.lock:
            queue.append(item)
            if call is not None:
                self.calls[item["spanId"]] = call
            over = len(queue) - KEEP
            if over > 0:
                for gone in queue[:over]:
                    self.calls.pop(gone.get("spanId"), None)
                del queue[:over]
                self.health["dropped"] += over

    def _take(self, queue, items):
        """Take out of its queue what was just sent (those very items: others may have been added, or the oldest let
        go, meanwhile). Returns the call ids whose words went."""
        sent = {id(item) for item in items}
        with self.lock:
            queue[:] = [item for item in queue if id(item) not in sent]
            return [self.calls.pop(item["spanId"]) for item in items if item.get("spanId") in self.calls]

    def score(self, run, name, value, comment="", kind="NUMERIC", key=None):
        """What a person (or the grading model) thought of a turn's work, as a score on its trace. key: the same key
        replaces the score sent before with it (a thumb turned over), none adds a new one."""
        body = {"id": key or os.urandom(16).hex(), "traceId": trace_id(run), "name": name, "value": value, "dataType": kind}
        if comment and self.words():
            body["comment"] = redact(_cut(comment))
        self._append(self.scores, {"id": os.urandom(16).hex(), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                                   "type": "score-create", "body": body})

    def item_score(self, item_id, name, value, key, comment=""):
        """A score on the trace of the turn whose job made a library item (a thumb on it, a still approved or made
        again); none for an item made before jobs kept their turn, or with no Langfuse in use."""
        try:
            turn = item_turn(self.db, item_id) if self.target() is not None else None
            if turn:
                self.score(turn["run"], name, value, comment, key=key)
        except Exception as problem:   # a score is a help: what the user did stands all the same
            print("The score could not be readied for Langfuse: {}".format(problem))

    def _refused(self, response, items, what):
        """Whether Langfuse refused a batch for good (REFUSED): then it is let go and counted, not sent for ever."""
        if response.status_code not in REFUSED:
            return False
        with self.lock:
            self.health["refused"] += len(items)
        print("Langfuse refused {} {} ({}): {}".format(len(items), what, response.status_code, response.text[:200]))
        return True

    async def send(self, http):
        """Send what waits, BATCH at a time. Returns how many went; what Langfuse did not take waits for the next time."""
        target = await offload(self.target) if self.waiting or self.scores else None
        if target is None:
            with self.lock:   # no Langfuse in use: nothing is kept for one
                self.waiting.clear()
                self.scores.clear()
                self.calls.clear()
            return 0
        url, auth = target
        sent = 0
        try:
            while self.waiting:
                with self.lock:
                    spans = self.waiting[:BATCH]
                response = await http.post(url + PATH, json=_body(spans), headers={"Authorization": auth})
                if self._refused(response, spans, "call(s)"):
                    self._take(self.waiting, spans)
                    continue
                response.raise_for_status()
                delivered = self._take(self.waiting, spans)
                sent += len(spans)
                if delivered and self.on_delivered is not None:
                    try:
                        await offload(self.on_delivered, delivered)
                    except Exception as problem:   # the words stay here a while longer: no harm
                        print("The words Langfuse took could not be let go here: {}".format(problem))
            while self.scores:
                with self.lock:
                    batch = self.scores[:BATCH]
                response = await http.post(url + SCORES, json={"batch": batch}, headers={"Authorization": auth})
                if self._refused(response, batch, "score(s)"):
                    self._take(self.scores, batch)
                    continue
                response.raise_for_status()
                self._take(self.scores, batch)
                sent += len(batch)
                try:
                    refused = (response.json() or {}).get("errors") if response.content else None
                except ValueError:
                    refused = None
                if refused:   # taken, but not all of it: said, and not sent again
                    print("Langfuse did not take {} score(s): {}".format(len(refused), refused[0]))
        except (httpx.HTTPError, OSError) as error:
            with self.lock:
                self.health["down_since"] = self.health["down_since"] or time.time()
                self.health["last_error"] = "{}: {}".format(type(error).__name__, error)[:300]
                self.health["sent"] += sent
            raise
        with self.lock:
            self.health["sent"] += sent
            if sent:
                self.health.update(last_sent=time.time(), down_since=None, last_error="")
        return sent

    def status(self):
        """How the sending goes, now: {"backlog" (spans and scores waiting), "keep", "sent", "dropped" (lost because
        more than KEEP waited), "refused" (that Langfuse would never take), "last_sent", "down_since", "last_error"}.
        No database, no network: health.py and the Servers card read it as often as they like."""
        with self.lock:
            return dict(self.health, backlog=len(self.waiting) + len(self.scores), spans=len(self.waiting),
                        scores=len(self.scores), keep=KEEP)

    async def run_forever(self):
        down = False   # said once when Langfuse stops answering, and once when it answers again, not every half minute
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3)) as http:
            while True:
                await asyncio.sleep(EVERY)
                try:
                    sent = await self.send(http)
                    if down and sent:
                        print("Langfuse answers again: the agent's calls held meanwhile were sent.")
                        down = False
                except (httpx.HTTPError, OSError) as error:
                    if not down:
                        print("The agent's calls could not be sent to Langfuse: {} (kept, at most {}, and tried again every 30 s)".format(
                            error, KEEP))
                        down = True
                    await asyncio.sleep(30)   # down or restarting: a while before trying again
                except Exception as error:   # whatever it is, the next calls are still sent
                    print("Langfuse: {}".format(error))
                    with self.lock:
                        self.health["dropped"] += len(self.waiting) + len(self.scores)
                        self.waiting.clear()
                        self.scores.clear()
                        self.calls.clear()

    async def link(self, http=None):
        """{"url", "project"}: where the console opens a trace in Langfuse ({url}/project/{project}/traces/{trace id}),
        or None when no Langfuse is in use or it does not answer. Asked at most every LINK_KEPT seconds."""
        target = await offload(self.target)
        if target is None:
            return None
        asked, found = self._link
        if time.time() - asked < LINK_KEPT and (found is None or found["url"] == target[0]):
            return found
        found = None
        try:
            async with (httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2)) if http is None else _Borrowed(http)) as client:
                response = await client.get(target[0] + "/api/public/projects", headers={"Authorization": target[1]})
                response.raise_for_status()
                projects = response.json().get("data") or []
                if projects:
                    found = {"url": target[0], "project": projects[0]["id"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            print("Langfuse did not say its project: {}".format(error))
        self._link = (time.time(), found)
        return found

    async def exchange(self, call_id, http=None):
        """The words of one call read back from Langfuse, as traces.Recorder.exchange gives them from its file:
        {"messages", "format", "answer"}; None when no Langfuse is in use, it does not have them or does not answer.
        For the console's Words and replay once Langfuse keeps the words alone (owns_words)."""
        target = await offload(self.target)
        if target is None:
            return None
        try:
            async with (httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3)) if http is None else _Borrowed(http)) as client:
                response = await client.get(target[0] + "/api/public/observations/" + call_span(call_id),
                                            headers={"Authorization": target[1]})
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                found = response.json()
        except (httpx.HTTPError, ValueError) as error:
            print("Langfuse did not give the words of call {}: {}".format(call_id, error))
            return None
        metadata = _parsed(found.get("metadata")) or {}
        messages = _parsed(found.get("input"))
        return {"messages": messages if isinstance(messages, list) else [], "answer": _parsed(found.get("output")),
                "format": _parsed(metadata.get("answer_format")) if isinstance(metadata, dict) else None, "from": "langfuse"}

    async def to_dataset(self, dataset, messages, answer, run="", note="", http=None):
        """Keep one call in a Langfuse dataset, made if it is not there yet: what was sent as its input, its answer as
        what is expected, its trace as where it came from. Raises LookupError with no Langfuse in use; httpx errors
        when it does not answer or refuses."""
        target = await offload(self.target)
        if target is None:
            raise LookupError("No Langfuse is set in Servers & APIs.")
        url, auth = target
        async with (httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3)) if http is None else _Borrowed(http)) as client:
            await _dataset(client, url, {"Authorization": auth}, dataset, "Agent calls kept from the studio's admin console.")
            item = {"datasetName": dataset, "input": scrub(_messages(messages)), "expectedOutput": scrub(answer),
                    "metadata": {"note": redact(note)} if note else {}}
            if run:
                item["sourceTraceId"] = trace_id(run)
            response = await client.post(url + "/api/public/dataset-items", headers={"Authorization": auth}, json=item)
            response.raise_for_status()
            return response.json()


def _parsed(value):
    """A value Langfuse gives back as it was sent: JSON text read again, anything else as it is."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class _Borrowed:
    """A client lent by the caller (a test's), used as `async with` without closing it."""

    def __init__(self, http):
        self.http = http

    async def __aenter__(self):
        return self.http

    async def __aexit__(self, *_):
        return False


def job_turn(settings):
    """The turn a job belongs to, as jobs.add kept it in its settings: {"run", "name"}, or None."""
    turn = (settings or {}).get("turn") if isinstance(settings, dict) else None
    if isinstance(turn, dict) and isinstance(turn.get("run"), str) and turn["run"].isalnum() and len(turn["run"]) <= 32:
        return {"run": turn["run"], "name": turn.get("name") if turn.get("name") in NAMES else "Render"}
    return None


def item_turn(db, item_id):
    """The turn the job that made a library item belongs to: {"run", "name"}, or None (made before turns were kept)."""
    row = db.one("SELECT j.settings FROM generations g JOIN jobs j ON j.id = g.job_id WHERE g.id = ?", (item_id,))
    try:
        return job_turn(json.loads(row["settings"])) if row else None
    except ValueError:
        return None


# ---------------------------------------------------------------- a Claude session's events (retention.move_events)

def event_spans(sender, rows):
    """Events of claude_events as spans for Langfuse, each in the trace of its session's day ("Claude session"), in the
    session of its Agent tab (the key traces.SESSION has, user:tab:project), by its user. rows: the events with their
    session's ref, user_id, run and project_id. Returns [(event id, span)]."""
    found = []
    for row in rows:
        day = time.strftime("%Y-%m-%d", time.gmtime(row["at"]))
        trace = trace_id("session-{}-{}".format(row["ref"], day))
        attributes = [_text("langfuse.observation.metadata.kind", row["kind"]), _text("langfuse.observation.metadata.event", row["id"]),
                      _text("langfuse.trace.metadata.session_ref", row["ref"])]
        if row.get("text"):
            attributes.append(_text("langfuse.observation.input", _cut(row["text"])))
        if row.get("data"):
            attributes.append(_text("langfuse.observation.metadata.data", _cut(row["data"])))
        session = "{}:{}:{}".format(row["user_id"], row["run"], row["project_id"] or 0)
        span = sender._build("event", row["kind"], row["at"], row["at"], attributes, "", session, row["user_id"],
                             {"name": "Claude session"}, "Claude session", "", True, span_id=event_span(row["id"]), trace=trace)
        found.append((row["id"], span))
    return found


def post_spans(target, spans, http=None):
    """Send spans now and wait for Langfuse to take them (on a database thread: retention.py). Raises httpx errors when
    it does not answer or refuses, so what was not taken is not let go."""
    url, auth = target
    client = http or httpx.Client(timeout=httpx.Timeout(15, connect=3))
    try:
        for start in range(0, len(spans), BATCH):
            response = client.post(url + PATH, json=_body(spans[start:start + BATCH]), headers={"Authorization": auth})
            response.raise_for_status()
    finally:
        if http is None:
            client.close()


# ---------------------------------------------------------------- datasets and their runs (backend/evals)

def _target(target=None, db=None):
    """Where a dataset goes: the target given ((address, Authorization header) or (address, public key, secret key)),
    else the Langfuse in use in the console's Servers (with a database), else LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY and
    LANGFUSE_SECRET_KEY from the environment. Raises LookupError when there is none."""
    if target:
        return (target[0].rstrip("/"), target[1]) if len(target) == 2 else (target[0].rstrip("/"), _auth(target[1], target[2]))
    if db is not None:
        found = Sender(db).target()
        if found:
            return found
    host, public, secret = (os.environ.get(k, "") for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"))
    if host and public and secret:
        return host.rstrip("/"), _auth(public, secret)
    raise LookupError("No Langfuse is set in Servers & APIs (or LANGFUSE_HOST and its keys in the environment).")


def _item_id(dataset, key):
    """A dataset item's id, the same for the same key in the same dataset: pushing a turn again updates it."""
    return "scene-" + hashlib.sha256("{}\0{}".format(dataset, key).encode("utf-8")).hexdigest()[:24]


async def _dataset(client, url, headers, name, description):
    """The dataset, made when it is not there yet."""
    found = await client.get(url + "/api/public/v2/datasets/" + quote(name, safe=""), headers=headers)
    if found.status_code == 404:
        made = await client.post(url + "/api/public/v2/datasets", headers=headers, json={"name": name, "description": description})
        made.raise_for_status()
    else:
        found.raise_for_status()


def _words_allowed(db):
    if db is not None and db.setting("langfuse_words", "1") == "0":
        raise PermissionError("Words are not sent to Langfuse (Settings, Langfuse): a dataset is all words, so none is sent.")


def _items(dataset, items):
    out = []
    for number, item in enumerate(items):
        key = str(item.get("key") or item.get("id") or number)
        body = {"id": _item_id(dataset, key), "datasetName": dataset, "input": scrub(item.get("input")),
                "metadata": scrub(dict(item.get("metadata") or {}, key=key))}
        if item.get("expected") is not None:
            body["expectedOutput"] = scrub(item["expected"])
        if item.get("source_run"):
            body["sourceTraceId"] = trace_id(str(item["source_run"]))
        out.append((key, body))
    return out


async def push_dataset(name, items, *, description="Agent turns saved from the studio.", target=None, db=None, http=None):
    """Put saved agent turns in a Langfuse dataset (made when it is not there). items: [{"key": a stable id of the turn
    (the same key updates its item), "input": what the agent was given, "expected": what a good answer is (optional),
    "metadata": {...} (optional), "source_run": the traces.RUN it was saved from (optional, links its trace)}].
    Every string is redacted. Returns {"dataset", "items": {key: item id}}. Raises LookupError with no Langfuse,
    PermissionError when the studio's langfuse_words is off, httpx errors when Langfuse does not answer or refuses."""
    if db is not None:
        await offload(_words_allowed, db)
    url, auth = await (offload(_target, target, db) if db is not None else asyncio.to_thread(_target, target, db))
    headers = {"Authorization": auth}
    async with (httpx.AsyncClient(timeout=httpx.Timeout(15, connect=3)) if http is None else _Borrowed(http)) as client:
        await _dataset(client, url, headers, name, description)
        made = {}
        for key, body in _items(name, items):
            response = await client.post(url + "/api/public/dataset-items", headers=headers, json=body)
            response.raise_for_status()
            made[key] = body["id"]
    return {"dataset": name, "items": made}


async def dataset_run(name, items, results, run_name=None, *, description="", metadata=None, target=None, db=None, http=None):
    """One evaluation of a dataset's items, kept in Langfuse as a dataset run, to compare prompts and models there.

    name: the dataset (made, and its items pushed as in push_dataset, when they are not there yet).
    items: as push_dataset takes them ([{"key", "input", "expected"?, "metadata"?, "source_run"?}]).
    results: what the run gave for each item, in the same order as items or with the item's "key":
        [{"key"?, "output": the answer, "scores": {name: number 0-1 or any number} (optional),
          "comments": {score name: why} (optional), "model": str (optional), "seconds": float (optional),
          "usage": {"prompt", "cached", "written", "answer"} (optional), "error": str (optional),
          "started": seconds since 1970 (optional, default now)}].
    run_name: the run's name in Langfuse (default "<name> <UTC date and time>"); description, metadata: the run's.

    Each result is a trace of its own ("Eval run", tagged "eval") with one generation (the item's input, the output,
    the model, tokens and seconds), linked to its item as the run's item, with its scores on that trace. Every string
    is redacted. Returns {"dataset", "run", "items": {key: item id}, "traces": {key: trace id}, "scores": count}.
    Raises LookupError with no Langfuse, PermissionError when the studio's langfuse_words is off, httpx errors when
    Langfuse does not answer or refuses (what was sent before stays)."""
    if db is not None:
        await offload(_words_allowed, db)
    run_name = run_name or "{} {}".format(name, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
    url, auth = await (offload(_target, target, db) if db is not None else asyncio.to_thread(_target, target, db))
    headers = {"Authorization": auth}
    pushed = _items(name, items)
    by_key = {key: body for key, body in pushed}
    sender = Sender(None)   # builds the spans; no database: the result's users are not known
    spans, links, scores, traces = [], [], [], {}
    for number, result in enumerate(results):
        key = str(result.get("key") if result.get("key") is not None else (pushed[number][0] if number < len(pushed) else number))
        item = by_key.get(key)
        if item is None:
            raise ValueError("A result for {!r}, which is not one of the items.".format(key))
        run = "eval:{}:{}".format(run_name, key)
        traces[key] = trace_id(run)
        started = float(result.get("started") or time.time())
        ended = started + float(result.get("seconds") or 0)
        model = str(result.get("model") or "")
        tokens, dollars = _usage(model, result.get("usage"))
        attributes = [_text("gen_ai.request.model", model), _text("langfuse.observation.usage_details", json.dumps(tokens)),
                      _text("langfuse.observation.input", _cut(json.dumps(item["input"], ensure_ascii=False, default=str))),
                      _text("langfuse.observation.output", _cut(json.dumps(result.get("output"), ensure_ascii=False, default=str))),
                      _text("langfuse.trace.metadata.dataset", name), _text("langfuse.trace.metadata.dataset_run", run_name),
                      _text("langfuse.trace.metadata.item", key)]
        if dollars:
            attributes.append(_text("langfuse.observation.cost_details", json.dumps(dollars)))
        span_id = hashlib.sha256(run.encode("utf-8")).hexdigest()[:16]
        spans.append(sender._build("generation", "eval " + name, started, ended, attributes, run, "", None,
                                   {"name": "Eval run", "tags": ["eval", name]}, "Eval run", result.get("error"), True, span_id=span_id))
        links.append({"runName": run_name, "runDescription": description, "metadata": scrub(metadata or {}),
                      "datasetItemId": item["id"], "traceId": trace_id(run), "observationId": span_id})
        for score, value in (result.get("scores") or {}).items():
            body = {"id": hashlib.sha256("{}\0{}".format(run, score).encode("utf-8")).hexdigest()[:32], "traceId": trace_id(run),
                    "name": str(score), "value": value, "dataType": "NUMERIC" if isinstance(value, (int, float)) else "CATEGORICAL"}
            why = (result.get("comments") or {}).get(score)
            if why:
                body["comment"] = redact(_cut(why))
            scores.append({"id": os.urandom(16).hex(), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                           "type": "score-create", "body": body})
    async with (httpx.AsyncClient(timeout=httpx.Timeout(15, connect=3)) if http is None else _Borrowed(http)) as client:
        await _dataset(client, url, headers, name, "Agent turns saved from the studio.")
        for _, body in pushed:
            response = await client.post(url + "/api/public/dataset-items", headers=headers, json=body)
            response.raise_for_status()
        for start in range(0, len(spans), BATCH):
            response = await client.post(url + PATH, headers=headers, json=_body(spans[start:start + BATCH]))
            response.raise_for_status()
        for link in links:
            response = await client.post(url + "/api/public/dataset-run-items", headers=headers, json=link)
            response.raise_for_status()
        for start in range(0, len(scores), BATCH):
            response = await client.post(url + SCORES, headers=headers, json={"batch": scores[start:start + BATCH]})
            response.raise_for_status()
    return {"dataset": name, "run": run_name, "items": {key: body["id"] for key, body in pushed}, "traces": traces,
            "scores": len(scores)}
