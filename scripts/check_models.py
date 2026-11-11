"""Check the agent's models: Claude, through Claude Code by the Claude connection the studio uses (the only models the
agent uses): the one picked in the admin console, as the studio reads it from its database.

Run it from the repo root with the project's Python:

    .venv\\Scripts\\python.exe scripts\\check_models.py        (Windows)
    .venv/bin/python scripts/check_models.py                   (macOS, Linux)

It checks the connection (as the console's Test does), then asks each Claude model named in claude_models for a
one-line JSON answer. It never prints a key.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from scene import claude, claude_connection  # noqa: E402
from scene.agent import Agent, AgentError  # noqa: E402
from scene.config import load_settings  # noqa: E402
from scene.db import as_everyone, open_database  # noqa: E402


async def main():
    s = load_settings()
    db = open_database(s)
    with as_everyone():
        claude_connection.apply(db, s)
    found = await claude_connection.status(run_claude=True)
    print("Claude connection:", claude_connection.MODES[found["mode"]], "works" if found["online"] else "FAILS: " + found["detail"])
    print("Claude Code:", found["claude_version"] or "(no version)")
    service = claude.service(s.claude_models, s.claude_timeout, s.claude_fast_model, s.path("storage_dir") / "claude-home",
                             s.claude_context)
    if service is None or not found["online"]:
        return
    brain = Agent(s.agent_model, [service])
    question = [{"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Reply with the JSON object {\"ok\": true}."}]
    print("Models offered:", ", ".join(await brain.models()))
    for name in await brain.models():
        try:
            answer = await brain.chat(question, {"type": "object", "properties": {"ok": {"type": "boolean"}}}, model=name)
            print("  {:20} works, answered {}".format(name, {k: v for k, v in answer.items() if not k.startswith("_")}))
        except AgentError as e:
            print("  {:20} FAILED: {}".format(name, e))
    print("Default model:", s.agent_model or "(the first one there is)", "· fast model:", s.claude_fast_model or "(the one in use)")
    print("Usage limits as Claude Code last reported them:", brain.claude_limits)
    await claude.close_all()

asyncio.run(main())
