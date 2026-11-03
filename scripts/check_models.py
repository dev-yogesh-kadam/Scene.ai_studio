"""Check the agent's models: Claude, through Claude Code on this machine (the only models the agent uses).

Run it from the repo root with the project's Python:

    .venv\\Scripts\\python.exe scripts\\check_models.py        (Windows)
    .venv/bin/python scripts/check_models.py                   (macOS, Linux)

It asks each Claude model named in claude_models for a one-line JSON answer. Claude Code must be installed and
signed in with the Claude account whose usage the studio spends.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from scene import claude  # noqa: E402
from scene.agent import Agent, AgentError  # noqa: E402
from scene.config import load_settings  # noqa: E402


async def main():
    s = load_settings()
    found = claude.find(s.claude_path)
    print("Claude Code:", found or "NOT FOUND (install it and sign in, or set claude_path in config.json)")
    service = claude.service(s.claude_models, s.claude_path, s.claude_timeout, s.claude_fast_model, str(ROOT), s.claude_context)
    if service is None:
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
