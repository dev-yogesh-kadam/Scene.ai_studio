"""A fake `claude` for the tests of the Claude connection (test_claude_connection.py): run as Claude Code would be, by
the studio itself (the "api_key" connection) or by the fake LUFI bridge, it speaks enough of Claude Code's stream-json
to be one, and writes down how it was started.

- `-v` prints a version.
- Each message it is given (stream-json on stdin) is answered with a result whose structured output is {"reply": ...}:
  "seen <n> pictures" when it carried pictures, "compacted" for /compact (after a compact_boundary event).
- A message saying "call <tool>" first calls that tool of the run's SDK MCP server (the studio's own tools), as the
  real one does: an mcp_message control request (the MCP handshake, then tools/call), and the reply is the tool's
  answer.
- The SDK's initialize control request is answered.
- FAKE_CLAUDE_SAY=signed_out: it says it is not signed in and exits 1.
- FAKE_CLAUDE_LOG: a file to which a JSON line is added for each run: its arguments, folder, API key, the "no memory"
  variable, its system prompt and the messages it was sent.
"""

import json
import os
import sys

args = sys.argv[1:]
log = {"args": args, "cwd": os.getcwd(), "api_key": os.environ.get("ANTHROPIC_API_KEY"),
       "memory": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"), "system": None, "messages": []}


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
    say({"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": reply,
         "duration_ms": 1, "duration_api_ms": 1, "num_turns": 1,
         "structured_output": {"reply": reply}, "usage": {"input_tokens": 10, "output_tokens": 5}})


while True:
    got = next_line()
    if got == "end":
        break
    if not isinstance(got, dict):
        continue
    if got.get("type") == "control_request" and got["request"].get("subtype") == "initialize":
        say({"type": "control_response", "response": {"subtype": "success", "request_id": got["request_id"], "response": {}}})
    elif got.get("type") == "user":
        log["messages"].append(got["message"])
        answer(got["message"])
keep()
