"""The studio's guardrails on spending and on the agent, in one place (docs/guardrails.md).

The rule they keep: the model only proposes; the server checks and prices; nothing runs until Approve, and nothing
costs more than was approved. Each guardrail is a small function here, called by a one-line hook where the work
happens (credits.cap_problem, studio.price, plans.approve, claude.converse, the agent's route), so the limits are
read and changed in one module and tested in tests/test_guardrails.py.

What an admin sets lives in the `settings` table (read through db.setting, so a change reaches every process at once,
with no restart):

- guard_stop: the studio-wide stop (the kill switch), {"since", "by", "text"} while on. New agent turns and new
  renders are refused; renders already waiting do not start; a running plan stops at its next step.
- guard_plan_max: the most credits one plan may reserve at its approval. 0: no limit.
- guard_run_max: the most credits the renders of one run (a long skill's run) may cost together. 0: no limit.
- guard_job_seconds: the longest result one job may be priced for, in seconds (3600).
- guard_sessions_per_user: the live Claude sessions one user may hold at once, of claude.LIVE (3).
- guard_tool_calls: the most tool calls the agent may make while answering one message (200).
- guard_turn_seconds: the longest one message to the agent's live session may take (3600).
- creative_big_job_credits: a plan priced above this is a big job (agent.big_job): it gets the brief, the concept, the
  stills first and the automatic second opinion (600). 0: a big job by its number of shots alone.

Functions that read the database are sync: async code calls them with db.offload, as everything else does.
"""

import asyncio
import json
import math
import time

from fastapi import HTTPException

# ---------------------------------------------------------------- the settings

DEFAULTS = {
    "guard_plan_max": 0,
    "guard_run_max": 0,
    "guard_job_seconds": 3600,
    "guard_sessions_per_user": 3,
    "guard_tool_calls": 200,
    "guard_turn_seconds": 3600,
    "creative_big_job_credits": 600,
}
# What each may be set to: (lowest, highest). 0 is "no limit" where the lowest is 0.
RANGES = {
    "guard_plan_max": (0, 10_000_000),
    "guard_run_max": (0, 10_000_000),
    "guard_job_seconds": (10, 86_400),
    "guard_sessions_per_user": (1, 50),
    "guard_tool_calls": (5, 5_000),
    "guard_turn_seconds": (60, 86_400),
    "creative_big_job_credits": (0, 10_000_000),
}
# Seconds a tool may run before the agent is told it was stopped: the film operations wait up to FILM_WAIT (900 s) for
# their job, and a tool that asks a model (page_build, second_opinion) waits up to claude_timeout (600 s).
TOOL_SECONDS = {"web_fetch": 90, "import_url": 300, "find_assets": 120, "look": 300, "check_shots": 300, "state_read": 60,
                "state_write": 60, "state_check": 60, "memory": 60, "preset_search": 60, "craft_search": 60, "read_skill": 60, "read_text": 60,
                "page_read": 60, "page_write": 60, "save_note": 60, "skill_draft": 60}
TOOL_SECONDS_DEFAULT = 960
# How often an answer that can't be read (not JSON, not an object, not the answer's shape) is sent back to the model
# before the message fails with "can't be read".
MALFORMED_RETRIES = 1
MALFORMED_AGAIN = ("Your answer could not be read: {}. Answer again, only as one JSON object in the answer's shape "
                   "(\"thought\", \"reply\", \"steps\", ...), with no other text.")


def limit(db, key):
    """One limit as an admin set it, or its default; always a number in its range."""
    low, high = RANGES[key]
    try:
        value = float(db.setting(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        value = DEFAULTS[key]
    if not math.isfinite(value):
        value = DEFAULTS[key]
    if value == 0 and low == 0:
        return 0
    return int(min(high, max(low, value)))


_seen = dict(DEFAULTS)   # the limits as last read in this process: for claude.py, which has no database (known())


def limits(db):
    found = {key: limit(db, key) for key in DEFAULTS}
    _seen.update(found)
    return found


def known(key):
    """A limit as this process last read it (limits(), which every agent turn calls through turn_check)."""
    return _seen[key]


def shown(db):
    """What the console shows: the stop and every limit with its range."""
    return {"stop": stopped(db), "limits": limits(db), "ranges": {k: list(v) for k, v in RANGES.items()}, "defaults": dict(DEFAULTS)}


def save(db, body, by=""):
    """Change the stop ({"stop": true/false, "text"}) and any limits ({"limits": {key: number}}) an admin sent. A value
    out of its range, or a key that is not a limit, is refused whole (ValueError) before anything is written."""
    body = body if isinstance(body, dict) else {}
    changes = body.get("limits") or {}
    if not isinstance(changes, dict):
        raise ValueError("limits is an object of {name: number}.")
    clean = {}
    for key, value in changes.items():
        if key not in RANGES:
            raise ValueError("{} is not a limit. The limits: {}.".format(key, ", ".join(RANGES)))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("{} must be a number.".format(key))
        if value != int(value):   # 2.5 sessions or credits is not a limit: refused, not cut to 2
            raise ValueError("{} must be a whole number.".format(key))
        low, high = RANGES[key]
        if not (value == 0 and low == 0) and not low <= value <= high:
            raise ValueError("{} must be {} to {}{}.".format(key, low, high, " (0: no limit)" if low == 0 else ""))
        clean[key] = int(value)
    if "stop" in body and not isinstance(body["stop"], bool):
        raise ValueError("stop is true or false.")
    for key, value in clean.items():
        db.set_setting(key, value)
    if body.get("stop") is True:
        set_stop(db, True, by, body.get("text"))
    elif body.get("stop") is False:
        set_stop(db, False)
    return shown(db)


# ---------------------------------------------------------------- the stop (kill switch)

STOP_TEXT = "The studio has stopped new work for now. Try again later."


def stopped(db):
    """The stop while it is on: {"since", "by", "text"}; else None."""
    try:
        found = json.loads(db.setting("guard_stop", "") or "{}")
    except (TypeError, ValueError):
        return None
    return found if isinstance(found, dict) and found.get("since") else None


def set_stop(db, on, by="", text=""):
    if on:
        said = " ".join(str(text or "").split())[:300] or STOP_TEXT
        db.set_setting("guard_stop", json.dumps({"since": time.time(), "by": str(by or "")[:120], "text": said}))
    else:
        db.set_setting("guard_stop", "")
    return stopped(db)


def stop_problem(db):
    """What the user is told while the studio is stopped, or None."""
    found = stopped(db)
    return found["text"] if found else None


def refuse_if_stopped(db):
    """Raises 503 with the stop's words while the studio is stopped: for the agent's turns and new jobs."""
    problem = stop_problem(db)
    if problem:
        raise HTTPException(503, problem)


def turn_check(db):
    """At the start of an agent turn: refused while the studio is stopped, and the limits read again for claude.py."""
    refuse_if_stopped(db)
    return limits(db)


# ---------------------------------------------------------------- spending

def plan_step_problem(db, plan_id, user_id, amount):
    """Why a step of an approved plan can't draw `amount` credits, or None. A plan's step is paid from what was reserved
    at its approval (credits.PREPAID): a step that would cost more than is left was priced lower than it is (its
    length known only now, say) and the user never approved that price, so it is not made; the plan fails there and
    what is left of the reservation goes back. Called for credits.cap_problem while a plan's step is queued."""
    if amount <= 0:
        return None
    row = db.one("SELECT reserved_left FROM agent_plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
    left = row["reserved_left"] if row else 0
    if amount > left:
        return ("This step costs {} credits, more than the {} left of what was approved for its plan. "
                "Resume the plan to see its price again and approve it.".format(amount, left))
    return None


def plan_problem(db, user, total):
    """Why a plan priced `total` may not be approved, or None: the studio is stopped, or it is over the most one plan
    may cost (guard_plan_max). Admins have no plan limit, as they have no daily one."""
    stop = stop_problem(db)
    if stop:
        return stop
    most = limit(db, "guard_plan_max")
    if most and total > most and (user or {}).get("role") != "admin":
        return "This plan costs {} credits; one plan may cost at most {}. Make it in parts, or ask an admin.".format(total, most)
    return None


def run_problem(db, user_id, run, amount):
    """Why a render of `amount` credits may not be added to run `run` (a long skill's run), or None: the renders of one
    run may cost at most guard_run_max together (what was refunded not counted)."""
    from .credits import PREPAID   # a plan's step: its plan was held to guard_plan_max at its approval
    most = limit(db, "guard_run_max")
    if not most or not run or amount <= 0 or PREPAID.get() is not None:
        return None
    row = db.one("SELECT COALESCE(SUM(cost - credits_refunded), 0) AS n FROM jobs WHERE user_id = ? AND run = ?", (user_id, str(run)[:32]))
    spent = int(row["n"] or 0) if row else 0
    if spent + amount > most:
        return ("This needs {} credits, and this run has used {} of the {} one run may use. "
                "Start a new run, or ask an admin.".format(amount, spent, most))
    return None


MIN_SECONDS = 1   # the shortest length a job is priced for: a render is never shorter, whatever was typed


def quote_problem(db, seconds, credits):
    """Why a price can't be right, or None: a length that is not a number, under MIN_SECONDS or longer than
    guard_job_seconds (a duration typed as -5, 0.0001 or 1e9), or a price below 0. The server prices what it is asked: a length it can't make
    sense of is refused, never charged."""
    if seconds is not None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < MIN_SECONDS:
            return "The length asked for is not a number of seconds of at least {:g}.".format(MIN_SECONDS)
        most = limit(db, "guard_job_seconds")
        if seconds > most:
            return "The length asked for ({:g} s) is longer than one job may be ({} s).".format(seconds, most)
    if isinstance(credits, bool) or not isinstance(credits, (int, float)) or not math.isfinite(credits) or credits < 0:
        return "This could not be priced."
    return None


def check_quote(db, estimate):
    """quote_problem of an estimate ({"seconds", "credits"}) as a 400."""
    problem = quote_problem(db, estimate.get("seconds"), estimate.get("credits"))
    if problem:
        raise HTTPException(400, problem)
    return estimate


# ---------------------------------------------------------------- the agent

def user_of(key):
    """The user a live session's key belongs to ("<user id>:<run>:<project>", workspace._thread), or None."""
    head = str(key or "").split(":", 1)[0]
    return head if head.isdigit() else None


def sessions_to_close(live, key, per_user, busy=lambda key, entry: entry.lock.locked()):
    """Before a new live session opens for `key`: (the keys of that user's sessions to close first, the oldest idle
    ones, so they hold at most per_user with the new one; and the words to refuse it with when every one of theirs
    is answering, else ""). live: claude.live, {key: entry with .used and .lock}. busy(key, entry): in use (claude._busy)."""
    owner = user_of(key)
    if owner is None or key in live:
        return [], ""
    mine = [(entry.used, k) for k, entry in live.items() if user_of(k) == owner]
    over = len(mine) + 1 - max(1, int(per_user))
    if over <= 0:
        return [], ""
    idle = sorted((used, k) for used, k in mine if not busy(k, live[k]))
    if len(idle) < over:
        return [k for _, k in idle], ("You have {} conversations with the agent answering at once, the most one person may. "
                                      "Wait for one to finish.".format(len(mine)))
    return [k for _, k in idle[:over]], ""


def tool_call_problem(called, most):
    """Why one more tool call is refused while answering a message, or None. called: the tools called so far in it,
    this one included (claude._Live.called)."""
    if len(called) > most:
        return ("That call was not run: {} tool calls is the most while answering one message. Answer now with what you "
                "have.".format(most))
    return None


def tool_seconds(name):
    return TOOL_SECONDS.get(name, TOOL_SECONDS_DEFAULT)


async def run_tool(name, called, most, start):
    """One tool call of the agent's, within the limits: refused past `most` calls in the message, stopped after
    tool_seconds(name). start(): the tool's awaitable (a task, already in the message's context). Returns its text."""
    problem = tool_call_problem(called, most)
    if problem:
        return problem
    task = start()
    try:
        return str(await asyncio.wait_for(task, tool_seconds(name)))
    except asyncio.TimeoutError:
        return "{} took longer than {} s and was stopped. Try a smaller piece of work, or go on without it.".format(name, tool_seconds(name))


# Writers of the agent's memory (run_state.writer) whose values are text from outside the studio: a transcript read in,
# a library text kept whole. Read back by state_read, they come framed as agent.external frames them, as they did when
# they were first read.
OUTSIDE_WRITERS = {"transcript": "transcript", "read_text": "file"}


def framed_state(found, external, more=""):
    """state_read's answer for the model: a leaf ({"path", "value", "writer"}) or a folder ({"folder", "leaves"}), as
    JSON, each value written from outside text (OUTSIDE_WRITERS) framed by `external` (agent.external) and so marked as
    data. A folder's leaves need their "writer" (runs.read) for this. more: the note of where to read on."""
    def one(leaf):
        text = json.dumps(leaf, ensure_ascii=False)
        source = OUTSIDE_WRITERS.get(str(leaf.get("writer") or ""))
        return external(text, source) if source else text
    if found.get("folder"):
        return "\n".join(one(leaf) for leaf in found.get("leaves") or []) + more
    return one(found) + more


def answer_problem(content):
    """Why an answer of the agent's model can't be used, or None: it must be one JSON object, whose "reply" (when
    given) is text and whose "steps" (when given) are a list of objects. The answer's other fields are cleaned by
    agent.shaped."""
    try:
        answer = json.loads(content) if isinstance(content, (str, bytes)) else content
    except (TypeError, ValueError):
        return "it is not JSON"
    if not isinstance(answer, dict):
        return "it is not one JSON object"
    if "reply" in answer and answer["reply"] is not None and not isinstance(answer["reply"], str):
        return "\"reply\" is not text"
    steps = answer.get("steps")
    if steps is not None and (not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps)):
        return "\"steps\" is not a list of objects"
    return None
