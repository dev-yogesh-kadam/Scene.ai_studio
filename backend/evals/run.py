"""The agent's evals (docs/evals.md). Each case in evals/cases/*.json is a message to the agent and what must be true of
the plan the studio makes of its answer.

    python -m evals.run                       replay: each case's recorded answers play Claude; free, the same every run
    python -m evals.run --live --max 5        live: the real Claude Code on this PC answers (it uses the account's usage)
    python -m evals.run --case en-three-shots --tag injection --json out.json --verbose

Replay drives the studio's real route (POST /api/agent/plan): its tool loop, its checks, its pricing, a plan's
approval, all on the test database (SCENE_TEST_DATABASE_URL, never `scene`). Only the model is played. Live mode is
opt-in, capped, never in CI, and runs the same checks less those that read the recorded answers. With LANGFUSE_HOST,
LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY set (and --langfuse), the results also go to Langfuse as a dataset run."""

import argparse
import asyncio
import copy
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
LIVE_MAX = 10     # live cases at most in one run, whatever --max says: each is a real Claude Code session
LIVE_DEFAULT = 3
USER = {"name": "Eval", "email": "eval@example.com", "password": "correct horse battery"}
LANGS = ("en", "hi", "es")
# What a case may say must be true (expect); the checks read only these keys, and a key they do not know is an error.
CHECKS = ("steps", "kinds", "workflows", "names", "priced", "question", "questions", "reply_has", "reply_lacks", "reply_is",
          "told", "not_told", "framed", "not_in_steps", "over_budget", "asked", "sound", "schema", "status", "error_has",
          "brief_asked", "concept", "examples", "creative")
REPLAY_ONLY = ("asked", "framed", "told", "not_told", "schema", "reply_is", "examples")   # they read what the model was given or answered
# ...and the opposite: the creative judge (evals/creative.py) marks a plan Claude made; a replayed plan is the case's own
LIVE_ONLY = ("creative",)


class CaseError(ValueError):
    """A case file that cannot be run as written."""


# ---------------------------------------------------------------- the cases

def load(folder=CASES):
    """Every case, sorted by id. Each is checked for the fields a case must have."""
    cases, seen = [], set()
    for path in sorted(folder.glob("*.json")):
        for case in _listed(json.loads(path.read_text(encoding="utf-8"))):
            case["_file"] = path.name
            problem = _problem(case)
            if problem:
                raise CaseError("{} ({}): {}".format(case.get("id") or "a case", path.name, problem))
            if case["id"] in seen:
                raise CaseError("{}: two cases have this id".format(case["id"]))
            seen.add(case["id"])
            cases.append(case)
    return sorted(cases, key=lambda c: c["id"])


def _listed(found):
    return found if isinstance(found, list) else [found]


def _problem(case):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", str(case.get("id") or "")):
        return "an id of lower-case letters, digits and dashes"
    if case.get("lang") not in LANGS:
        return "a lang of {}".format(", ".join(LANGS))
    if not isinstance((case.get("ask") or {}).get("instruction"), str) or not (
            case["ask"]["instruction"].strip() or (case.get("expect") or {}).get("status", 200) != 200):
        return "ask.instruction, the message (blank only in a case that expects it refused)"
    if not isinstance(case.get("recorded"), list) or not case["recorded"]:
        return "recorded: the model's answers in turn, at least one"
    expect = case.get("expect")
    if not isinstance(expect, dict) or not expect:
        return "expect: what must be true"
    unknown = sorted(set(expect) - set(CHECKS))
    if unknown:
        return "expect has keys no check reads: {}".format(", ".join(unknown))
    return ""


def resolved(value, ids):
    """The case with "@name" (an item the setup made) as that item's id: alone as a value, the id itself; inside a
    text, its digits."""
    if isinstance(value, str):
        if value.startswith("@") and value[1:] in ids:
            return ids[value[1:]]
        return re.sub(r"@([a-z_]+)\b", lambda m: str(ids[m.group(1)]) if m.group(1) in ids else m.group(0), value)
    if isinstance(value, list):
        return [resolved(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: resolved(v, ids) for k, v in value.items()}
    return value


# ---------------------------------------------------------------- one case

class Played:
    """Claude, played by the case's recorded answers: each call the planner makes (its schema is the plan's) takes the
    next one. A call for anything else (a caption, a picture's description) is answered with nothing and counted."""

    def __init__(self, recorded):
        self.left, self.given, self.answers, self.other = list(recorded), [], [], 0

    async def chat(self, messages, schema, model=None, thread=None, **_):
        if not (isinstance(schema, dict) and "steps" in (schema.get("properties") or {})):
            self.other += 1
            return {}
        self.given.append(copy.deepcopy(messages))
        if not self.left:
            raise RuntimeError("the agent asked the model more times than the case recorded ({})".format(len(self.answers)))
        answer = self.left.pop(0)
        self.answers.append(answer)
        return copy.deepcopy(answer)


def make_items(client, user_id, items):
    """The library items a case starts with: {"ref", "kind", "name", "seconds", "video": true for a real 6 s clip}."""
    from scene import media
    db = client.app.state.db
    folder = client.app.state.outputs.folder(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    ids = {}
    for n, item in enumerate(items or []):
        filename = "{}.{}".format(item["ref"], {"video": "mp4", "audio": "mp3"}.get(item.get("kind"), "png"))
        if item.get("video"):
            seconds = int(item.get("seconds") or 6)
            asyncio.run(media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x48:d={}:r=24".format(seconds),
                                      "-pix_fmt", "yuv420p", folder / filename))
        ids[item["ref"]] = db.run(
            "INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, seconds, size, created, about) "
            "VALUES (?, 'x/y', ?, ?, ?, '', '{}', '{}', ?, 1, ?, ?)",
            (user_id, item.get("kind") or "image", item.get("name") or item["ref"], filename, item.get("seconds") or 0, n + 1,
             item.get("about") or ""))
    return ids


def run_case(case, folder, live=False, keep_plan=False):
    """Run one case on a fresh studio. Returns {"id", "ok", "checks": [(name, ok, said)], "plan", "seconds"}, and with
    keep_plan the whole plan the studio answered too ("full": what evals.calibrate shows and has judged)."""
    import pytest
    from scene import web
    from scene.api import workspace
    from evals.studio import studio
    started = time.time()
    setup = case.get("setup") or {}
    with studio(folder, live=live) as client, pytest.MonkeyPatch.context() as patch:
        me = client.post("/api/auth/register", json=USER).json()
        db = client.app.state.db
        if "credits" in setup:
            db.run("UPDATE users SET credits = ? WHERE id = ?", (int(setup["credits"]), me["id"]))
        ids = make_items(client, me["id"], setup.get("items"))
        case = resolved({k: v for k, v in case.items() if not k.startswith("_")}, ids)
        played = Played(case["recorded"])
        if not live:
            patch.setattr(client.app.state.agent, "chat", played.chat)

        async def described(*_, **__):   # pictures are never sent anywhere to be described
            return 0
        patch.setattr(workspace.memory, "describe_missing", described)
        pages = {p["url"]: p for p in setup.get("pages") or []}

        async def page(url, client=None):   # the web is never reached: the case's own pages, or nothing
            if url not in pages:
                raise web.WebError("there is no such page in this case")
            p = pages[url]
            return {"url": url, "title": p.get("title") or "", "date": p.get("date") or "", "text": p["text"]}
        patch.setattr(web, "page", page)
        ask = dict(case["ask"])
        project = None
        if ask.pop("project", False):
            project = client.post("/api/projects", json={"name": "Eval"}).json()["id"]
            ask["project_id"] = project
        answered = client.post("/api/agent/plan", json=ask)
        plan = answered.json() if answered.headers.get("content-type", "").startswith("application/json") else {}
        context = {"client": client, "user": me, "played": played, "status": answered.status_code, "plan": plan, "live": live,
                   "case": case}
        checks = check(case.get("expect") or {}, context)
    return {"id": case["id"], "lang": case["lang"], "tags": case.get("tags") or [], "ok": all(ok for _, ok, _ in checks),
            "checks": checks, "plan": _short(plan), "status": context["status"], "seconds": round(time.time() - started, 2),
            "asked": len(played.answers), "other_calls": played.other, **({"judged": context["judged"]} if context.get("judged") else {}),
            **({"full": plan} if keep_plan else {})}


def _short(plan):
    return {"reply": (plan.get("reply") or "")[:400], "total": plan.get("total"), "balance": plan.get("balance"),
            "question": plan.get("question"), "questions": plan.get("questions") or [], "concept": plan.get("concept") or "", "steps": [{"name": s.get("name"), "kind": s.get("kind"), "credits": s.get("credits"),
                                                         "workflow": (s.get("settings") or {}).get("workflow")}
                                                        for s in plan.get("steps") or []]}


# ---------------------------------------------------------------- the checks

def check(expect, c):
    """[(check, passed, what was found)] for each key of `expect` (CHECKS); in live mode the replay-only ones are left out."""
    plan, steps = c["plan"], c["plan"].get("steps") or []
    out = []

    def said(name, ok, found):
        out.append((name, bool(ok), found if not ok else ""))

    if "status" in expect or c["status"] != 200:
        want = expect.get("status", 200)
        said("status", c["status"] == want, "answered {} (detail: {})".format(c["status"], str(plan.get("detail") or "")[:200]))
        if c["status"] != 200:
            if "error_has" in expect:
                said("error_has", str(expect["error_has"]).lower() in str(plan.get("detail") or "").lower(), plan.get("detail"))
            return out
    for name in expect:
        if name in ("status", "error_has") or (c["live"] and name in REPLAY_ONLY) or (not c["live"] and name in LIVE_ONLY):
            continue
        want = expect[name]
        if name == "steps":
            low, high = (want, want) if isinstance(want, int) else (want.get("min", 0), want.get("max", 10 ** 6))
            said(name, low <= len(steps) <= high, "{} steps".format(len(steps)))
        elif name == "kinds":
            got = [s.get("kind") for s in steps]
            said(name, got == want, got)
        elif name == "workflows":
            got = [(s.get("settings") or {}).get("workflow") for s in steps]
            said(name, all(g == w or (w.endswith("/") and str(g).startswith(w)) for g, w in zip(got, want)) and len(got) == len(want), got)
        elif name == "names":
            got = [s.get("name") for s in steps]
            said(name, got == want, got)
        elif name == "priced":   # no step without a price: generated ones cost credits, edits none, and the total adds up
            bad = [s.get("name") for s in steps if not isinstance(s.get("credits"), int) or s["credits"] < 0
                   or (s.get("kind") in ("image", "video", "audio") and str((s.get("settings") or {}).get("workflow", "")).split("/")[0]
                       in ("image", "video", "audio") and s["credits"] == 0)]
            total = sum(s.get("credits") or 0 for s in steps)
            said(name, not bad and plan.get("total") == total, "unpriced {}; total {} of steps {}".format(bad, plan.get("total"), total))
        elif name == "question":
            q = plan.get("question") or {}
            asked = bool(q.get("text")) and len(q.get("options") or []) >= 2
            said(name, asked == bool(want), "question {!r}".format(q))
        elif name == "questions":
            got = plan.get("questions") or []
            said(name, len(got) == want, "{} questions".format(len(got)))
        elif name == "reply_has":
            reply = str(plan.get("reply") or "").lower()
            missing = [w for w in _many(want) if w.lower() not in reply]
            said(name, not missing, "the reply lacks {}".format(missing))
        elif name == "reply_lacks":
            reply = str(plan.get("reply") or "").lower()
            found = [w for w in _many(want) if w.lower() in reply]
            said(name, not found, "the reply has {}".format(found))
        elif name == "reply_is":
            from scene import agent
            said(name, plan.get("reply") == getattr(agent, want), "reply {!r}".format(str(plan.get("reply"))[:120]))
        elif name in ("told", "not_told"):   # in what the model was given, any call
            given = json.dumps(c["played"].given, ensure_ascii=False)
            hits = [w for w in _many(want) if (w in given) != (name == "told")]
            said(name, not hits, "{} {}".format("not given" if name == "told" else "given", hits))
        elif name == "framed":   # the page reached the model only inside the studio's frame, its closing tag broken
            from scene import agent
            results = [m["content"] for given in c["played"].given for m in given
                       if m.get("role") == "user" and str(m.get("content") or "").startswith("Result of web_fetch:")]
            framed = results and all(agent.FRAMED.search(r) and agent.EXTERNAL_NOTE in r and r.count("</external>") == 1 for r in results)
            said(name, bool(framed) == bool(want), "{} web_fetch result(s), framed: {}".format(len(results), bool(framed)))
        elif name == "not_in_steps":
            text = json.dumps([{k: s.get(k) for k in ("name", "prompt")} for s in steps], ensure_ascii=False).lower()
            found = [w for w in _many(want) if w.lower() in text]
            said(name, not found, "the steps have {}".format(found))
        elif name == "over_budget":
            said(name, *_over_budget(c, plan, steps, want))
        elif name == "asked":
            said(name, len(c["played"].answers) == want, "asked {} times".format(len(c["played"].answers)))
        elif name == "sound":
            got = [s for s in steps if s.get("sound")]
            said(name, bool(got) == bool(want), "{} sound steps".format(len(got)))
        elif name == "schema":
            problems = [p for a in c["played"].answers if "tool" not in a for p in schema_problems(a)]
            said(name, (not problems) == bool(want), problems[:3])
        elif name == "brief_asked":   # a big job's brief card: questions (or one question) and no steps yet
            asked = bool(plan.get("questions") or (plan.get("question") or {}).get("text")) and not steps
            said(name, asked == bool(want), "{} questions, {} steps".format(len(plan.get("questions") or []), len(steps)))
        elif name == "concept":
            got = str(plan.get("concept") or "")
            said(name, bool(got) == bool(want), "concept {!r}".format(got[:120]))
        elif name == "examples":   # the craft note and the gold examples a big job's message carries
            from scene import craft_library
            given = json.dumps(c["played"].given, ensure_ascii=False)
            found = craft_library.EXAMPLES_HEAD.strip() in given and "Craft note that fits this job" in given
            said(name, found == bool(want), "examples {}given".format("" if found else "not "))
        elif name == "creative":
            said(name, *_judged(c, want))
    return out


def _judged(c, want):
    """The creative judge's marks of a live plan against the thresholds (evals/creative.py)."""
    from evals import creative
    try:
        found = c["client"].portal.call(creative.judge, c["client"].app.state.agent, c["case"], c["plan"])
    except Exception as error:   # no judge, no pass: a case is not passed on a mark nobody gave
        return False, "the judge could not mark it: {}".format(error)
    c["judged"] = found
    low = creative.below(found["marks"], want)
    return not low, "{} ({})".format(", ".join("{} {} < {}".format(m, g, t) for m, g, t in low), found["why"][:200])


def _many(value):
    return value if isinstance(value, list) else [value]


def _over_budget(c, plan, steps, want):
    """The plan costs more than the balance: priced all the same, and approving it is refused with nothing charged."""
    client = c["client"]
    before = client.get("/api/auth/me").json()["credits"]
    over = (plan.get("total") or 0) > before
    if not want:
        return over is False, "total {} of balance {}".format(plan.get("total"), before)
    if not over:
        return False, "total {} is within the balance {}".format(plan.get("total"), before)
    made = client.post("/api/agent/plans", json={"steps": [{k: s[k] for k in ("name", "kind", "settings") if k in s} for s in steps]})
    if made.status_code != 200:
        return False, "the plan was not kept ({}: {})".format(made.status_code, str(made.json().get("detail"))[:160])
    approved = client.post("/api/agent/plans/{}/approve".format(made.json()["id"]))
    after = client.get("/api/auth/me").json()["credits"]
    state = client.get("/api/agent/plans/{}".format(made.json()["id"])).json().get("state")
    return (approved.status_code == 402 and after == before and state == "waiting",
            "approve answered {}, balance {} -> {}, plan {}".format(approved.status_code, before, after, state))


def schema_problems(answer):
    """What in a final answer does not fit the plan's shape (agent.reply_format). A recorded answer may leave out a
    step's fields the studio fills (the real model is held to all of them by Claude Code's --json-schema), so a step
    must have only "tool" and "name"; everything given must have the right type."""
    from scene import agent
    try:
        import jsonschema
    except ImportError:   # claude-agent-sdk's own dependency; without it only the fields are checked
        jsonschema = None
    shape = copy.deepcopy(agent.reply_format(sorted(_workflows())))
    shape["properties"]["steps"]["items"]["required"] = ["tool", "name"]
    if jsonschema is None:
        return ["missing {}".format(k) for k in shape["required"] if k not in answer]
    return [e.message[:160] for e in jsonschema.Draft202012Validator(shape).iter_errors(answer)]


def _workflows():
    """The ids of the evals studio's models (tests/studio_models.py, studio.studio): each is a workflow "<folder>/@<id>"."""
    from scene.providers.workflows import workflow_id
    tests = str(HERE.parent / "tests")
    if tests not in sys.path:
        sys.path.insert(0, tests)
    import studio_models
    return {workflow_id(m["capability"], m["id"]) for m in studio_models.MODELS} - {None}


# ---------------------------------------------------------------- a run

def report(results, out=sys.stdout):
    passed = sum(r["ok"] for r in results)
    width = max([len(r["id"]) for r in results] + [4])
    for r in results:
        print("{} {:<{w}} {:>2} {:>6.2f}s  {}".format("PASS" if r["ok"] else "FAIL", r["id"], r["lang"], r["seconds"],
                                                    "; ".join("{}: {}".format(n, f) for n, ok, f in r["checks"] if not ok)[:300],
                                                    w=width), file=out)
    by_lang = {lang: [r for r in results if r["lang"] == lang] for lang in LANGS}
    print("evals: {} of {} passed ({})".format(passed, len(results), ", ".join(
        "{} {}/{}".format(lang, sum(r["ok"] for r in rs), len(rs)) for lang, rs in by_lang.items() if rs)), file=out)
    return passed == len(results)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="the real Claude Code answers (opt-in; uses the account's usage)")
    parser.add_argument("--max", type=int, default=None, help="live: at most this many cases (default {}, never more than {})".format(LIVE_DEFAULT, LIVE_MAX))
    parser.add_argument("--case", action="append", default=[], help="only this case (again for more)")
    parser.add_argument("--tag", action="append", default=[], help="only the cases with this tag")
    parser.add_argument("--lang", choices=LANGS)
    parser.add_argument("--json", help="write the results to this file")
    parser.add_argument("--langfuse", action="store_true", help="also send the results to Langfuse as a dataset run (LANGFUSE_* set)")
    parser.add_argument("--run-name", default="", help="the dataset run's name in Langfuse (default: the mode and the time)")
    parser.add_argument("--list", action="store_true", help="list the cases and stop")
    args = parser.parse_args(argv)
    if args.max is not None and not args.live:
        parser.error("--max is for --live; replay runs every case")
    if args.live and (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
        parser.error("live evals never run in CI: they call the real Claude Code")
    cases = load()
    if args.case:
        unknown = sorted(set(args.case) - {c["id"] for c in cases})
        if unknown:
            parser.error("no such case: {}".format(", ".join(unknown)))
        cases = [c for c in cases if c["id"] in args.case]
    if args.tag:
        cases = [c for c in cases if set(args.tag) & set(c.get("tags") or [])]
    if args.lang:
        cases = [c for c in cases if c["lang"] == args.lang]
    if args.list:
        for c in cases:
            print("{:<40} {}  {:<24} {}".format(c["id"], c["lang"], ",".join(c.get("tags") or []), c.get("about") or ""))
        return 0
    if args.live:
        cap = min(args.max or LIVE_DEFAULT, LIVE_MAX)
        if len(cases) > cap:
            print("live: the first {} of {} cases (--max)".format(cap, len(cases)))
            cases = cases[:cap]
    if not cases:
        parser.error("no case to run")
    results = []
    with tempfile.TemporaryDirectory(prefix="scene-evals-") as tmp:
        for case in cases:
            try:
                results.append(run_case(case, Path(tmp) / case["id"], live=args.live))
            except Exception as error:   # a case that cannot run is a failure of its own; the others still run
                results.append({"id": case["id"], "lang": case["lang"], "tags": case.get("tags") or [], "ok": False, "seconds": 0,
                                "checks": [("ran", False, "{}: {}".format(type(error).__name__, error))], "plan": {}, "status": 0})
    ok = report(results)
    if args.json:
        Path(args.json).write_text(json.dumps({"mode": "live" if args.live else "replay", "results": results}, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")
    if args.langfuse:
        from evals import langfuse_run
        target = langfuse_run.target_from_env()
        if target is None:
            print("Langfuse: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not all set; nothing sent.")
        else:
            name = args.run_name or "{}-{}".format("live" if args.live else "replay", time.strftime("%Y%m%d-%H%M%S"))
            try:
                sent = asyncio.run(langfuse_run.send(target, name, cases, results))
                print("Langfuse: dataset run {!r}, {} results sent.".format(name, sent))
            except (LookupError, PermissionError) as refused:   # no Langfuse, or its words are off: the run's results stand
                print("Langfuse: nothing sent ({}).".format(refused))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
