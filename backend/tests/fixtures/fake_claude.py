"""A fake `claude` for the tests of the Claude connection (test_claude_connection.py): run as Claude Code would be, by
the studio itself (Claude on this PC, or the "api_key" connection), it speaks enough of Claude Code's stream-json
to be one, and writes down how it was started.

- `auth login` prints a link and reads a code ("good-code#s1" signs in), `auth logout` signs out: both kept in
  FAKE_CLAUDE_AUTH_FILE, which `auth status` reads first.
- `-v` prints a version; `auth status --json` says it is signed in (as Claude Code does: loggedIn, email,
  subscriptionType), or signed out with FAKE_CLAUDE_AUTH=signed_out.
- Each message it is given (stream-json on stdin) is answered with a result whose structured output is {"reply": ...}:
  "seen <n> pictures" when it carried pictures, "compacted" for /compact (after a compact_boundary event).
- A message saying "call <tool>" first calls that tool of the run's SDK MCP server (the studio's own tools), as the
  real one does: an mcp_message control request (the MCP handshake, then tools/call), and the reply is the tool's
  answer.
- The SDK's initialize control request is answered.
- FAKE_CLAUDE_SAY=signed_out: it says it is not signed in and exits 1.
- FAKE_CLAUDE_LIMITS: a rate_limit_info (JSON) it reports before each result, as on a Claude subscription.
- FAKE_CLAUDE_LOG: a file to which a JSON line is added for each run: its arguments, folder, API key, the "no memory"
  variable, its system prompt, the messages it was sent and each one's client_composed, and the control requests
  it was sent.
"""

import json
import os
import sys

args = sys.argv[1:]
log = {"args": args, "cwd": os.getcwd(), "api_key": os.environ.get("ANTHROPIC_API_KEY"),
       "auth_token": os.environ.get("ANTHROPIC_AUTH_TOKEN"),
       "memory": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"), "system": None, "messages": [], "composed": [],
       "controls": []}


def value(flag):
    return args[args.index(flag) + 1] if flag in args else None


def say(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def keep():
    if os.environ.get("FAKE_CLAUDE_LOG"):
        with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as out:
            out.write(json.dumps(log) + "\n")


if "-v" in args or "--version" in args:
    print("2.1.310 (Claude Code)")
    sys.exit(0)
def auth_file(write=None):
    """FAKE_CLAUDE_AUTH_FILE: where `auth login` and `auth logout` keep the sign-in ("signed_in" / "signed_out")."""
    path = os.environ.get("FAKE_CLAUDE_AUTH_FILE")
    if not path:
        return ""
    if write is not None:
        with open(path, "w", encoding="utf-8") as out:
            out.write(write)
        return write
    return open(path, encoding="utf-8").read().strip() if os.path.exists(path) else ""


if args[:2] == ["auth", "login"]:   # as Claude Code does it with no terminal: a link, then a code on stdin
    sys.stdout.write("Opening browser to sign in…\nIf the browser didn't open, visit: https://claude.com/cai/oauth/"
                     "authorize?code=true&client_id=fake&state=s1\nPaste code here if prompted > ")
    sys.stdout.flush()
    code = sys.stdin.readline().strip()
    if code == "good-code#s1":
        auth_file("signed_in")
        print("\nLogin successful.")
        sys.exit(0)
    print("\nOAuth error: Request failed with status code 400")
    sys.exit(1)
if args[:2] == ["auth", "logout"]:
    auth_file("signed_out")
    print("Successfully logged out from your Anthropic account.")
    sys.exit(0)
if args[:2] == ["auth", "status"]:
    if auth_file() == "signed_out" or (os.environ.get("FAKE_CLAUDE_AUTH") == "signed_out" and auth_file() != "signed_in"):
        print(json.dumps({"loggedIn": False, "authMethod": "none"}))
    elif os.environ.get("ANTHROPIC_API_KEY"):   # as Claude Code says it: the key, not the account it is signed in with
        print(json.dumps({"loggedIn": True, "authMethod": "api_key", "apiKeySource": "ANTHROPIC_API_KEY"}))
    else:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "owner@example.com", "orgName": "Owner",
                          "subscriptionType": "pro"}))
    sys.exit(0)
if value("--system-prompt-file"):
    with open(value("--system-prompt-file"), encoding="utf-8") as prompt:
        log["system"] = prompt.read()
if os.environ.get("FAKE_CLAUDE_SAY") == "signed_out":
    keep()
    sys.stderr.write("Invalid API key · Please run /login\n")
    sys.exit(1)

servers = json.loads(value("--mcp-config") or "{}").get("mcpServers", {})
sdk_server = next((name for name, s in servers.items() if s.get("type") == "sdk"), None)
session = value("--resume") or "fake-session-1"
answers = {}   # request id -> the SDK's control response
counter = [0]
handshaken = []


def next_line():
    line = sys.stdin.readline()
    return json.loads(line) if line.strip() else ("end" if not line else None)


def ask_sdk(message):
    """An MCP message to the SDK's server, through a control request; the answer's mcp_response."""
    counter[0] += 1
    request_id = "fake_{}".format(counter[0])
    say({"type": "control_request", "request_id": request_id,
         "request": {"subtype": "mcp_message", "server_name": sdk_server, "message": message}})
    while request_id not in answers:
        got = next_line()
        if got == "end":
            raise SystemExit(1)
        if isinstance(got, dict) and got.get("type") == "control_response":
            answers[got["response"]["request_id"]] = got["response"]
    return answers[request_id]["response"]["mcp_response"]


def call_tool(name, arguments):
    if not handshaken:
        ask_sdk({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake-claude", "version": "1"}}})
        ask_sdk({"jsonrpc": "2.0", "method": "notifications/initialized"})
        handshaken.append(True)
    got = ask_sdk({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    return got["result"]["content"][0]["text"]


def answer(message):
    content = message.get("content")
    say({"type": "system", "subtype": "init", "session_id": session})
    if isinstance(content, str) and content.startswith("/compact"):
        say({"type": "system", "subtype": "compact_boundary",
             "compact_metadata": {"trigger": "manual", "pre_tokens": 800000, "post_tokens": 9000}})
        reply = "compacted"
    else:
        blocks = content if isinstance(content, list) else [{"type": "text", "text": str(content)}]
        text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        pictures = sum(1 for b in blocks if b.get("type") == "image")
        reply = "seen {} pictures".format(pictures) if pictures else "hello"
        if "call " in text and sdk_server:
            reply = "the tool said: " + call_tool(text.split("call ", 1)[1].split()[0], {"query": "Mira"})
    if os.environ.get("FAKE_CLAUDE_LIMITS"):   # a plan's limits, as a subscription's Claude Code reports them
        say({"type": "rate_limit_event", "uuid": "fake-limits", "session_id": session,
             "rate_limit_info": json.loads(os.environ["FAKE_CLAUDE_LIMITS"])})
    say({"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": reply,
         "duration_ms": 1, "duration_api_ms": 1, "num_turns": 1,
         "structured_output": {"reply": reply}, "usage": {"input_tokens": 10, "output_tokens": 5}})


while True:
    got = next_line()
    if got == "end":
        break
    if not isinstance(got, dict):
        continue
    if got.get("type") == "control_request":
        log["controls"].append(got["request"].get("subtype"))
    if got.get("type") == "control_request" and got["request"].get("subtype") == "initialize":
        say({"type": "control_response", "response": {"subtype": "success", "request_id": got["request_id"], "response": {}}})
    elif got.get("type") == "user":
        log["messages"].append(got["message"])
        log["composed"].append(got.get("client_composed"))
        answer(got["message"])
keep()
