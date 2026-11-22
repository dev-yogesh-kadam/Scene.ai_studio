"""Claude as a model of the agent, through Claude Code: the `claude` program of this PC, run here one of two ways, as an
admin picks in the console (Servers & APIs → Providers, "The agent uses"; claude_connection.py), and switched on the
next call with no restart:

- "this_pc" (Claude on this PC): with the account Claude Code is signed in with (a personal Claude subscription), and
  never an API key, even one in the studio's environment.
- "api_key": with an Anthropic API key in its environment.

A run here is checked by claude_policy.py before it starts (its arguments and environment) and as it goes (each line
of its stdin): Claude Code only answers, with none of this PC's own tools, settings or files.

Each call runs `claude -p` once with Claude Code's own tools, settings, MCP servers and skills off (but its web search,
when the agent may research: WEB_TOOLS): Claude only answers. The agent's tools, skills, questions and Approve all stay
in the studio (agent.py), the same as with any other model.

On this PC's sign-in, calls draw on the Claude account's usage limits (a five-hour and a seven-day window, kept as last
reported in LIMITS); with a key, on the key's rate limits. A call refused at a limit is AgentBusy in agent.py: the user
is told when the limit lifts.

A conversation of the studio is one session of Claude Code's (a thread, see agent.py): its first message carries
everything, and each later one only what is new; Claude Code keeps the rest and its cache holds it, so the turns
before are neither sent again by the studio nor read again at the full rate.

A conversation's session runs in one folder that never changes (`home`, with either connection), since Claude Code
finds a session by its folder. Its owner's memory is off in it, and it is compacted, still the same
session, when its context is COMPACT full (sessions.py)."""

import asyncio
import codecs
import collections
import contextlib
import contextvars
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from . import claude_policy, guardrails

try:   # the Claude Agent SDK: every message of the agent runs in a live session of Claude Code (converse); service() refuses to start without it
    import claude_agent_sdk as sdk
except ImportError:
    sdk = None

PARALLEL = 3   # calls running at once; more wait their turn (each is a program of its own, and all share one account)
MAX_TURNS = 3  # an answer in a schema takes two turns of Claude Code's (the answer, then its check)
# Claude Code's own web search, the one of its tools a studio session may use: the search runs at Anthropic, so it
# reaches nothing on this machine or its network. Reading a page is the studio's own tool (web_fetch, web.py), which
# fetches only public addresses: Claude Code's WebFetch runs here and would reach this PC's own network and localhost.
WEB_TOOLS = ("WebSearch",)
WEB_TURNS = 6  # more turns for a call that may search first
WINDOW = 1_000_000   # tokens of context the models have (Sonnet 5, Opus 4.7, Haiku 5.5 and later); claude_context in config.json
COMPACT = 0.9        # a session is compacted when its context is this full (sessions.COMPACT)
# How hard Claude thinks before it answers, as the user picked it in the agent panel (Claude Code's --effort, the API's
# output_config.effort). Set for one message of a conversation (workspace._planning); the agent's small jobs of their
# own (captions, checks) keep each model's default. Empty: the model's default.
EFFORT = contextvars.ContextVar("claude_effort", default="")
LEVELS = ("low", "medium", "high", "xhigh", "max")
NO_MEMORY = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}   # the owner's own notes of the folder never reach a studio session
# What Claude Code says when it did not answer, read by failure(): only where it gives no structured reason (an HTTP
# status, a rate limit event, the error of an assistant message).
LIMITED = re.compile(r"usage limit|rate.?limit|limit reached|out of (extra )?usage|overloaded|try again later|\b(429|529)\b", re.IGNORECASE)
SIGNED_OUT = re.compile(r"\blog ?in\b|logged out|not signed|authenticat|oauth|invalid api key|\b401\b", re.IGNORECASE)
API_KEY, LOCAL_SIGNIN = "api_key", "this_pc"   # the connections (claude_connection.MODES)
# How the studio reaches Claude now: claude_connection.apply() sets it from the console's choice (keys included, so it
# is never sent to a page), read afresh by every call. The default: Claude on this PC, with no key.
CONNECTION = {"mode": LOCAL_SIGNIN, "api_key": ""}
# Variables that would make Claude Code use an API key or token instead of its sign-in: never given to it on this PC's
# sign-in, so the subscription is what is used, and never a key that happens to be in the studio's environment.
KEY_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
# Called before every call that runs Claude Code, or None: raises Failed when the user of the request may not use the
# agent now (claude_connection.guard: only admins, while the studio tests on a personal subscription).
GUARD = None
NOT_INSTALLED = ("Claude Code is not installed on this PC: install it (claude.ai/code), so `claude` is on PATH or in "
                 "~/.local/bin.")
NO_API_KEY = "Paste an Anthropic API key, or pick Claude on this PC, in Servers & APIs → Providers."
SIGNED_OUT_HERE = "Signed out. Press Sign in on Claude on this PC, in Servers & APIs → Providers."


def signed_out_said():
    """What the user is told when Claude Code is not signed in, by the connection in use."""
    if CONNECTION.get("mode") == LOCAL_SIGNIN:
        return "Claude Code on this PC is not signed in: press Sign in on Claude on this PC, in Servers & APIs → Providers."
    return ("Claude Code is not signed in: the Anthropic API key is missing or was refused. Check it in Servers & APIs, "
            "Claude connection.")


class Busy(Exception):
    """Claude is at a usage limit or overloaded for now."""


class Failed(Exception):
    """Claude Code could not answer; the message says what to do."""


class Lost(Failed):
    """The session a thread goes on with is gone (Claude Code cleaned it up): the conversation starts a new one."""


def failure(said="", limits=None, status=None, kind=None, default="Claude could not answer: {}"):
    """What Claude Code not answering means, as the exception to raise: Busy (a usage limit, or Anthropic overloaded),
    Lost (the session is gone), or Failed (signed out, or anything else). The one place its words are read.
    said: what it said (a result's text, an error's message, what it printed); limits: its last rate limit event;
    status: the HTTP status of the call that failed (a result's api_error_status); kind: the error of an assistant
    message (the SDK's AssistantMessageError: "rate_limit", "authentication_failed", "billing_error" ...). The
    structured reasons come first; words are read only without them. default: the message of a Failed nothing here
    knows, with {} for what was said (quoted, at most 300 characters)."""
    said = " ".join(str(said or "").split())
    if kind == "rate_limit" or (limits or {}).get("status") == "rejected" or status in (429, 529):
        return Busy("Claude is at its usage limit{}".format(resets(limits)))
    if "no conversation found" in said.lower():
        return Lost("The conversation's Claude session is gone.")
    if kind == "authentication_failed" or status == 401:
        return Failed(signed_out_said())
    if kind == "billing_error":
        return Failed("Claude Code's account could not pay for this message: check its plan and extra usage on claude.ai."
                      if CONNECTION.get("mode") != API_KEY else
                      "The Anthropic API key's account could not pay for this message: check its credit on console.anthropic.com.")
    if LIMITED.search(said):
        return Busy("Claude is at its usage limit{}".format(resets(limits)))
    if SIGNED_OUT.search(said):
        return Failed(signed_out_said())
    return Failed(default.format(said[:300] or "Claude Code stopped without an answer."))


def find():
    """The claude program a local connection runs: the one on PATH, else where Claude Code's own installer puts it
    (~/.local/bin, not always on the PATH the studio starts with). "" when there is none."""
    found = shutil.which("claude")
    if found:
        return found
    for candidate in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if candidate.is_file():
            return str(candidate)
    return ""


def service(models, timeout=600, fast="", home="", window=WINDOW):
    """The Claude service for Agent(services=...), or None when it is off (no models named). Whether Claude Code can be
    reached is the connection's, asked at each call (CONNECTION), not here: it may be switched while the studio runs.
    models: the names to offer, comma separated, as Claude Code takes them ("sonnet, opus, haiku", or full model ids).
    fast: the one for the agent's small jobs (captions, notes, checks); empty = the one in use.
    home: the folder its sessions run in with the "api_key" connection (Claude Code files a session by that folder).
    window: the tokens of context its models have."""
    names = [m.strip() for m in str(models or "").split(",") if m.strip()]
    if not names or names[0].lower() in ("off", "none"):
        return None
    if sdk is None:   # the agent's every message runs in a live session (converse): there is no other way
        raise RuntimeError("Claude is offered to the agent (claude_models), but the Claude Agent SDK is not installed: "
                           "pip install claude-agent-sdk (it is in backend/requirements.txt).")
    return {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": names, "only": "", "cli": "claude",
            "timeout": max(30, int(timeout or 600)), "fast": str(fast or "").strip(),
            "home": str(home or Path(tempfile.gettempdir()) / "scene-claude"), "window": int(window or WINDOW)}


def efforts(model):
    """The effort levels `model` takes, and the one it uses when none is chosen: (levels, default). No levels: it has
    no effort setting. The names Claude Code takes stand for the newest of their family: "opus" is Opus 5.5, "sonnet"
    Sonnet 5.5, "haiku" Haiku 5.5."""
    name = str(model or "").lower().rsplit("/", 1)[-1]
    if re.search(r"haiku-(3|4)|claude-3|sonnet-(3|4-[0-5])|opus-(3|4-[0-4]|4$)", name):
        return [], None                                     # Haiku 4.5, Sonnet 4.5 and older: none
    if re.search(r"opus-4-5", name):
        return ["low", "medium", "high"], "high"
    if re.search(r"4-6", name):
        return ["low", "medium", "high", "max"], "high"     # xhigh came with Opus 4.7
    if name in ("opus", "haiku") or re.search(r"opus-5-5|haiku-5", name):
        return list(LEVELS), "medium"                       # Opus 5.5 and Haiku 5.5 default to medium
    if re.search(r"opus|sonnet|fable|mythos", name):
        return list(LEVELS), "high"
    return list(LEVELS), None


def chosen_effort(model, wanted):
    """The effort to ask `model` for: `wanted` when the model takes it, else nothing (its default)."""
    wanted = str(wanted or "").strip().lower()
    return wanted if wanted in efforts(model)[0] else ""


def session_settings(s):
    """The settings of Claude Code for the studio's sessions, as JSON: the owner's memory off, and compacted on its own
    when the context is COMPACT full."""
    window = int((s or {}).get("window") or WINDOW)
    return json.dumps({"autoMemoryEnabled": False, "autoCompactWindow": max(100_000, min(1_000_000, int(window * COMPACT)))})


def prompt_of(messages):
    """(system prompt, the text blocks of the one message Claude Code is sent). A conversation of several turns (the
    agent's loop of tool calls) is sent as one message with a block for each turn, in order: each round of the loop
    then opens with the blocks of the round before, and Claude reads those from its cache instead of anew."""
    system = str(messages[0].get("content") or "") if messages and messages[0].get("role") == "system" else ""
    rest = messages[1:] if system else list(messages)
    if len(rest) == 1:
        return system, [str(rest[0].get("content") or "")]
    return system, ["The conversation so far, oldest first, a block for each turn. Answer its last message.",
                    *("[{}]\n{}".format(m.get("role") or "user", m.get("content") or "") for m in rest)]


gate = None   # made on first use, inside the event loop that uses it


@contextlib.asynccontextmanager
async def answering():
    """One of the PARALLEL places, held while a call to Claude runs (more wait their turn): the calls a subscription
    takes at once are shared by everyone. RUNNING["answering"] counts the calls holding one, for the console's card."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
    async with gate:
        RUNNING["answering"] += 1
        try:
            yield
        finally:
            RUNNING["answering"] -= 1


async def ask(s, model, messages, schema, images=(), thread=None, web=False):
    """Ask Claude through Claude Code. Returns (the answer as JSON text, {"prompt", "cached", "answer"} tokens, the
    account's usage limits as Claude Code reported them or None). Raises Busy, Lost or Failed.
    thread: the conversation's session ({"id", "sent"}), or None for a call of its own. With an id, only the messages
    after the first `sent` go, and only the user's: the session already holds Claude's own answers. Its id and `sent`
    are kept up to date here. web: Claude may search the web (WEB_TOOLS) before it answers."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
    await guarded()
    going_on = bool(thread and thread.get("id"))
    if going_on:
        system = str(messages[0].get("content") or "") if messages and messages[0].get("role") == "system" else ""
        new = [m for m in messages[thread.get("sent") or 1:] if m.get("role") != "assistant"]
        blocks = [str(m.get("content") or "") for m in new] or ["Go on."]
    else:
        system, blocks = prompt_of(messages)
    content = [*({"type": "text", "text": text} for text in blocks), *({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                                                "data": picture}} for picture in images)]
    line = json.dumps({"type": "user", "message": {"role": "user", "content": content}}, ensure_ascii=False)
    args = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", model,
            "--tools", ",".join(WEB_TOOLS) if web else "", "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
            "--max-turns", str(MAX_TURNS + (WEB_TURNS if web else 0)), "--settings", session_settings(s)]
    if web:
        args += ["--allowedTools", " ".join(WEB_TOOLS)]
    if thread is not None and EFFORT.get():
        args += ["--effort", EFFORT.get()]   # a conversation's message: the effort the user picked
    if going_on:
        args += ["--resume", thread["id"]]
    elif thread is None:
        args += ["--no-session-persistence"]   # a call of its own: nothing is kept
    if isinstance(schema, dict):
        args += ["--json-schema", json.dumps(schema)]
    else:
        system += "\n\nAnswer with one JSON object and nothing else."
    # The system prompt goes as a file, since a long one does not fit on a Windows command line (files of _run). A call
    # of its own runs in an empty folder thrown away after, so no CLAUDE.md, settings or memory reach it; a thread runs
    # in `home`, always the same, where Claude Code keeps its sessions.
    args += ["--system-prompt-file", "@system_prompt"]
    where = s["home"] if thread is not None else None
    async with answering():
        run = await _run(args, line, where, s["timeout"], {"system_prompt": system})
    got = read(run.stdout, run.stderr)
    if thread is not None:
        thread.update(id=got["session"] or thread.get("id"), sent=len(messages), size=got["size"])
    return got["answer"], got["tokens"], got["limits"]


Ran = collections.namedtuple("Ran", "stdout stderr code")


async def _run(args, line, room, timeout, files=None, program=None):
    """One run of Claude Code to its end, through the connection in use: `line` on its stdin, which is then closed.
    Returns what it printed (Ran). args: claude's arguments, without the program; files: {name: text} for the
    arguments "@name" (_placed); room: the folder it runs in with a local connection (None: an empty one, thrown
    away after); program: the program to run instead of the connection's (a check of `claude -v`). Raises Busy or
    Failed, also when it takes longer than `timeout` seconds."""
    with tempfile.TemporaryDirectory(prefix="scene-claude-") as spare:
        if room:
            Path(room).mkdir(parents=True, exist_ok=True)
        program = program or connected()
        out, err = [], []

        async def whole():
            await program.start(args, files, NO_MEMORY, room or spare)
            if line:
                await program.write(line + "\n")
            await program.end_input()
            async for stream, text in program.output():
                (out if stream == "stdout" else err).append(text)
        try:
            await asyncio.wait_for(whole(), timeout)
        except asyncio.TimeoutError:
            raise Failed("Claude took longer than {} s to answer. Raise claude_timeout in config.json.".format(timeout))
        finally:
            await program.stop()
    return Ran("".join(out), "".join(err), program.code)


def read(stdout, stderr=""):
    """What one run of Claude Code printed (stream-json, one event a line): {"answer" (JSON text), "tokens" (of the
    whole run), "limits", "session" (its id), "size" (the tokens its last call to the model read: how long the
    session has grown)}."""
    result, limits, last_call = None, None, None
    for raw in str(stdout or "").splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "rate_limit_event" and isinstance(event.get("rate_limit_info"), dict):
            limits = event["rate_limit_info"]
            note_limits(limits)
        elif event.get("type") == "assistant" and not event.get("parent_tool_use_id")                 and isinstance((event.get("message") or {}).get("usage"), dict):
            last_call = event["message"]["usage"]
        elif event.get("type") == "result":
            result = dict(event, last_call=last_call)
    return judged(result, limits, " ".join([str(stderr or "")] + [line for line in str(stdout or "").splitlines() if not line.startswith("{")]))


def call_size(result, usage, number):
    """How long the session has grown: the tokens its latest call to the model read. From that call's own usage as it
    streamed (result["last_call"]), else the result's last iteration. Never the result's usage itself: that adds up
    every call of the turn (a turn of ten tool steps on a 150k context reads 1.5M), which is no context's size."""
    last = result.get("last_call") if isinstance(result.get("last_call"), dict) else None
    if last is None:
        calls = [c for c in usage.get("iterations") or [] if isinstance(c, dict)]
        last = calls[-1] if calls else {}
    return sum(number(last.get(k)) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def judged(result, limits, printed="", kind=None):
    """read() of Claude Code's result event (a dict) and its last rate limit event: raises Busy, Lost or Failed when it
    did not answer (failure()). printed: what else it said, for the error; kind: the error an assistant message gave."""
    if result is None or result.get("is_error") or result.get("subtype") != "success":
        said = " ".join(str((result or {}).get("result") or "").split()) or " ".join(str(printed or "").split())[-300:]
        raise failure(said, limits, (result or {}).get("api_error_status"), kind)
    answer = result.get("structured_output")
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    number = lambda v: int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    cached, written = number(usage.get("cache_read_input_tokens")), number(usage.get("cache_creation_input_tokens"))
    tokens = {"prompt": number(usage.get("input_tokens")) + written + cached,
              "cached": cached, "written": written, "answer": number(usage.get("output_tokens"))}
    size = call_size(result, usage, number)
    return {"answer": json.dumps(answer, ensure_ascii=False) if isinstance(answer, dict) else str(result.get("result") or ""),
            "tokens": tokens, "limits": limits, "session": result.get("session_id"), "size": size}


# ---------------------------------------------------------------- one run of `claude`
#
# Every run of Claude Code goes through a program of the connection in use (connected(), a LocalProgram): a call of its own (ask), a
# command (command) and a live session (the SDK's Transport, _Through). A program is started with claude's arguments,
# without the program's name, and with files given as text ({"system_prompt": ...}, named "@system_prompt" in the
# arguments); it is written to, its stdin closed, and its output read, a piece at a time, as ("stdout" | "stderr", text),
# until it ends with its exit code (`code`). stop() lets it go: its stdin closed, a moment to end, then it is ended.

PIECE = 65536      # bytes of its output read at a time
LET_GO = 5         # seconds a program has to end once its stdin is closed (it writes its session's file), before it is ended
RUNNING = collections.Counter()   # "now": the programs running for this studio (the console's Claude connection card)
RUN_WITH = ()      # what runs the claude program: nothing, it is one (the tests' fake claude is a Python script: Python)


async def guarded():
    """Raises Failed when this request's user may not use the agent now (GUARD)."""
    if GUARD is not None:
        await GUARD()


def connection_mark():
    """A short mark of the connection in use, keys included: it changes whenever the connection does."""
    return hashlib.sha1(json.dumps(CONNECTION, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def connected():
    """A program of the connection in use (CONNECTION), not started yet. The API key connection with no key is refused,
    never run on whatever account Claude Code here is signed in with: a subscription is used only when it is picked."""
    if CONNECTION.get("mode") == API_KEY:
        if not CONNECTION.get("api_key"):
            raise Failed(NO_API_KEY)
        return LocalProgram(CONNECTION["api_key"])
    return LocalProgram(api_key="")   # Claude on this PC: its sign-in


def _placed(args, files, folder):
    """The arguments with each "@name" of `files` made the path of a file in `folder` that holds its text."""
    placed = []
    for arg in args:
        name = arg[1:] if arg.startswith("@") else None
        if name in (files or {}):
            path = Path(folder) / (name + ".txt")
            path.write_text(files[name], encoding="utf-8")
            arg = str(path)
        placed.append(arg)
    return placed


def refused(error):
    """A call claude_policy.py refused, as the studio says it: a bug in how the studio builds the call, never the user's."""
    return Failed("The studio would not let this through to Claude Code ({}). That is a bug in how the studio builds the "
                  "call: see claude_policy.py.".format(error))


class LocalProgram:
    """Claude Code run here: the `claude` of this PC (find). With an API key (the "api_key" connection), the key is put
    in its environment; without one (Claude on this PC), every key or token variable is taken out of it (KEY_VARIABLES),
    so it uses the account it is signed in with. Either way claude_policy.py checks its arguments and environment
    before it starts and each line written to its stdin; a control request it refuses is answered here, on claude's
    stdout at a line's end, and the session goes on."""

    def __init__(self, api_key=""):
        self.api_key, self.process, self.code, self.folder, self.readers = api_key, None, None, None, []
        self.pieces = asyncio.Queue()
        self.plan, self.pending = None, ""
        self.mid_line, self.answers = False, []   # claude's stdout stopped inside a line; answers waiting for its end

    async def start(self, args, files=None, env=None, cwd=None):
        program = find()
        if not program:
            raise Failed(NOT_INSTALLED)
        self.folder = tempfile.mkdtemp(prefix="scene-claude-files-")
        try:
            placed = _placed(args, files, self.folder)
            self.plan = claude_policy.parse(placed, prompt_folder=self.folder)
            extra = claude_policy.environment(env)
        except claude_policy.Refused as error:
            shutil.rmtree(self.folder, ignore_errors=True)
            raise refused(error)
        environment = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}   # the studio may itself be started from Claude Code
        environment.update(extra)
        for name in KEY_VARIABLES:
            environment.pop(name, None)
        if self.api_key:
            environment["ANTHROPIC_API_KEY"] = self.api_key
        try:
            self.process = await asyncio.create_subprocess_exec(
                *RUN_WITH, program, *placed, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=cwd or None, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            shutil.rmtree(self.folder, ignore_errors=True)
            raise Failed("Claude Code can't be started ({}). {}".format(error, NOT_INSTALLED))
        RUNNING["now"] += 1
        self.readers = [asyncio.ensure_future(self._pump(name, getattr(self.process, name))) for name in ("stdout", "stderr")]

    async def _pump(self, name, stream):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            chunk = await stream.read(PIECE)
            text = decoder.decode(chunk, final=not chunk)
            if text:
                await self.pieces.put((name, text))
                if name == "stdout":
                    self.mid_line = not text.endswith("\n")
                    if not self.mid_line:
                        await self._answered()
            if not chunk:
                if name == "stdout":
                    self.mid_line = False
                    await self._answered()
                await self.pieces.put((name, None))
                return

    async def _answered(self):
        """The answers to refused control requests, put in claude's stdout now that it is at a line's end."""
        while self.answers:
            await self.pieces.put(("stdout", self.answers.pop(0)))

    async def write(self, text):
        """Write to claude's stdin, a whole line at a time, each as claude_policy.stdin_line lets it through."""
        if self.plan is not None and not self.plan.stream_input and text:
            raise refused("this run takes no stdin")
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if len(line) > claude_policy.MAX_LINE:
                raise refused("a stdin line is longer than {} MiB".format(claude_policy.MAX_LINE // 2 ** 20))
            await self._line(line + "\n")

    async def _line(self, line):
        try:
            forward, answer = claude_policy.stdin_line(line)
        except claude_policy.Refused as error:
            raise refused(error)
        if answer is not None:
            if self.mid_line:
                self.answers.append(answer)
            else:
                await self.pieces.put(("stdout", answer))
        if forward is None:
            return
        try:
            self.process.stdin.write(forward.encode("utf-8"))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):   # it has ended: its output says why
            pass

    async def end_input(self):
        if self.pending:   # a last line with no newline
            line, self.pending = self.pending, ""
            await self._line(line)
        if self.process is not None and not self.process.stdin.is_closing():
            self.process.stdin.close()

    async def output(self):
        ended = 0
        while ended < 2:
            name, text = await self.pieces.get()
            if text is None:
                ended += 1
            else:
                yield name, text
        self.code = await self.process.wait()

    async def stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.returncode is None:
                with contextlib.suppress(OSError):
                    process.stdin.close()
                try:
                    await asyncio.wait_for(process.wait(), LET_GO)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
        finally:
            RUNNING["now"] -= 1
            for reader in self.readers:
                reader.cancel()
            shutil.rmtree(self.folder, ignore_errors=True)


# ---------------------------------------------------------------- live sessions
#
# A conversation of the agent panel (a tab) keeps its Claude Code running between its messages, through the Claude
# Agent SDK: a message is answered at once, without starting the program and reading its session anew, and the
# studio's tools are Claude's own tools (an MCP server inside the studio), which it calls as it goes in one turn.
# A session no one wrote to for IDLE is closed, and so is the oldest past LIVE; its next message opens it again.
# A message from outside a tab gets a session of its own (oneoff()): at most ONEOFF_LIVE of those at once, more wait
# their turn, and they never count against LIVE, so a burst of them never pushes a tab's session out.

IDLE = 15 * 60   # seconds
LIVE = 6         # live sessions of tabs at once: each is a program of its own, holding a few hundred MB of memory
ONEOFF = "oneoff:"   # the key of a session opened for one message outside a tab (oneoff())
ONEOFF_LIVE = 2      # such sessions at once; more wait for one to end. Each also takes a place of PARALLEL as it answers.
WATCH = 1.0      # seconds between looks at a turn that may have gone quiet (_next)
TOOLS_SERVER = "studio"


class _Live:
    """One conversation's running Claude Code: its client, the session it holds and what it was opened with."""

    def __init__(self, signature):
        self.signature, self.client, self.session = signature, None, None
        self.lock = asyncio.Lock()
        self.used = time.monotonic()
        self.tools, self.called, self.context, self.result_chars = {}, [], None, 8000
        self.record, self.compacted = None, []   # record(kind, text, data): what happens in it, for its story (sessions.py)
        self.users = 0           # messages of converse() using this entry now (holding or waiting for its lock)
        self.heard = time.monotonic()   # when Claude Code last said something, or a tool of the studio's last ended
        self.running = 0         # the studio's tools running now for it (Claude Code is quiet while they work)
        self.seen = []           # the session ids Claude Code named in it (its start, its result), oldest first
        self.error_kind = None   # the error an assistant message of the turn gave (the SDK's AssistantMessageError)


live = {}   # a conversation's key (thread["key"]) -> its _Live
held = collections.Counter()   # a conversation's key -> messages using it now (holding()): its session is never closed to make room
_slots_of = {}   # a name -> (the event loop, its Semaphore): see _slots


def key_of(thread):
    """The key of a conversation's live session: its thread's "key", else its session id."""
    return (thread or {}).get("key") or (thread or {}).get("id") or "default"


@contextlib.contextmanager
def holding(key):
    """While this runs, the live session of `key` is in use: _tidy() never closes it to make room for another, even
    between the rounds of one message (a plan sent back to be fixed)."""
    held[key] += 1
    try:
        yield
    finally:
        held[key] -= 1
        if held[key] <= 0:
            del held[key]


def _slots(name, size):
    """A semaphore of `size` places for the running event loop (each test runs its own loop)."""
    loop = asyncio.get_running_loop()
    found = _slots_of.get(name)
    if found is None or found[0] is not loop:
        found = _slots_of[name] = (loop, asyncio.Semaphore(size))
    return found[1]


def _handlers(entry, names):
    """{name: async function(args) -> MCP result}: the tools Claude Code calls. Each runs the tool of the message being
    answered (entry.tools), in that message's request (its context: whose rows the database shows)."""
    def one(name):
        async def run(args):
            entry.called.append(name)
            tool = entry.tools.get(name)
            entry.running += 1
            try:
                if tool is None:
                    text = "{} is not on offer for this message: use the tools you have now.".format(name)
                else:
                    try:   # at most guard_tool_calls in a message, each within its time (guardrails.py)
                        text = await guardrails.run_tool(name, entry.called, guardrails.known("guard_tool_calls"),
                                                         lambda: asyncio.get_running_loop().create_task(tool(dict(args or {})), context=entry.context))
                    except (KeyError, ValueError, TypeError):
                        text = "That call could not be run. Check its fields."
            finally:
                entry.running -= 1
                entry.heard = time.monotonic()
            chars = entry.result_chars(name) if callable(entry.result_chars) else entry.result_chars
            from .agent import fit_result   # agent.py builds on this module: found once both are loaded
            return {"content": [{"type": "text", "text": fit_result(text, chars, name)}]}
        return run
    return {name: one(name) for name in names}


PROMPTS = Path(tempfile.gettempdir()) / "scene-claude-prompts"


def prompt_file(system):
    """The file a live session reads its system prompt from. On the command line the prompt (with a long skill, tens of
    thousands of characters) would pass Windows' limit of about 32,000, and the program would not start at all."""
    path = PROMPTS / (hashlib.sha1(system.encode("utf-8")).hexdigest() + ".txt")
    if not path.is_file():
        PROMPTS.mkdir(parents=True, exist_ok=True)
        path.write_text(system, encoding="utf-8")
    return str(path)


def _options(s, settings):
    """The ClaudeAgentOptions of one conversation's client. settings: {"model", "system", "schema", "tools": {name:
    (about, input schema)}, "handlers", "resume", "max_turns", "web", "effort"}. With "web", Claude Code's web search
    (WEB_TOOLS) is on too; "effort", how hard it thinks (EFFORT), or empty for the model's default."""
    tools = [sdk.tool(name, about, shape)(settings["handlers"][name]) for name, (about, shape) in settings["tools"].items()]
    web = list(WEB_TOOLS) if settings.get("web") else []
    return sdk.ClaudeAgentOptions(
        cli_path="claude", model=settings["model"], system_prompt={"type": "file", "path": prompt_file(settings["system"])}, tools=web,
        allowed_tools=["mcp__{}__{}".format(TOOLS_SERVER, name) for name in settings["tools"]] + web,
        mcp_servers={TOOLS_SERVER: sdk.create_sdk_mcp_server(TOOLS_SERVER, tools=tools)} if tools else {},
        strict_mcp_config=True, setting_sources=[], cwd=s["home"], resume=settings["resume"] or None,
        max_turns=settings["max_turns"], output_format={"type": "json_schema", "schema": settings["schema"]},
        settings=session_settings(s), env=dict(NO_MEMORY), effort=settings.get("effort") or None)


def sdk_arguments(options):
    """claude's arguments for a live session, as the SDK itself builds them from its options, without the program's
    name; and its files: the system prompt, as text ({"system_prompt": ...}, "@system_prompt" in the arguments)."""
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
    args, files = SubprocessCLITransport(prompt="", options=options)._build_command()[1:], {}
    if "--system-prompt-file" in args:
        at = args.index("--system-prompt-file") + 1
        files["system_prompt"] = Path(args[at]).read_text(encoding="utf-8")
        args[at] = "@system_prompt"
    return args, files


if sdk is not None:
    class _Through(sdk.Transport):
        """The SDK's way to Claude Code for one live session: a program of the connection in use (connected()),
        started with the arguments the SDK builds (sdk_arguments) and its options' env (NO_MEMORY), in its cwd."""

        def __init__(self, options):
            self.options, self.program, self.ready = options, None, False

        async def connect(self):
            args, files = sdk_arguments(self.options)
            self.program = connected()
            await self.program.start(args, files, dict(self.options.env or {}), str(self.options.cwd or "") or None)
            self.ready = True

        async def write(self, data):
            await self.program.write(data)

        def read_messages(self):
            return self._messages()

        async def _messages(self):
            pending, said = "", []
            async for stream, text in self.program.output():
                if stream == "stderr":
                    said.append(text)
                    continue
                pending += text
                *lines, pending = pending.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("{"):
                        yield json.loads(line)
            if pending.strip().startswith("{"):
                with contextlib.suppress(ValueError):
                    yield json.loads(pending)
            if self.program.code not in (0, None):
                raise sdk.ProcessError("Claude Code stopped", exit_code=self.program.code, stderr="".join(said)[-1000:] or None)

        async def close(self):
            self.ready = False
            if self.program is not None:
                await self.program.stop()

        def is_ready(self):
            return self.ready

        async def end_input(self):
            if self.program is not None:
                await self.program.end_input()


async def _open(s, settings):
    """A connected client for one conversation (settings: see _options), through the connection in use (_Through)."""
    Path(s["home"]).mkdir(parents=True, exist_ok=True)
    options = _options(s, settings)
    client = sdk.ClaudeSDKClient(options, transport=_Through(options))
    await asyncio.wait_for(client.connect(), 60)
    return client


async def _shut(entry):
    """Let go of an entry's running program (its session stays, for the next message to resume)."""
    client, entry.client = entry.client, None
    if client is not None:
        try:
            await asyncio.wait_for(client.disconnect(), 15)
        except Exception as error:   # it is let go either way
            print("A Claude session did not close cleanly: {}".format(error))


async def _close(key, entry=None):
    """Close a conversation's live session and forget it here (only `entry`, when given, not one opened since)."""
    found = live.get(key)
    if found is None or (entry is not None and found is not entry):
        found = entry
    else:
        live.pop(key, None)
    if found is not None:
        await _shut(found)


async def close_all(starting=""):
    """Close every live session (the studio stops), or the ones whose key starts so (a conversation deleted)."""
    for key in [k for k in live if k.startswith(starting)]:
        await _close(key)


def _busy(key, entry):
    return bool(held.get(key)) or entry.users > 0 or entry.lock.locked()


async def _tidy():
    """Close the sessions idle for IDLE, then the tabs' ones used longest ago past LIVE: never one in use (answering,
    waiting to, or between the rounds of a message), and never a one-off session (oneoff() closes its own)."""
    now = time.monotonic()
    for key, entry in list(live.items()):
        if not key.startswith(ONEOFF) and now - entry.used > IDLE and not _busy(key, entry):
            await _close(key, entry)
    while True:
        tabs = [(entry.used, key) for key, entry in live.items() if not key.startswith(ONEOFF)]
        idle = [(used, key) for used, key in tabs if not _busy(key, live[key])]
        if len(tabs) <= LIVE or not idle:
            break
        await _close(min(idle)[1])


def _events_of(message):
    """[(kind, text, data)] of one message of a live session, for its story (sessions.KINDS)."""
    found = []
    if isinstance(message, sdk.AssistantMessage):
        for block in message.content or []:
            if isinstance(block, sdk.TextBlock) and block.text.strip():
                found.append(("text", block.text, None))
            elif isinstance(block, sdk.ThinkingBlock) and block.thinking.strip():
                found.append(("thinking", block.thinking, None))
            elif isinstance(block, sdk.ToolUseBlock):
                found.append(("tool_call", str(block.name).split("__")[-1], {"input": block.input, "id": block.id}))
    elif isinstance(message, sdk.UserMessage) and isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, sdk.ToolResultBlock):
                content = block.content
                text = content if isinstance(content, str) else " ".join(
                    str(part.get("text") or "") for part in content or [] if isinstance(part, dict))
                found.append(("tool_result", text, {"id": block.tool_use_id, "error": bool(block.is_error)}))
    elif isinstance(message, sdk.SystemMessage) and message.subtype == "compact_boundary":
        meta = (message.data or {}).get("compact_metadata") or {}
        found.append(("compact", "Compacted the context ({})".format(meta.get("trigger") or "auto"), meta))
    return found


def _session_named(message):
    """The session id a message of the stream names: the start of a session (system "init") and the result do."""
    if isinstance(message, sdk.SystemMessage) and message.subtype == "init":
        return (message.data or {}).get("session_id")
    if isinstance(message, sdk.ResultMessage):
        return message.session_id
    return None


def _told(entry, message):
    named = _session_named(message)
    if named and named not in entry.seen:
        entry.seen.append(named)
    if isinstance(message, sdk.AssistantMessage) and getattr(message, "error", None):
        entry.error_kind = message.error
    for kind, text, data in _events_of(message):
        if kind == "compact":
            entry.compacted.append(data)
        if kind == "tool_call" and text in WEB_TOOLS:   # Claude Code's own tool: it is not one of the studio's handlers
            entry.called.append(text)
        if entry.record:
            try:
                entry.record(kind, text, data)
            except Exception as error:   # the story is kept beside the conversation: a failure there never stops it
                print("A Claude session's event was not kept: {}".format(error))


async def _next(entry, stream, quiet):
    """The stream's next message. Raises StopAsyncIteration at its end, and Failed when Claude Code has said nothing
    for `quiet` seconds while none of the studio's tools ran for it (a tool's own time is the tool's: a film operation
    may take many minutes). quiet 0: waits as long as it takes."""
    if not quiet:
        return await stream.__anext__()
    task = asyncio.ensure_future(stream.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait([task], timeout=WATCH)
            if done:
                return task.result()
            if not entry.running and time.monotonic() - entry.heard > quiet:
                raise Failed("Claude Code said nothing for {} s, so this message was stopped. Try again; if it happens "
                             "often, raise claude_timeout in config.json.".format(quiet))
    finally:
        if not task.done():
            task.cancel()


async def _turn(entry, text, quiet=0):
    """One message to the live session; returns (its result as a result event, the last rate limit event). quiet: see
    _next."""
    result, limits, last_call = None, None, None
    async with answering():
        entry.heard, entry.error_kind = time.monotonic(), None
        await entry.client.query(text)
        stream = entry.client.receive_response().__aiter__()
        while True:
            try:
                message = await _next(entry, stream, quiet)
            except StopAsyncIteration:
                break
            entry.heard = time.monotonic()
            _told(entry, message)
            if isinstance(message, sdk.RateLimitEvent):
                info = message.rate_limit_info
                limits = dict(info.raw or {"status": info.status, "resetsAt": info.resets_at})
                note_limits(limits)
            elif isinstance(message, sdk.AssistantMessage) and not message.parent_tool_use_id and isinstance(message.usage, dict):
                last_call = message.usage   # the context the session's latest call to the model read (call_size)
            elif isinstance(message, sdk.ResultMessage):
                result = {"type": "result", "subtype": message.subtype, "is_error": message.is_error, "session_id": message.session_id,
                          "result": message.result or " ".join(message.errors or []), "structured_output": message.structured_output,
                          "usage": message.usage or {}, "api_error_status": message.api_error_status, "last_call": last_call}
    return result, limits


async def converse(s, model, system, text, schema, thread, tools, about, finish_now, max_turns, result_chars=8000, web=False):
    """One message of a conversation in its live session. Returns (the answer as JSON text, {"prompt", "cached",
    "answer"} tokens, the usage limits or None, the names of the tools it called in order). Raises Busy, Lost or Failed.
    thread: the conversation's {"key", "id", ...}; its id (the session) and size are kept up to date here. A one-off
    thread (oneoff()) also gets "opened": every session id Claude Code named, so they can be removed however it ends.
    tools: {name: async function(call) -> str}, the studio's tools for this message; about: {name: (what it does,
    its input schema)}, every tool the session offers. A turn that runs out of max_turns is asked finish_now.
    result_chars: how much of a tool's result Claude is given, in characters: a number, or a function of the tool's name
    (agent.result_chars). web: Claude Code's web search is on in the session (WEB_TOOLS). A turn in which Claude Code
    says nothing for the service's timeout (claude_timeout) while no tool runs is stopped (Failed)."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
    await guarded()
    key = key_of(thread)
    effort = EFFORT.get()
    # A session opened with another effort is opened again (going on with the same conversation): it is set as it starts.
    # So is one opened by another connection (switched in the console): its program runs that way.
    signature = json.dumps([model, system, schema, sorted(about), max_turns, bool(web), effort, connection_mark()], sort_keys=True)
    if text.lstrip().startswith("/"):   # a message is never taken for a command of Claude Code's (/compact): command() runs those
        text = "Message:\n" + text
    quiet = int(s.get("timeout") or 0)
    with holding(key):
        entry = live.get(key)
        if entry is None:
            closing, refused = guardrails.sessions_to_close(live, key, guardrails.known("guard_sessions_per_user"),
                                                            busy=_busy)   # in use as _tidy() sees it: held between rounds too
            for old in closing:   # one person holds at most their share of the live sessions
                await _close(old)
            if refused:
                raise Failed(refused)
            entry = live[key] = _Live(signature)
        entry.users += 1
        try:
            await _tidy()
            async with entry.lock:
                if key not in live:   # let go while this message waited (a deleted conversation): it is this one's again
                    live[key] = entry
                if entry.client is not None and (entry.signature != signature or entry.session != thread.get("id")):
                    await _shut(entry)   # opened for another prompt, shape or session: opened again, going on with the session
                entry.signature = signature
                entry.tools, entry.called, entry.context, entry.result_chars = tools, [], contextvars.copy_context(), result_chars
                entry.record, entry.compacted, entry.seen = thread.get("record"), [], []
                try:
                    if entry.client is None:
                        entry.session = thread.get("id")
                        entry.client = await _open(s, {"model": model, "system": system, "schema": schema, "tools": about,
                                                       "handlers": _handlers(entry, about), "resume": thread.get("id"),
                                                       "max_turns": max_turns, "web": web, "effort": effort})
                    result, limits = await _turn(entry, text, quiet)
                    tokens = None
                    if (result or {}).get("subtype") == "error_max_turns":   # still working when its turns ran out: it answers now
                        tokens = judged(dict(result, subtype="success", is_error=False), limits)["tokens"]
                        result, limits = await _turn(entry, finish_now, quiet)
                    got = judged(result, limits, kind=entry.error_kind)
                except asyncio.CancelledError:   # the user stopped it: the program goes, the session stays for the next message
                    await asyncio.shield(_let_go(key, entry))
                    raise
                except (Busy, Failed):
                    await _let_go(key, entry)
                    raise
                except Exception as error:   # the SDK's own errors: the program could not be started, or stopped
                    await _let_go(key, entry)
                    if sdk is not None and isinstance(error, getattr(sdk, "CLINotFoundError", ())):
                        raise Failed("Claude Code can't be started ({}). {}".format(error, NOT_INSTALLED)) from error
                    raise failure(str(error), kind=entry.error_kind, default="Claude Code stopped: {}") from error
                finally:
                    entry.used = time.monotonic()
                    if key.startswith(ONEOFF):
                        thread["opened"] = list(dict.fromkeys([*(thread.get("opened") or []), *entry.seen]))
                entry.session = got["session"] or thread.get("id")
        finally:
            entry.users -= 1
    thread.update(id=entry.session, size=got["size"], compacted=len(entry.compacted) + (thread.get("compacted") or 0))
    total = {k: got["tokens"][k] + (tokens or {}).get(k, 0) for k in got["tokens"]}
    return got["answer"], total, got["limits"], list(entry.called)


async def _let_go(key, entry):
    """A message failed or was stopped: its program goes. The entry goes too, unless another message waits for it."""
    if entry.users <= 1 and live.get(key) is entry:
        live.pop(key, None)
    await _shut(entry)


@contextlib.asynccontextmanager
async def oneoff(s):
    """A thread for one message outside a tab: a session of its own, opened by its first converse(), then closed and
    its files removed (forget) when the message ends, however it ends: answered, failed, stopped or timed out. At most
    ONEOFF_LIVE are open at once; more wait their turn here. They never count against LIVE: a burst of them never
    closes a tab's session."""
    thread = {"key": ONEOFF + uuid.uuid4().hex, "id": None, "opened": []}
    async with _slots("oneoff", ONEOFF_LIVE):
        try:
            yield thread
        finally:
            await asyncio.shield(_discard(s, thread))


async def _discard(s, thread):
    await _close(thread["key"])
    for session in dict.fromkeys([thread.get("id"), *(thread.get("opened") or [])]):
        if session:
            try:
                await asyncio.to_thread(forget, s, session)
            except OSError as error:   # a file in use stays: nothing reads it again
                print("A one-off Claude session's file was not removed: {}".format(error))


async def command(s, thread, text):
    """A command of Claude Code's (/compact, /rename ...) in a conversation's session: in its live program when it has
    one, else in a run of its own that goes on with the session. Returns {"compacted": the compact_metadata of a
    compaction (pre_tokens, post_tokens) or None, "session": its id}."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
    await guarded()
    key, name = key_of(thread), text.split()[0]
    entry = live.get(key)
    if entry is not None and entry.client is not None and entry.session == thread.get("id"):
        with holding(key):
            entry.users += 1
            try:
                async with entry.lock:
                    if entry.client is not None and entry.session == thread.get("id"):   # still so once its turn came
                        entry.record, entry.compacted, entry.seen = thread.get("record"), [], []
                        try:
                            result, limits = await _turn(entry, text, int(s.get("timeout") or 0))
                            if result is not None and (result.get("is_error") or result.get("subtype") != "success"):
                                said = " ".join(str(result.get("result") or "").split())
                                raise failure(said, limits, result.get("api_error_status"), entry.error_kind,
                                              default="Claude Code could not do " + name + ": {}")
                        except (Busy, Failed):
                            await _let_go(key, entry)
                            raise
                        except Exception as error:
                            await _let_go(key, entry)
                            raise failure(str(error), kind=entry.error_kind, default="Claude Code could not do " + name + ": {}") from error
                        finally:
                            entry.used = time.monotonic()
                        done = entry.compacted[-1] if entry.compacted else None
                        return {"compacted": done, "session": entry.session}
            finally:
                entry.users -= 1
    if not thread.get("id"):
        raise Failed("This conversation has no Claude session yet.")
    # The command goes on stdin, as a message of the session, never as an argument (claude_policy takes a prompt on the
    # command line only for these commands, and the SDK sends them so too).
    args = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--resume", thread["id"],
            "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--settings", session_settings(s)]
    # As the SDK sends one to a live session (query("/compact")): a message whose content is the command's text.
    line = json.dumps({"type": "user", "message": {"role": "user", "content": text}}, ensure_ascii=False)
    async with answering():
        run = await _run(args, line, s["home"], s["timeout"])
    done, session = None, thread["id"]
    for raw in str(run.stdout or "").splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "compact_boundary":
            done = event.get("compact_metadata") or {}
            if thread.get("record"):
                thread["record"]("compact", "Compacted the context ({})".format(done.get("trigger") or "manual"), done)
        elif event.get("type") == "result":
            session = event.get("session_id") or session
            if event.get("is_error"):
                raise failure(event.get("result"), None, event.get("api_error_status"),
                              default="Claude Code could not do " + name + ": {}")
    return {"compacted": done, "session": session}


async def compact(s, thread):
    """Compact a conversation's session now: Claude Code sums up the turns so far and goes on from that, in the same
    session. Returns the tokens its context holds after (None when Claude Code did not say)."""
    done = (await command(s, thread, "/compact"))["compacted"]
    after = (done or {}).get("post_tokens")
    if isinstance(after, int):
        thread["size"] = after
    thread["compacted"] = (thread.get("compacted") or 0) + 1
    return after


async def rename(s, thread, title):
    """Give a conversation's session its title, as Claude Code's other places list it (VS Code)."""
    clean = " ".join(str(title or "").split())[:120]
    if clean and thread.get("id"):
        await command(s, thread, "/rename " + clean)


def forget(s, session):
    """Remove the file Claude Code keeps a thread's session in (the conversation was deleted), from where Claude Code
    files a session: under its folder's path, every character but letters and digits made a dash, in its own home
    (~/.claude, or CLAUDE_CONFIG_DIR). It waits on the disk: run it off the event loop (asyncio.to_thread)."""
    if not s or not re.fullmatch(r"[0-9A-Za-z-]{8,64}", str(session or "")):
        return
    kept = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects" / re.sub(
        r"[^A-Za-z0-9]", "-", str(Path(s["home"]).resolve()))
    (kept / (session + ".jsonl")).unlink(missing_ok=True)
    shutil.rmtree(kept / session, ignore_errors=True)


# ---------------------------------------------------------------- the plan's limits
#
# On a Claude subscription, Claude Code reports how much of the plan is used in its rate_limit_event: the 5-hour session
# and the week, each a utilization (0..1) and when it resets. The last seen of each window is kept here, for the
# console's card (claude_connection.status), and handed to ON_LIMITS, which keeps it in the database so it is there
# after a restart and in the app's other processes. Ported from the SceneCloude bridge (usage.Ledger.limits).

LIMITS = {}        # a window's name ("five_hour", "seven_day") -> {"utilization", "status", "resets_at", "seen"}
ON_LIMITS = None   # called with LIMITS whenever they change (claude_connection.keep_limits), or None


def fraction(value):
    """Claude Code reports utilization as 0..1; a percentage is taken too."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return round(value / 100 if value > 1 else value, 4)


def note_limits(info):
    """Keep what a rate_limit_info says of each window: all of them (unifiedWindows), or at least the one it is about."""
    if not isinstance(info, dict):
        return
    now = time.time()
    windows = info.get("unifiedWindows") if isinstance(info.get("unifiedWindows"), dict) else {}
    for name, window in windows.items():
        if isinstance(window, dict):
            LIMITS[str(name)[:40]] = {"utilization": fraction(window.get("utilization")), "status": str(window.get("status") or "")[:20],
                                      "resets_at": window.get("resetsAt") or window.get("resets_at"), "seen": now}
    name = info.get("rateLimitType")
    if isinstance(name, str) and name not in windows:
        before = LIMITS.get(name[:40], {})
        LIMITS[name[:40]] = {"utilization": fraction(info.get("utilization")) if "utilization" in info else before.get("utilization"),
                             "status": str(info.get("status") or "")[:20], "resets_at": info.get("resetsAt"), "seen": now}
    if ON_LIMITS is not None:
        try:
            ON_LIMITS(dict(LIMITS))
        except Exception as error:   # the card's numbers only: a failure to keep them never stops a call
            print("The plan's limits were not kept: {}".format(error))


def plan_windows(kept=None):
    """{"session", "week"}: the 5-hour window and the week as last reported, {"utilization", "resets_at"}, or None
    until a call has reported one. A window whose reset time has passed shows as 0, with no reset time."""
    kept, now, found = LIMITS if kept is None else kept, time.time(), {}
    for window, called in (("five_hour", "session"), ("seven_day", "week")):
        seen = kept.get(window)
        if not isinstance(seen, dict):
            found[called] = None
            continue
        passed = isinstance(seen.get("resets_at"), (int, float)) and seen["resets_at"] < now
        found[called] = {"utilization": 0.0 if passed else seen.get("utilization"),
                         "resets_at": None if passed else seen.get("resets_at")}
    return found


def resets(limits):
    """", until 14:30" from Claude Code's rate limit event, or "" when it did not say."""
    when = (limits or {}).get("resetsAt")
    return ", until {}".format(time.strftime("%H:%M", time.localtime(when))) if isinstance(when, (int, float)) else ""
