"""What the studio lets through to the `claude` it runs on this PC: its arguments, its environment and, line by line, its
stdin. Ported from the SceneCloude bridge's policy.py (its docs/protocol.md, section 3), which checked the same on LUFI
when the studio reached Claude Code through it; now the studio runs `claude` itself (claude.LocalProgram) and checks it
here, in-process, for both local connections: Claude on this PC and an Anthropic API key.

Why, though the studio builds every call itself:

- Claude Code is a whole agent on this PC. The studio wants it to answer only: none of its own tools, settings, hooks,
  MCP servers or plugins (--tools "", --setting-sources "", --strict-mcp-config). A change to the studio that dropped
  one of those would give Claude this PC's full tool set: the flags are checked on every start, so that change fails
  at once, naming the flag, instead of working quietly.
- What a user types reaches Claude Code as a message. Without "client_composed", Claude Code reads "@C:\\path" in a
  message as a file to attach, from this PC's disk, and runs "/logout" or any other slash command. Every user message
  is marked client_composed, so it is delivered as written; only the studio's own /compact and /rename go as commands.
- The SDK sends control requests on stdin; the few the studio uses pass, and any other (set_permission_mode,
  mcp_reconnect, an initialize carrying agents ...) is answered here with an error, and the session goes on.

What is not listed is refused, with an error that names it (Refused). The bridge's rules are kept as they were, with
two changes, since the run is now here: --system-prompt-file is allowed, to a file in the run's own temporary folder
(parse's prompt_folder; the bridge took the prompt's text instead and wrote its own file), and the SDK's "--flag=value"
form is taken as two."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

WEB_TOOLS = {"WebSearch"}   # Claude Code's web search runs at Anthropic; WebFetch would run on this PC, so it is not here
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
COMMANDS = re.compile(r"/(compact|rename [^\r\n]{1,200})")   # the slash commands the studio sends, whole
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-\[\]]{0,99}")
SESSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z-]{7,63}")
NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
TOOL = re.compile(r"[A-Za-z0-9_-]{1,128}")

BOOL, VALUE, MANY = "bool", "value", "many"
FLAGS = {
    "-p": BOOL, "--print": BOOL, "--verbose": BOOL, "--strict-mcp-config": BOOL, "--disable-slash-commands": BOOL,
    "--no-session-persistence": BOOL,
    "--input-format": VALUE, "--output-format": VALUE, "--model": VALUE, "--effort": VALUE, "--max-turns": VALUE,
    "--settings": VALUE, "--json-schema": VALUE, "--resume": VALUE, "--setting-sources": VALUE,
    "--system-prompt-file": VALUE,   # only to a file in the run's own folder (parse)
    "--tools": MANY, "--allowedTools": MANY, "--allowed-tools": MANY, "--mcp-config": MANY,
}
SAME = {"--print": "-p", "--allowed-tools": "--allowedTools"}
NAMED = {
    "--dangerously-skip-permissions": "it would let Claude act on this PC without asking",
    "--allow-dangerously-skip-permissions": "it would let Claude act on this PC without asking",
    "--add-dir": "it would give Claude a folder on this PC",
    "--permission-mode": "permissions are fixed by the studio",
    "--plugin-dir": "plugins run code on this PC",
    "--system-prompt": "the system prompt goes as a file (--system-prompt-file): a long one passes Windows' command line limit",
    "--append-system-prompt": "the system prompt goes whole, as a file (--system-prompt-file)",
}
ENV = {
    "CLAUDE_CODE_ENTRYPOINT": re.compile(r"sdk-py|sdk-ts|cli"),
    "CLAUDE_AGENT_SDK_VERSION": re.compile(r"[0-9][0-9.]{0,30}"),
    "CLAUDE_CODE_SDK_READS_SESSION_STATE": re.compile(r"[01]"),
    "CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS": re.compile(r"[01]"),
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": re.compile(r"1"),
}
SETTINGS = {"autoMemoryEnabled": bool, "autoCompactWindow": int}
CONTROL = {"initialize", "interrupt", "mcp_status", "get_context_usage", "set_model", "stop_task"}
MAX_LINE = 64 * 1024 * 1024   # one stdin line (a message with pictures in base64)


class Refused(Exception):
    """The call asks for something the studio does not let through to Claude Code."""


@dataclass
class Plan:
    """A checked call: the arguments to give claude (as they came), and what the run needs of them."""
    args: list
    version: bool = False          # claude -v / --version
    stream_input: bool = False     # stdin is stream-json lines (else it must be empty)
    model: str = ""
    flags: list = field(default_factory=list)   # the flag names, for a log (never their values)


def _json(flag, text):
    if not text.lstrip().startswith("{"):
        raise Refused("{} must be inline JSON, not a file path".format(flag))
    try:
        found = json.loads(text)
    except ValueError:
        raise Refused("{} is not valid JSON".format(flag))
    if not isinstance(found, dict):
        raise Refused("{} must be a JSON object".format(flag))
    return found


def _names(values):
    return [n for v in values for n in re.split(r"[,\s]+", v) if n]


def _sdk_servers(values):
    if len(values) != 1:
        raise Refused("--mcp-config takes one inline JSON value")
    found = _json("--mcp-config", values[0])
    servers = found.get("mcpServers")
    if set(found) != {"mcpServers"} or not isinstance(servers, dict):
        raise Refused('--mcp-config must be {"mcpServers": {...}} and nothing else')
    for name, server in servers.items():
        if not NAME.fullmatch(str(name)) or not isinstance(server, dict) or server.get("type") != "sdk" \
                or set(server) - {"type", "name"} or server.get("name", name) != name:
            raise Refused('--mcp-config may only declare in-process servers ({{"type": "sdk", "name": ...}}): {!r} is not one'.format(name))
    return set(servers)


def split_flags(args):
    """The arguments with each "--flag=value" made two, "--flag" and "value": the SDK's own form for --resume and
    --setting-sources. Safe, since a value that starts with "-" is refused."""
    found = []
    for arg in args:
        if arg.startswith("--") and "=" in arg:
            found += arg.split("=", 1)
        else:
            found.append(arg)
    return found


def _inside(path, folder):
    try:
        return Path(path).resolve().is_relative_to(Path(folder).resolve())
    except (OSError, ValueError):
        return False


def parse(args, prompt_folder):
    """Check claude's arguments. Returns a Plan, or raises Refused.
    prompt_folder: the run's own temporary folder (LocalProgram): its --system-prompt-file must be a file in it."""
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise Refused("args must be a list of strings")
    if args in (["-v"], ["--version"]):
        return Plan(list(args), version=True, flags=list(args))
    args = split_flags(args)
    seen, prompt, i = {}, None, 0
    while i < len(args):
        token = args[i]
        if not token.startswith("-"):
            if i > 0 and SAME.get(args[i - 1], args[i - 1]) == "-p" and prompt is None:
                prompt = token
                i += 1
                continue
            if i == 0:
                raise Refused("subcommands are not allowed ({!r})".format(token))
            raise Refused("unexpected argument {!r}".format(token[:40]))
        if token in NAMED:
            raise Refused("{} is refused: {}".format(token, NAMED[token]))
        kind = FLAGS.get(token)
        if kind is None:
            raise Refused("unknown flag {} is refused".format(token[:60]))
        name = SAME.get(token, token)
        if name in seen:
            raise Refused("{} is given twice".format(name))
        i += 1
        if kind == BOOL:
            seen[name] = True
        elif kind == VALUE:
            if i >= len(args) or args[i].startswith("-"):
                raise Refused("{} needs a value".format(name))
            seen[name], i = args[i], i + 1
        else:   # variadic, as Claude Code's parser takes it: every token up to the next that starts with "-"
            values = []
            while i < len(args) and not args[i].startswith("-"):
                values.append(args[i])
                i += 1
            if not values:
                raise Refused("{} needs a value".format(name))
            seen[name] = values
    if "--system-prompt-file" in seen and not _inside(seen["--system-prompt-file"], prompt_folder):
        raise Refused("--system-prompt-file must be a file in this run's own temporary folder")
    return _check(args, seen, prompt)


def _check(args, seen, prompt):
    for required in ("--tools", "--setting-sources", "--strict-mcp-config"):
        if required not in seen:
            raise Refused("{} is required, so none of this PC's own tools, settings or MCP servers are used".format(required))
    if seen["--setting-sources"] != "":
        raise Refused("--setting-sources must be empty")
    if set(_names(seen["--tools"])) - WEB_TOOLS:
        raise Refused("--tools may be empty or {} only".format(", ".join(sorted(WEB_TOOLS))))
    servers = _sdk_servers(seen["--mcp-config"]) if "--mcp-config" in seen else set()
    for name in _names(seen.get("--allowedTools", [])):
        if name in WEB_TOOLS:
            continue
        if not any(name.startswith("mcp__{}__".format(s)) and TOOL.fullmatch(name[len(s) + 7:]) for s in servers):
            raise Refused("--allowedTools may hold {} or the studio's own in-process tools (mcp__<sdk server>__<tool>), not {!r}".format(
                ", ".join(sorted(WEB_TOOLS)), name[:80]))
    checks = {
        "--input-format": lambda v: v in ("stream-json", "text"),
        "--output-format": lambda v: v in ("stream-json", "json", "text"),
        "--model": lambda v: bool(MODEL.fullmatch(v)),
        "--effort": lambda v: v in EFFORTS,
        "--max-turns": lambda v: v.isdigit() and 1 <= int(v) <= 500,
        "--resume": lambda v: bool(SESSION.fullmatch(v)),
    }
    for name, ok in checks.items():
        if name in seen and not ok(seen[name]):
            raise Refused("{} has a value the studio does not take".format(name))
    if "--settings" in seen:
        settings = _json("--settings", seen["--settings"])
        for key, value in settings.items():
            kind = SETTINGS.get(key)
            if kind is None or type(value) is not kind:
                raise Refused("--settings may only hold {}: {!r} is refused".format(", ".join(SETTINGS), key[:60]))
    if "--json-schema" in seen:
        _json("--json-schema", seen["--json-schema"])
    if prompt is not None and not COMMANDS.fullmatch(prompt):
        raise Refused("a prompt on the command line may only be /compact or /rename <title>: send messages on stdin")
    stream = seen.get("--input-format") == "stream-json"
    return Plan(list(args), stream_input=stream, model=seen.get("--model", ""), flags=[a for a in args if a.startswith("-")])


def environment(env):
    """The variables the studio may set for claude, beyond its own environment: the SDK's and the "no memory" one."""
    if env is None:
        return {}
    if not isinstance(env, dict):
        raise Refused("env must be an object")
    for key, value in env.items():
        pattern = ENV.get(key)
        if pattern is None:
            raise Refused("the environment variable {} is refused".format(str(key)[:60]))
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise Refused("{} has a value the studio does not take".format(key))
    return dict(env)


def _content_ok(content):
    if isinstance(content, str):
        return True
    if not isinstance(content, list):
        return False
    for block in content:
        if not isinstance(block, dict):
            return False
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            continue
        source = block.get("source")
        if block.get("type") == "image" and isinstance(source, dict) and source.get("type") == "base64" \
                and str(source.get("media_type", "")).startswith("image/") and isinstance(source.get("data"), str):
            continue
        return False
    return True


def _command_of(content):
    """The slash command a message is, whole (/compact, /rename T), or None."""
    if isinstance(content, list) and len(content) == 1 and content[0].get("type") == "text":
        content = content[0]["text"]
    return content.strip() if isinstance(content, str) and COMMANDS.fullmatch(content.strip()) else None


def stdin_line(line):
    """One line the studio sends to claude's stdin (text, with its newline). Returns (the line to pass on, or None; a
    line to answer with on claude's stdout, or None). Raises Refused for a line that stops the run."""
    if not line.strip():
        return line, None
    try:
        message = json.loads(line)
    except ValueError:
        raise Refused("stdin carries stream-json: one JSON object a line")
    if not isinstance(message, dict):
        raise Refused("stdin carries stream-json: one JSON object a line")
    kind = message.get("type")
    if kind == "control_response":
        return line, None
    if kind == "user":
        body = message.get("message")
        if not isinstance(body, dict) or not _content_ok(body.get("content")):
            raise Refused("a user message may hold text and base64 images only")
        if _command_of(body.get("content")):
            message.pop("client_composed", None)   # /compact, /rename: run as Claude Code's command
        else:
            message["client_composed"] = True     # as written: no @path reading on this PC, no slash commands
        return json.dumps(message, ensure_ascii=False) + "\n", None
    if kind == "control_request":
        request = message.get("request") if isinstance(message.get("request"), dict) else {}
        subtype = request.get("subtype")
        why = None
        if subtype not in CONTROL:
            why = "{} is not allowed".format(str(subtype)[:60])
        elif subtype == "initialize" and set(request) - {"subtype", "hooks"}:
            why = "initialize may carry hooks only (no agents, skills or other options)"
        elif subtype == "set_model" and request.get("model") is not None and not MODEL.fullmatch(str(request.get("model"))):
            why = "set_model has a model name the studio does not take"
        if why is None:
            return line, None
        answer = {"type": "control_response", "response": {"subtype": "error", "request_id": message.get("request_id"),
                                                           "error": "Refused by the studio: " + why}}
        return None, json.dumps(answer) + "\n"
    raise Refused("stdin line of type {!r} is refused".format(str(kind)[:40]))
