"""Harvest candidates from real use (docs/evals.md, docs/creative-director.md): turns people liked become candidate gold
examples, turns they disliked candidate eval cases. Nothing goes into the live sets on its own: a human reads each
candidate, fills in what is missing (a gold example's "why", an eval case's "expect") and moves it over.

    python -m evals.harvest                    the last 14 days, from Langfuse when it is set, else the studio's tables
    python -m evals.harvest --days 30 --limit 100 --source local

Writes:
- backend/scene/gold/candidates/<id>.json: a liked or approved turn as a gold example, "status": "draft". The gold
  loader never reads this folder: a human moves a reviewed one up into gold/ (and marks it approved).
- backend/evals/cases/candidates/<id>.json: a disliked, retaken or badly reviewed turn as an eval case with "expect":
  {"creative": true}. The runner reads only cases/*.json: a human moves a reviewed one up.

What makes a turn good or bad is what the studio already scores in Langfuse (langfuse_trace.Sender.score / item_score):
"user-thumb" 1 (liked) and "approved" 1 (a plan or a still approved) are good; "user-thumb" 0 (disliked), "retaken" 1 (a
shot made again) and "review" 0 (a major fault found) are bad. Bad wins over good. ("user-feedback" is the thumb's
older name, still read.)

Sources:
- langfuse (LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY set): the traces with those scores, each trace's input
  as the brief and its output as the plan. Best effort: what a trace holds depends on what the studio sent it.
- local (the studio's own tables, without Langfuse): the same signals read where they are kept: an approved plan
  (agent_plans) is good, and bad when something it made got a thumbs-down (generations.rating -1), was made again (a job
  whose "parent" is one of its items) or failed its review (generations.review not passed). The brief is the user's
  message just before it in their Claude session's story (claude_events).
A candidate already written (same id) is not written again."""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_CANDIDATES = HERE.parent / "scene" / "gold" / "candidates"
CASE_CANDIDATES = HERE / "cases" / "candidates"
DAY = 86_400
# The scores of a turn, and what each value says of it (langfuse_trace: library thumbs, plans.approve, jobs.add, review.py)
SIGNALS = {"user-thumb": {1: "up", 0: "down"}, "user-feedback": {1: "up", 0: "down"}, "approved": {1: "approved"},
           "retaken": {1: "retaken"}, "review": {0: "major"}}
GOOD = ("up", "approved")
BAD = ("down", "retaken", "major")


def verdict_of(signals):
    """One verdict from a turn's signals: a bad one wins over a good one; None when none says anything."""
    return next((v for v in BAD if v in signals), None) or next((v for v in GOOD if v in signals), None)


# ---------------------------------------------------------------- what a turn becomes

def shape_of(steps):
    found = {str((s.get("settings") or {}).get("orientation") or s.get("orientation") or "") for s in steps if isinstance(s, dict)}
    return next((f for f in found if f), "")


def outline(steps):
    lines = []
    for n, step in enumerate(steps if isinstance(steps, list) else [], start=1):
        if isinstance(step, dict):
            settings = step.get("settings") if isinstance(step.get("settings"), dict) else {}
            prompt = " ".join(str(step.get("prompt") or settings.get("prompt") or "").split())[:240]
            lines.append("{}. {} · {}: {}".format(n, step.get("name") or "step", step.get("kind") or settings.get("workflow") or "", prompt))
    return lines


def language(text):
    if re.search(r"[ऀ-ॿ]", text or ""):
        return "hi"
    if re.search(r"[áéíóúñ¿¡]", (text or "").lower()):
        return "es"
    return "en"


def gold_candidate(turn):
    return {"id": "cand-" + turn["id"], "status": "draft", "brief": turn["brief"],
            "context": {"platform": shape_of(turn["steps"]) or "(to fill in)", "audience": "(to fill in)"},
            "concept": turn.get("concept") or "(to fill in)", "plan_outline": outline(turn["steps"]),
            "why": ["(a human creative writes why it works)"], "tags": ["harvested"],
            "source": {"from": turn["source"], "ref": turn["ref"], "verdict": turn["verdict"], "at": turn["at"]}}


def case_candidate(turn):
    lang = language(turn["brief"])
    return {"id": "{}-cand-{}".format(lang, turn["id"]), "lang": lang, "about": "Harvested: a disliked turn ({})".format(turn["ref"]),
            "tags": ["creative", "candidate", "harvested"], "ask": {"instruction": turn["brief"]},
            "recorded": [{"thought": "", "concept": turn.get("concept") or "", "reply": turn.get("reply") or "",
                          "steps": [{"tool": "generate", "name": s.get("name") or "step",
                                     "prompt": str(s.get("prompt") or (s.get("settings") or {}).get("prompt") or "")}
                                    for s in turn["steps"] if isinstance(s, dict)][:12],
                          "direction": "", "question": {"text": "", "options": []}, "claims_making": bool(turn["steps"]),
                          "wants_sound": False, "go_ahead": False}],
            "expect": {"creative": True}, "source": {"from": turn["source"], "ref": turn["ref"], "at": turn["at"]}}


def write(turns, gold=None, cases=None):
    """Each good turn as a gold candidate, each bad one as a case candidate; one already there is left alone.
    Returns {"gold": [paths written], "cases": [paths written]}. gold, cases: the folders (GOLD_CANDIDATES,
    CASE_CANDIDATES when not given)."""
    gold, cases = gold or GOLD_CANDIDATES, cases or CASE_CANDIDATES
    made = {"gold": [], "cases": []}
    for turn in turns:
        good = turn["verdict"] in GOOD
        found = gold_candidate(turn) if good else case_candidate(turn)
        folder = Path(gold if good else cases)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (found["id"] + ".json")
        if path.exists():
            continue
        path.write_text(json.dumps(found, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        made["gold" if good else "cases"].append(path)
    return made


# ---------------------------------------------------------------- the studio's own tables

def local_turns(db, days=14, limit=50, now=None):
    """Approved plans of the last `days`, newest first, each a turn: {"id", "ref", "source", "verdict" (verdict_of its
    signals: up, approved, or down, retaken, major), "brief", "reply", "steps", "at"}. A plan with no message before it is
    left out: without its brief it teaches nothing."""
    since = (now or time.time()) - days * DAY
    turns = []
    for plan in db.all("SELECT id, user_id, steps, progress, created FROM agent_plans WHERE approved IS NOT NULL AND created > ? "
                       "ORDER BY id DESC LIMIT ?", (since, int(limit))):
        try:
            steps, progress = json.loads(plan["steps"] or "[]"), json.loads(plan["progress"] or "[]")
        except ValueError:
            continue
        jobs = [p.get("job") for p in progress if isinstance(p, dict) and p.get("job")]
        made = db.all("SELECT id, rating, review FROM generations WHERE job_id IN ({})".format(", ".join("?" * len(jobs))),
                      tuple(jobs)) if jobs else []
        signals = {"approved"}
        for item in made:
            signals.add({1: "up", -1: "down"}.get(item["rating"], ""))
            review = item["review"] if isinstance(item["review"], dict) else _loaded(item["review"])
            if isinstance(review, dict) and review.get("passed") is False:
                signals.add("major")
        if made and db.one("SELECT 1 FROM jobs WHERE settings->>'parent' IN ({}) LIMIT 1".format(", ".join("?" * len(made))),
                           tuple(str(item["id"]) for item in made)):
            signals.add("retaken")
        said = db.one("SELECT e.text FROM claude_events e JOIN claude_sessions s ON s.id = e.session_id WHERE s.user_id = ? "
                      "AND e.kind = 'user' AND e.at <= ? ORDER BY e.at DESC LIMIT 1", (plan["user_id"], plan["created"]))
        if not said or not str(said["text"] or "").strip():
            continue
        turns.append({"id": "plan-{}".format(plan["id"]), "ref": "agent_plans {}".format(plan["id"]), "source": "local",
                      "verdict": verdict_of(signals), "brief": str(said["text"]).strip()[:2000],
                      "reply": "", "steps": steps if isinstance(steps, list) else [], "at": plan["created"]})
    return turns


# ---------------------------------------------------------------- Langfuse

def _loaded(text):
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


async def langfuse_turns(target, days=14, limit=50, client=None, signals=SIGNALS):
    """The traces Langfuse scored with SIGNALS, as turns (see the module's note): target is (url, "Basic ..."), as
    langfuse_run.target_from_env gives it."""
    import httpx
    url, auth = target
    headers = {"Authorization": auth}
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    turns, said = [], {}   # said: a trace's id -> its signals
    try:
        for name, meaning in signals.items():
            found = await client.get(url + "/api/public/v2/scores", headers=headers, params={"name": name, "limit": int(limit)})
            if found.status_code != 200:
                continue
            for score in (found.json() or {}).get("data") or []:
                value = score.get("value")
                if isinstance(value, (int, float)) and score.get("traceId") and meaning.get(value):
                    said.setdefault(score["traceId"], set()).add(meaning[value])
        for trace_id, found_signals in said.items():
            verdict = verdict_of(found_signals)
            if verdict:
                trace = await client.get(url + "/api/public/traces/" + trace_id, headers=headers)
                if trace.status_code != 200:
                    continue
                body = trace.json() or {}
                brief = _text_of(body.get("input"))
                if not brief:
                    continue
                answered = body.get("output") if isinstance(body.get("output"), dict) else {}
                turns.append({"id": "lf-" + str(trace_id)[:16], "ref": "langfuse trace {}".format(trace_id),
                              "source": "langfuse", "verdict": verdict, "brief": brief[:2000],
                              "reply": _text_of(answered.get("reply")), "concept": _text_of(answered.get("concept")),
                              "steps": answered.get("steps") if isinstance(answered.get("steps"), list) else [],
                              "at": body.get("timestamp") or ""})
    finally:
        if own:
            await client.aclose()
    return turns[:int(limit)]


def _text_of(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("instruction", "message", "text", "content"):
            if isinstance(value.get(key), str):
                return value[key].strip()
    return ""


# ---------------------------------------------------------------- the command

def main(argv=None, db=None, out=print):
    parser = argparse.ArgumentParser(prog="python -m evals.harvest", description=__doc__.split("\n\n")[0])
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--source", choices=("auto", "local", "langfuse"), default="auto")
    args = parser.parse_args(argv)
    from evals import langfuse_run
    target = langfuse_run.target_from_env() if args.source in ("auto", "langfuse") else None
    if args.source == "langfuse" and target is None:
        parser.error("--source langfuse needs LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
    if target is not None:
        turns = asyncio.run(langfuse_turns(target, args.days, args.limit))
        out("Langfuse: {} scored turns".format(len(turns)))
    else:
        if db is None:
            from scene.config import Settings
            from scene.db import Database
            db = Database(Settings().database_url)
        turns = local_turns(db, args.days, args.limit)
        out("The studio's tables: {} approved plans with their message".format(len(turns)))
    made = write(turns)
    out("Wrote {} gold candidates ({}) and {} eval case candidates ({}). Review each and move the good ones up by hand.".format(
        len(made["gold"]), GOLD_CANDIDATES, len(made["cases"]), CASE_CANDIDATES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
