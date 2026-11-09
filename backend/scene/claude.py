"""Claude as a model of the agent, through Claude Code on this machine: the `claude` program the CLI and the VS Code
extension share, signed in with its owner's Claude account, so no API key is needed. Each call runs `claude -p` once
with Claude Code's own tools, settings, MCP servers and skills off (but its web search, when the agent may research:
WEB_TOOLS): Claude only answers. The agent's tools, skills,
questions and Approve all stay in the studio (agent.py), the same as with any other model.

Calls draw on the account's usage limits (a five-hour and a seven-day window), shared with everything else its owner
does with Claude. A call refused at the limit is AgentBusy in agent.py: the user is told when the limit lifts.

A conversation of the studio is one session of Claude Code's (a thread, see agent.py): its first message carries
everything, and each later one only what is new; Claude Code keeps the rest and its cache holds it, so the turns
before are neither sent again by the studio nor read again at the full rate.

A conversation's session runs in the studio's own folder (`home`), so it is listed with the sessions of the folder in
Claude Code's other places (VS Code, `claude --resume`), titled "Studio · tab · project · user". Its owner's memory is
off in it, and it is compacted, still the same session, when its context is COMPACT full (sessions.py)."""

import asyncio
import contextvars
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

try:   # the Claude Agent SDK: keeps a conversation's Claude Code running between its messages (converse)
    import claude_agent_sdk as sdk
except ImportError:
    sdk = None

PARALLEL = 3   # calls running at once; more wait their turn (each is a program of its own, and all share one account)
MAX_TURNS = 3  # an answer in a schema takes two turns of Claude Code's (the answer, then its check)
# Claude Code's own web search, the one of its tools a studio session may use: the search runs at Anthropic, so it
# reaches nothing on this machine or its network. Reading a page is the studio's own tool (web_fetch, web.py), which
# fetches only public addresses: Claude Code's WebFetch runs here and would reach the render PC and localhost.
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
LIMITED = re.compile(r"usage limit|rate.?limit|limit reached|out of (extra )?usage|overloaded|try again later|429|529", re.IGNORECASE)
SIGNED_OUT = re.compile(r"log ?in|logged out|not signed|authenticat|oauth|invalid api key|401", re.IGNORECASE)


class Busy(Exception):
    """Claude is at a usage limit or overloaded for now."""


class Failed(Exception):
    """Claude Code could not answer; the message says what to do."""


class Lost(Failed):
    """The session a thread goes on with is gone (Claude Code cleaned it up): the conversation starts a new one."""


def find(path=""):
    """The claude program: `path` when it is set, else the one on PATH, else the native installer's, else the newest
    one a VS Code extension carries. "" when there is none."""
    if path:
        return path if Path(path).is_file() else ""
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    native = [home / ".local" / "bin" / name for name in ("claude.exe", "claude")]
    carried = glob.glob(str(home / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude*"))
    for candidate in [*(str(n) for n in native), *sorted(carried, key=os.path.getmtime, reverse=True)]:
        if Path(candidate).is_file():
            return candidate
    return ""


def service(models, path="", timeout=600, fast="", home="", window=WINDOW):
    """The Claude service for Agent(services=...), or None when it is off (no models named) or Claude Code isn't here.
    models: the names to offer, comma separated, as Claude Code takes them ("sonnet, opus, haiku", or full model ids).
    fast: the one for the agent's small jobs (captions, notes, checks); empty = the one in use.
    home: the folder its sessions run in (Claude Code files a session by that folder, and lists it with the folder's
    others). window: the tokens of context its models have."""
    names = [m.strip() for m in str(models or "").split(",") if m.strip()]
    if not names or names[0].lower() in ("off", "none"):
        return None
    program = find(path)
    if not program:
        print("Claude is not offered to the agent: Claude Code isn't installed on this machine{}.".format(
            " at " + path if path else ""))
        return None
    return {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": names, "only": "", "cli": program,
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


async def ask(s, model, messages, schema, images=(), thread=None, web=False):
    """Ask Claude through Claude Code. Returns (the answer as JSON text, {"prompt", "cached", "answer"} tokens, the
    account's usage limits as Claude Code reported them or None). Raises Busy, Lost or Failed.
    thread: the conversation's session ({"id", "sent"}), or None for a call of its own. With an id, only the messages
    after the first `sent` go, and only the user's: the session already holds Claude's own answers. Its id and `sent`
    are kept up to date here. web: Claude may search the web (WEB_TOOLS) before it answers."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
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
    args = [s["cli"], "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", model,
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
    # An empty folder to run in, so no CLAUDE.md, settings or memory of this project's reach it: a call of its own gets
    # one that is thrown away; a thread runs in `home`, always the same, where Claude Code keeps its sessions. The
    # system prompt goes in a file, since a long one does not fit on a Windows command line.
    with tempfile.TemporaryDirectory(prefix="scene-claude-") as room:
        (Path(room) / "system.txt").write_text(system, encoding="utf-8")
        args += ["--system-prompt-file", str(Path(room) / "system.txt")]
        where = room
        if thread is not None:
            Path(s["home"]).mkdir(parents=True, exist_ok=True)
            where = s["home"]
        async with gate:
            run = await asyncio.to_thread(_run, args, line, where, s["timeout"])
    got = read(run.stdout, run.stderr)
    if thread is not None:
        thread.update(id=got["session"] or thread.get("id"), sent=len(messages), size=got["size"])
    return got["answer"], got["tokens"], got["limits"]


def _run(args, line, room, timeout):
    env = {**{k: v for k, v in os.environ.items() if k != "CLAUDECODE"}, **NO_MEMORY}   # the studio may itself be started from Claude Code
    try:
        return subprocess.run(args, input=line + "\n", capture_output=True, text=True, encoding="utf-8", errors="replace",
                              cwd=room, env=env, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise Failed("Claude took longer than {} s to answer. Raise claude_timeout in config.json.".format(timeout))
    except OSError as error:
        raise Failed("Claude Code can't be started ({}). Set claude_path in config.json.".format(error))


def read(stdout, stderr=""):
    """What one run of Claude Code printed (stream-json, one event a line): {"answer" (JSON text), "tokens" (of the
    whole run), "limits", "session" (its id), "size" (the tokens its last call to the model read: how long the
    session has grown)}."""
    result, limits = None, None
    for raw in str(stdout or "").splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "rate_limit_event" and isinstance(event.get("rate_limit_info"), dict):
            limits = event["rate_limit_info"]
        elif event.get("type") == "result":
            result = event
    return judged(result, limits, " ".join([str(stderr or "")] + [line for line in str(stdout or "").splitlines() if not line.startswith("{")]))


def judged(result, limits, printed=""):
    """read() of Claude Code's result event (a dict) and its last rate limit event: raises Busy, Lost or Failed when it
    did not answer. printed: what else it said, for the error."""
    if result is None or result.get("is_error") or result.get("subtype") != "success":
        said = " ".join(str((result or {}).get("result") or "").split()) or " ".join(str(printed or "").split())[-300:]
        if (limits or {}).get("status") == "rejected" or (result or {}).get("api_error_status") in (429, 529) or LIMITED.search(said):
            raise Busy("Claude is at its usage limit{}".format(resets(limits)))
        if "no conversation found" in said.lower():
            raise Lost("The conversation's Claude session is gone.")
        if SIGNED_OUT.search(said):
            raise Failed("Claude Code on this machine is not signed in. Run claude in a terminal and type /login.")
        raise Failed("Claude could not answer: {}".format(said[:300] or "Claude Code stopped without an answer."))
    answer = result.get("structured_output")
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    number = lambda v: int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    cached, written = number(usage.get("cache_read_input_tokens")), number(usage.get("cache_creation_input_tokens"))
    tokens = {"prompt": number(usage.get("input_tokens")) + written + cached,
              "cached": cached, "written": written, "answer": number(usage.get("output_tokens"))}
    calls = [c for c in usage.get("iterations") or [] if isinstance(c, dict)]
    last = calls[-1] if calls else usage
    size = sum(number(last.get(k)) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return {"answer": json.dumps(answer, ensure_ascii=False) if isinstance(answer, dict) else str(result.get("result") or ""),
            "tokens": tokens, "limits": limits, "session": result.get("session_id"), "size": size}


# ---------------------------------------------------------------- live sessions
#
# A conversation of the agent panel (a tab) keeps its Claude Code running between its messages, through the Claude
# Agent SDK: a message is answered at once, without starting the program and reading its session anew, and the
# studio's tools are Claude's own tools (an MCP server inside the studio), which it calls as it goes in one turn.
# A session no one wrote to for IDLE is closed, and so is the oldest past LIVE; its next message opens it again.

IDLE = 15 * 60   # seconds
LIVE = 6         # live sessions at once: each is a program of its own, holding a few hundred MB of memory
TOOLS_SERVER = "studio"


class _Live:
    """One conversation's running Claude Code: its client, the session it holds and what it was opened with."""

    def __init__(self, signature):
        self.signature, self.client, self.session = signature, None, None
        self.lock = asyncio.Lock()
        self.used = time.monotonic()
        self.tools, self.called, self.context, self.result_chars = {}, [], None, 8000
        self.record, self.compacted = None, []   # record(kind, text, data): what happens in it, for its story (sessions.py)


live = {}   # a conversation's key (thread["key"]) -> its _Live


def live_ok(s):
    """Whether a conversation with the service `s` can go on in a live session: Claude, with the SDK installed."""
    return sdk is not None and bool(s and s.get("cli"))


def _handlers(entry, names):
    """{name: async function(args) -> MCP result}: the tools Claude Code calls. Each runs the tool of the message being
    answered (entry.tools), in that message's request (its context: whose rows the database shows)."""
    def one(name):
        async def run(args):
            entry.called.append(name)
            tool = entry.tools.get(name)
            if tool is None:
                text = "{} is not on offer for this message.".format(name)
            else:
                try:
                    text = str(await asyncio.get_running_loop().create_task(tool(dict(args or {})), context=entry.context))
                except (KeyError, ValueError, TypeError):
                    text = "That call could not be run. Check its fields."
            chars = entry.result_chars(name) if callable(entry.result_chars) else entry.result_chars
            return {"content": [{"type": "text", "text": text[:chars]}]}
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


async def _open(s, settings):
    """A connected client for one conversation. settings: {"model", "system", "schema", "tools": {name: (about, input
    schema)}, "handlers", "resume", "max_turns", "web", "effort"}. With "web", Claude Code's web search (WEB_TOOLS) is on
    too; "effort", how hard it thinks (EFFORT), or empty for the model's default."""
    tools = [sdk.tool(name, about, shape)(settings["handlers"][name]) for name, (about, shape) in settings["tools"].items()]
    Path(s["home"]).mkdir(parents=True, exist_ok=True)
    web = list(WEB_TOOLS) if settings.get("web") else []
    options = sdk.ClaudeAgentOptions(
        cli_path=s["cli"], model=settings["model"], system_prompt={"type": "file", "path": prompt_file(settings["system"])}, tools=web,
        allowed_tools=["mcp__{}__{}".format(TOOLS_SERVER, name) for name in settings["tools"]] + web,
        mcp_servers={TOOLS_SERVER: sdk.create_sdk_mcp_server(TOOLS_SERVER, tools=tools)} if tools else {},
        strict_mcp_config=True, setting_sources=[], cwd=s["home"], resume=settings["resume"] or None,
        max_turns=settings["max_turns"], output_format={"type": "json_schema", "schema": settings["schema"]},
        settings=session_settings(s), env=dict(NO_MEMORY), effort=settings.get("effort") or None)
    client = sdk.ClaudeSDKClient(options)
    await asyncio.wait_for(client.connect(), 60)
    return client


async def _close(key):
    entry = live.pop(key, None)
    if entry is not None and entry.client is not None:
        try:
            await asyncio.wait_for(entry.client.disconnect(), 15)
        except Exception as error:   # it is let go either way
            print("A Claude session did not close cleanly: {}".format(error))


async def close_all(starting=""):
    """Close every live session (the studio stops), or the ones whose key starts so (a conversation deleted)."""
    for key in [k for k in live if k.startswith(starting)]:
        await _close(key)


async def _tidy():
    """Close the sessions idle for IDLE, then the ones used longest ago past LIVE (never one that is answering)."""
    now = time.monotonic()
    for key, entry in list(live.items()):
        if now - entry.used > IDLE and not entry.lock.locked():
            await _close(key)
    while len(live) > LIVE:
        idle = [(entry.used, key) for key, entry in live.items() if not entry.lock.locked()]
        if not idle:
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


def _told(entry, message):
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


async def _turn(entry, text):
    """One message to the live session; returns (its result as a result event, the last rate limit event)."""
    result, limits = None, None
    async with gate:
        await entry.client.query(text)
        async for message in entry.client.receive_response():
            _told(entry, message)
            if isinstance(message, sdk.RateLimitEvent):
                info = message.rate_limit_info
                limits = dict(info.raw or {"status": info.status, "resetsAt": info.resets_at})
            elif isinstance(message, sdk.ResultMessage):
                result = {"type": "result", "subtype": message.subtype, "is_error": message.is_error, "session_id": message.session_id,
                          "result": message.result or " ".join(message.errors or []), "structured_output": message.structured_output,
                          "usage": message.usage or {}, "api_error_status": message.api_error_status}
    return result, limits


async def converse(s, model, system, text, schema, thread, tools, about, finish_now, max_turns, result_chars=8000, web=False):
    """One message of a conversation in its live session. Returns (the answer as JSON text, {"prompt", "cached",
    "answer"} tokens, the usage limits or None, the names of the tools it called in order). Raises Busy, Lost or Failed.
    thread: the conversation's {"key", "id", ...}; its id (the session) and size are kept up to date here.
    tools: {name: async function(call) -> str}, the studio's tools for this message; about: {name: (what it does,
    its input schema)}, every tool the session offers. A turn that runs out of max_turns is asked finish_now.
    result_chars: how much of a tool's result Claude is given, in characters: a number, or a function of the tool's name
    (agent.result_chars). web: Claude Code's web search is on in the session (WEB_TOOLS)."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
    key = thread.get("key") or thread.get("id") or "default"
    effort = EFFORT.get()
    # A session opened with another effort is opened again (going on with the same conversation): it is set as it starts.
    signature = json.dumps([model, system, schema, sorted(about), max_turns, bool(web), effort], sort_keys=True)
    if text.lstrip().startswith("/"):   # a message is never taken for a command of Claude Code's (/compact): command() runs those
        text = "Message:\n" + text
    await _tidy()
    entry = live.get(key)
    if entry is not None and (entry.signature != signature or entry.session != thread.get("id")):
        await _close(key)   # opened for another prompt, shape or session: opened again, going on with the session
        entry = None
    if entry is None:
        entry = live[key] = _Live(signature)
    async with entry.lock:
        entry.tools, entry.called, entry.context, entry.result_chars = tools, [], contextvars.copy_context(), result_chars
        entry.record, entry.compacted = thread.get("record"), []
        try:
            if entry.client is None:
                entry.client = await _open(s, {"model": model, "system": system, "schema": schema, "tools": about,
                                               "handlers": _handlers(entry, about), "resume": thread.get("id"), "max_turns": max_turns,
                                               "web": web, "effort": effort})
            result, limits = await _turn(entry, text)
            tokens = None
            if (result or {}).get("subtype") == "error_max_turns":   # still working when its turns ran out: it answers now
                tokens = judged(dict(result, subtype="success", is_error=False), limits)["tokens"]
                result, limits = await _turn(entry, finish_now)
            got = judged(result, limits)
        except asyncio.CancelledError:   # the user stopped it: the program goes, the session stays for the next message
            await asyncio.shield(_close(key))
            raise
        except (Busy, Failed):
            await _close(key)
            raise
        except Exception as error:   # the SDK's own errors: the program could not be started, or stopped
            await _close(key)
            said = str(error)
            if "no conversation found" in said.lower():
                raise Lost("The conversation's Claude session is gone.")
            raise Failed("Claude Code stopped: {}".format(" ".join(said.split())[:300]))
        finally:
            entry.used = time.monotonic()
        entry.session = got["session"] or thread.get("id")
    thread.update(id=entry.session, size=got["size"], compacted=len(entry.compacted) + (thread.get("compacted") or 0))
    total = {k: got["tokens"][k] + (tokens or {}).get(k, 0) for k in got["tokens"]}
    return got["answer"], total, got["limits"], list(entry.called)


async def command(s, thread, text):
    """A command of Claude Code's (/compact, /rename ...) in a conversation's session: in its live program when it has
    one, else in a run of its own that goes on with the session. Returns {"compacted": the compact_metadata of a
    compaction (pre_tokens, post_tokens) or None, "session": its id}."""
    global gate
    gate = gate or asyncio.Semaphore(PARALLEL)
    key = thread.get("key") or thread.get("id") or "default"
    entry = live.get(key)
    if entry is not None and entry.client is not None and entry.session == thread.get("id"):
        async with entry.lock:
            entry.record, entry.compacted = thread.get("record"), []
            try:
                await _turn(entry, text)
            except Exception as error:
                await _close(key)
                raise Failed("Claude Code could not do {}: {}".format(text.split()[0], " ".join(str(error).split())[:300]))
            finally:
                entry.used = time.monotonic()
            done = entry.compacted[-1] if entry.compacted else None
        return {"compacted": done, "session": entry.session}
    if not thread.get("id"):
        raise Failed("This conversation has no Claude session yet.")
    args = [s["cli"], "-p", text, "--resume", thread["id"], "--output-format", "stream-json", "--verbose", "--tools", "",
            "--strict-mcp-config", "--setting-sources", "", "--settings", session_settings(s)]
    Path(s["home"]).mkdir(parents=True, exist_ok=True)
    async with gate:
        run = await asyncio.to_thread(_run, args, "", s["home"], s["timeout"])
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
                said = " ".join(str(event.get("result") or "").split())
                if "no conversation found" in said.lower():
                    raise Lost("The conversation's Claude session is gone.")
                raise Failed("Claude Code could not do {}: {}".format(text.split()[0], said[:300]))
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
    """Remove the file Claude Code keeps a thread's session in (the conversation was deleted). It files a session under
    its folder's path, every character but letters and digits made a dash, in its own home (~/.claude)."""
    if not s or not re.fullmatch(r"[0-9A-Za-z-]{8,64}", str(session or "")):
        return
    kept = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects" / re.sub(
        r"[^A-Za-z0-9]", "-", str(Path(s["home"]).resolve()))
    (kept / (session + ".jsonl")).unlink(missing_ok=True)
    shutil.rmtree(kept / session, ignore_errors=True)


def resets(limits):
    """", until 14:30" from Claude Code's rate limit event, or "" when it did not say."""
    when = (limits or {}).get("resetsAt")
    return ", until {}".format(time.strftime("%H:%M", time.localtime(when))) if isinstance(when, (int, float)) else ""
