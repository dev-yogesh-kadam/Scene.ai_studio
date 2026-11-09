"""Each call of the agent's models sent to Langfuse as well (docs/langfuse.md), when a Langfuse server is set and in use
in the console's Servers section: its address, and its project's two keys kept as "public:secret", encrypted (vault.py).

traces.Recorder hands every call it writes down to `add`, which only puts it in a list: nothing here can slow or fail a
user's answer. `run_forever` sends what waits every few seconds, as OpenTelemetry spans (Langfuse 4 takes traces only
that way, at /api/public/otel/v1/traces). What one turn of the agent asked is one trace (traces.RUN), named for what it
was ("Agent turn", "Film run"), with the skills it used as tags; the Agent tab of a project is one session
(traces.SESSION). Each call is a generation named by its purpose, with its model, tokens, what Anthropic charges for
them in dollars (credits.CLAUDE_PRICES) and what that comes to in the studio's credits and rupees, the words sent and
the answer. The renders a turn made join its trace as spans (`span`, from jobs.py); a render nobody asked the agent
for has a trace of its own, "Render".

What the users think of a result (their thumbs, a still approved or made again) goes as a score (`score`), at
/api/public/ingestion, which in Langfuse 4 takes scores only.

Two settings, in the console's Settings: langfuse_words ("0": no words are sent, only names, models, numbers and
times) and langfuse_grade_share (the share of turns, in percent, the fast model grades; see workspace.py).

With no Langfuse in use, or one that does not answer, the calls are let go: at most KEEP wait for it to come back.
"""

import asyncio
import base64
import hashlib
import json
import os
import time
from urllib.parse import quote

import httpx

from . import endpoints, vault
from .credits import Credits

EVERY = 3        # seconds between two sendings
BATCH = 100      # calls in one request at most
KEEP = 1000      # calls kept waiting at most while Langfuse does not answer; the oldest go first
PATH = "/api/public/otel/v1/traces"
SCORES = "/api/public/ingestion"   # Langfuse 4 takes only scores there
LONGEST = 50000  # characters of one message (or one answer) sent at most: a long skill is cut, so Langfuse stays small
NAMES = ("Agent turn", "Film run", "Render")   # what a trace can be called
LINK_KEPT = 300  # seconds the console's link to Langfuse (its address and project) is kept before it is asked again


def trace_id(run):
    """The Langfuse trace of a run (traces.RUN): the same run always gives the same trace, a new one each time without one."""
    return hashlib.sha256(run.encode("utf-8")).hexdigest()[:32] if run else os.urandom(16).hex()


def _text(key, value):
    return {"key": key, "value": {"stringValue": str(value)}}


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


def _trace(turn, fallback):
    """The attributes that say what the whole trace is: its name, its tags and what is known of it (traces.TURN)."""
    turn = turn or {}
    found = [_text("langfuse.trace.name", turn.get("name") or fallback)]
    if turn.get("tags"):
        found.append(_text("langfuse.trace.tags", json.dumps([str(t) for t in turn["tags"]])))
    for key, value in (turn.get("metadata") or {}).items():
        if value not in (None, "", []):
            found.append(_text("langfuse.trace.metadata." + key, json.dumps(value) if isinstance(value, (list, dict)) else value))
    return found


class Sender:
    def __init__(self, db, credits=None):
        self.db = db
        self.credits = credits   # what a call's tokens come to in credits and rupees (credits.Credits; none in some tests)
        self.waiting = []   # the spans not sent yet
        self.scores = []    # the scores not sent yet
        self._link = (0, None)   # (when it was asked, {"url", "project"} or None): the console's link to Langfuse
        self._emails = {}   # user id -> email, read once (an email change shows after a restart)

    def target(self):
        """(address, Authorization header) of the first Langfuse in use that has its keys, or None."""
        for row in endpoints.listed(self.db, "langfuse", active_only=True):
            keys = vault.reveal(row["api_key"])
            if row["url"] and ":" in keys:
                return row["url"], "Basic " + base64.b64encode(keys.encode("utf-8")).decode("ascii")
        return None

    def _who(self, user):
        """The user's email, as Langfuse lists them; the id when there is none (or no database, in some tests)."""
        if user not in self._emails:
            row = self.db.one("SELECT email FROM users WHERE id = ?", (user,)) if self.db is not None else None
            self._emails[user] = (row or {}).get("email") or str(user)
        return self._emails[user]

    def words(self):
        """Whether the words (what was asked, the answers, a grade's reasons) are sent, or only names and numbers."""
        return self.db is None or self.db.setting("langfuse_words", "1") != "0"

    def add(self, purpose, model, asked, started, ended, messages, content=None, usage=None, error=None, tool=None,
            run="", session="", user=None, turn=None):
        """One call, as traces.Recorder wrote it down, made into a generation waiting to be sent. turn: what the turn
        it was made in is (traces.TURN): its name, tags and metadata."""
        tokens, dollars = _usage(model or asked, usage)
        words = self.words()
        attributes = [_text("gen_ai.request.model", model or asked or ""),
                      _text("langfuse.observation.usage_details", json.dumps(tokens))]
        if words:
            attributes.append(_text("langfuse.observation.input", json.dumps(_messages(messages), ensure_ascii=False, default=str)))
            if content is not None:
                attributes.append(_text("langfuse.observation.output", _cut(json.dumps(content, ensure_ascii=False, default=str))))
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
        self._queue("generation", purpose, started, ended, attributes, run, session, user, turn, purpose, error)

    def span(self, name, started, ended, run="", turn=None, metadata=None, user=None, session="", error=None, fallback="Render"):
        """Something other than a call to a model (a render, an edit) as a span of the trace of `run`. metadata: names
        and numbers only, so it is sent whatever langfuse_words says."""
        attributes = [_text("langfuse.observation.metadata." + key, json.dumps(value) if isinstance(value, (list, dict)) else value)
                      for key, value in (metadata or {}).items() if value not in (None, "")]
        self._queue("span", name, started, ended, attributes, run, session, user, turn, fallback, error)

    def _queue(self, kind, name, started, ended, attributes, run, session, user, turn, fallback, error):
        attributes = [_text("langfuse.observation.type", kind), *_trace(turn, fallback), *attributes]
        if user is not None:   # shown by email, easier to tell apart than a number; the number stays in the metadata
            attributes += [_text("user.id", self._who(user)), _text("langfuse.trace.metadata.user_id", user)]
        if session:
            attributes.append(_text("session.id", session))
        if error:
            attributes += [_text("langfuse.observation.level", "ERROR"), _text("langfuse.observation.status_message", _cut(error))]
        self.waiting.append({"traceId": trace_id(run), "spanId": os.urandom(8).hex(), "name": name, "kind": 1,
                             "startTimeUnixNano": str(int(started * 1e9)), "endTimeUnixNano": str(int(ended * 1e9)),
                             "attributes": attributes, "status": {"code": 2, "message": error} if error else {}})
        del self.waiting[:-KEEP]

    def score(self, run, name, value, comment="", kind="NUMERIC", key=None):
        """What a person (or the grading model) thought of a turn's work, as a score on its trace. key: the same key
        replaces the score sent before with it (a thumb turned over), none adds a new one."""
        body = {"id": key or os.urandom(16).hex(), "traceId": trace_id(run), "name": name, "value": value, "dataType": kind}
        if comment and self.words():
            body["comment"] = _cut(comment)
        self.scores.append({"id": os.urandom(16).hex(), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                            "type": "score-create", "body": body})
        del self.scores[:-KEEP]

    def item_score(self, item_id, name, value, key, comment=""):
        """A score on the trace of the turn whose job made a library item (a thumb on it, a still approved or made
        again); none for an item made before jobs kept their turn, or with no Langfuse in use."""
        try:
            turn = item_turn(self.db, item_id) if self.target() is not None else None
            if turn:
                self.score(turn["run"], name, value, comment, key=key)
        except Exception as problem:   # a score is a help: what the user did stands all the same
            print("The score could not be readied for Langfuse: {}".format(problem))

    async def send(self, http):
        """Send what waits, BATCH at a time. Returns how many went; what Langfuse did not take waits for the next time."""
        target = self.target() if self.waiting or self.scores else None
        if target is None:
            self.waiting.clear()   # no Langfuse in use: nothing is kept for one
            self.scores.clear()
            return 0
        url, auth = target
        sent = 0
        while self.waiting:
            spans = self.waiting[:BATCH]
            body = {"resourceSpans": [{"resource": {"attributes": [_text("service.name", "scene-studio")]},
                                       "scopeSpans": [{"scope": {"name": "scene.traces"}, "spans": spans}]}]}
            response = await http.post(url + PATH, json=body, headers={"Authorization": auth})
            response.raise_for_status()
            del self.waiting[:len(spans)]
            sent += len(spans)
        while self.scores:
            batch = self.scores[:BATCH]
            response = await http.post(url + SCORES, json={"batch": batch}, headers={"Authorization": auth})
            response.raise_for_status()
            del self.scores[:len(batch)]
            sent += len(batch)
            refused = (response.json() or {}).get("errors") if response.content else None
            if refused:   # taken, but not all of it: said, and not sent again
                print("Langfuse did not take {} score(s): {}".format(len(refused), refused[0]))
        return sent

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
                        print("The agent's calls could not be sent to Langfuse: {} (kept, and tried again every 30 s)".format(error))
                        down = True
                    await asyncio.sleep(30)   # down or restarting: a while before trying again
                except Exception as error:   # whatever it is, the next calls are still sent
                    print("Langfuse: {}".format(error))
                    self.waiting.clear()
                    self.scores.clear()

    async def link(self, http=None):
        """{"url", "project"}: where the console opens a trace in Langfuse ({url}/project/{project}/traces/{trace id}),
        or None when no Langfuse is in use or it does not answer. Asked at most every LINK_KEPT seconds."""
        target = self.target()
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

    async def to_dataset(self, dataset, messages, answer, run="", note="", http=None):
        """Keep one call in a Langfuse dataset, made if it is not there yet: what was sent as its input, its answer as
        what is expected, its trace as where it came from. Raises LookupError with no Langfuse in use; httpx errors
        when it does not answer or refuses."""
        target = self.target()
        if target is None:
            raise LookupError("No Langfuse is set in Servers & APIs.")
        url, auth = target
        async with (httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3)) if http is None else _Borrowed(http)) as client:
            headers = {"Authorization": auth}
            found = await client.get(url + "/api/public/v2/datasets/" + quote(dataset, safe=""), headers=headers)
            if found.status_code == 404:
                made = await client.post(url + "/api/public/v2/datasets", headers=headers,
                                         json={"name": dataset, "description": "Agent calls kept from the studio's admin console."})
                made.raise_for_status()
            else:
                found.raise_for_status()
            item = {"datasetName": dataset, "input": _messages(messages), "expectedOutput": answer,
                    "metadata": {"note": note} if note else {}}
            if run:
                item["sourceTraceId"] = trace_id(run)
            response = await client.post(url + "/api/public/dataset-items", headers=headers, json=item)
            response.raise_for_status()
            return response.json()


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
