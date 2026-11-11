"""Calibrate the creative judge against a person (docs/evals.md, docs/creative-rubric.md).

    python -m evals.calibrate                  every creative case: its recorded plan, the judge's marks, then yours
    python -m evals.calibrate --case en-creative-open-cafe-ad --max 3
    python -m evals.calibrate --live --max 3   the plans Claude makes now, not the recorded ones (uses the account's usage)

For each case with the tag "creative" the plan is made as `evals.run` makes it (replayed from the case's recorded answer,
or by Claude with --live), the judge (an Opus, evals/creative.py) marks it against the rubric, and you are shown the
plan and the judge's marks and asked for your own, 1 to 5 each (Enter skips a mark, q stops). Each case's marks are
added to evals/calibration.json, and the report says, per mark, how far the judge is from you over every case in it:
the mean distance and the mean lean (judge minus you: above 0 the judge is kinder). The judge always needs Claude Code on
this machine; nothing is charged to a user."""

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

from evals import creative, run

CALIBRATION = run.HERE / "calibration.json"


def judge_brain():
    """An Agent with the `claude` on this machine (an Opus offered), for the judge: signed in, or with
    SCENE_ANTHROPIC_API_KEY set."""
    import os
    from scene import claude
    from scene.agent import Agent
    from scene.config import Settings
    settings = Settings()
    claude.CONNECTION = dict(claude.CONNECTION, api_key=os.environ.get("SCENE_ANTHROPIC_API_KEY", ""))
    if not claude.find():
        raise SystemExit("The judge needs Claude Code on this machine (`claude` on PATH), signed in or with SCENE_ANTHROPIC_API_KEY.")
    return Agent("claude/opus", services=[claude.service("sonnet, opus, haiku", settings.claude_timeout, "haiku")])


def kept(path=CALIBRATION):
    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return found if isinstance(found, list) else []


def distance(entries):
    """Per mark: {"n", "mean_distance", "mean_lean"} over the entries where both the judge and the person gave it."""
    found = {}
    for mark in creative.MARKS:
        pairs = [(e["judge"][mark], e["human"][mark]) for e in entries
                 if isinstance((e.get("judge") or {}).get(mark), int) and isinstance((e.get("human") or {}).get(mark), int)]
        found[mark] = {"n": len(pairs), "mean_distance": round(sum(abs(j - h) for j, h in pairs) / len(pairs), 2) if pairs else None,
                       "mean_lean": round(sum(j - h for j, h in pairs) / len(pairs), 2) if pairs else None}
    return found


def asked_marks(judged, ask, out):
    """The person's marks, asked one by one: {mark: 1..5}; Enter skips one. None when they typed q (stop)."""
    mine = {}
    for mark in creative.MARKS:
        while True:
            said = str(ask("  your {} (1-5, the judge gave {}; Enter skips, q stops): ".format(mark, judged.get(mark))) or "").strip().lower()
            if said == "q":
                return None
            if not said:
                break
            if said in ("1", "2", "3", "4", "5"):
                mine[mark] = int(said)
                break
            out("  a whole number from 1 to 5, please")
    return mine


def report(entries, out=print):
    out("\nThe judge against you, over {} case{}:".format(len(entries), "" if len(entries) == 1 else "s"))
    for mark, found in distance(entries).items():
        out("  {:<15} {}".format(mark, "no marks yet" if not found["n"] else "{} apart on average, leaning {:+} ({} marks)".format(
            found["mean_distance"], found["mean_lean"], found["n"])))


def main(argv=None, ask=input, out=print, judge=None, path=CALIBRATION):
    parser = argparse.ArgumentParser(prog="python -m evals.calibrate", description=__doc__.split("\n\n")[0])
    parser.add_argument("--case", action="append", default=[], help="only this case (again for more)")
    parser.add_argument("--max", type=int, default=None, help="at most this many cases")
    parser.add_argument("--live", action="store_true", help="the plans Claude makes now (uses the account's usage)")
    args = parser.parse_args(argv)
    cases = [c for c in run.load() if "creative" in (c.get("tags") or [])]
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    cases = cases[:args.max] if args.max else cases
    if not cases:
        parser.error("no creative case to calibrate")
    brain = None if judge else judge_brain()
    judge = judge or (lambda case, plan: asyncio.run(creative.judge(brain, case, plan)))
    entries = kept(path)
    with tempfile.TemporaryDirectory(prefix="scene-calibrate-") as tmp:
        for case in cases:
            plan = run.run_case(case, Path(tmp) / case["id"], live=args.live, keep_plan=True)["full"]
            found = judge(case, plan)
            out("\n=== {} ({})\n{}".format(case["id"], case.get("about") or "", creative.plan_text(case, plan)))
            out("The judge: {}  {}".format(", ".join("{} {}".format(m, found["marks"].get(m)) for m in creative.MARKS), found.get("why") or ""))
            mine = asked_marks(found["marks"], ask, out)
            if mine is None:
                break
            entries.append({"case": case["id"], "at": time.strftime("%Y-%m-%d %H:%M"), "mode": "live" if args.live else "replay",
                            "judge": found["marks"], "human": mine, "why": found.get("why") or "", "model": found.get("model")})
            Path(path).write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report(entries, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
