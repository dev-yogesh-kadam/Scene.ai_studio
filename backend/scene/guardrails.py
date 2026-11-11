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
- content_check_mode: what the content check (content_check.py) does with a plan it flags: off, warn (a note on the
  plan card; the default) or block (a "block" flag refuses the plan). One of CHOICES, not a number.
- creative_auto_review: on (the default) or off: the automatic second opinion of a big job's plan and of a long run's
  shot plan. The studio pays for it (never the user's credits); off saves that Claude usage.

The quality gates at the end (continuity_gate, variety_gate, hook_gate, video_text_gate) are not limits: each is a
hint the model gets once before the user sees the plan (quality_hints), never a block.

Functions that read the database are sync: async code calls them with db.offload, as everything else does.
"""

import asyncio
import json
import math
import re
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


# The settings that are one of a few words, not a number: {key: (the words it may be)}, the first listed in
# CHOICE_DEFAULTS when an admin set nothing.
CHOICES = {"content_check_mode": ("off", "warn", "block"), "creative_auto_review": ("on", "off")}
CHOICE_DEFAULTS = {"content_check_mode": "warn", "creative_auto_review": "on"}


def choice(db, key):
    """One of CHOICES as an admin set it, or its default."""
    value = str(db.setting(key, CHOICE_DEFAULTS[key]) or "").strip().lower()
    return value if value in CHOICES[key] else CHOICE_DEFAULTS[key]


def shown(db):
    """What the console shows: the stop, every limit with its range, and every choice with the words it may be."""
    return {"stop": stopped(db), "limits": limits(db), "ranges": {k: list(v) for k, v in RANGES.items()}, "defaults": dict(DEFAULTS),
            "choices": {k: choice(db, k) for k in CHOICES}, "options": {k: list(v) for k, v in CHOICES.items()},
            "choice_defaults": dict(CHOICE_DEFAULTS)}


def save(db, body, by=""):
    """Change the stop ({"stop": true/false, "text"}), any limits ({"limits": {key: number}}) and any choices
    ({"choices": {key: word}}) an admin sent. A value out of its range, a word a choice does not have, or a key that is
    neither, is refused whole (ValueError) before anything is written."""
    body = body if isinstance(body, dict) else {}
    picked = body.get("choices") or {}
    if not isinstance(picked, dict):
        raise ValueError("choices is an object of {name: word}.")
    for key, value in picked.items():
        if key not in CHOICES:
            raise ValueError("{} is not a choice. The choices: {}.".format(key, ", ".join(CHOICES)))
        if value not in CHOICES[key]:
            raise ValueError("{} must be one of {}.".format(key, ", ".join(CHOICES[key])))
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
    for key, value in picked.items():
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


# ---------------------------------------------------------------- the quality gates (hints, never blocks)
#
# Each reads the model's own steps (the answer's "steps": tool, workflow, prompt, shot_size, move, place, uses...) and
# says what a creative director would send back, or None. quality_hints gathers them; the agent's route gives them to
# the model once, with its other notes, before the user sees the plan. A gate judges only what a plan says: a shot with
# no shot_size is not called the same size as another.

PEOPLE = ("girl", "boy", "woman", "man", "child", "kid", "lady", "gentleman", "teenager", "student", "chef", "mother",
          "father", "grandmother", "grandfather", "old man", "old woman", "fisherman", "fisherwoman", "dancer", "runner",
          "singer", "bride", "groom", "worker", "farmer", "detective", "soldier", "nurse", "doctor", "barista", "dog", "cat")
# "a girl of about twenty with a black braid and a yellow raincoat": a person and the words that describe them
DESCRIBED = re.compile(r"\b(?:a|an|the)\s+((?:[\w'-]+\s+){0,3}?(?:" + "|".join(sorted(PEOPLE, key=len, reverse=True)) + r"))\b"
                        r"((?:\s*,?\s*(?:of about|in (?:her|his|their)|with|wearing|dressed in|in a|in an)\s+[^,.;:]+)+)", re.IGNORECASE)
# ...of which the words of a look are compared: its colours, its hair and its clothes ("black braid", "yellow raincoat")
LOOK = frozenset("""black white grey gray silver red orange yellow gold golden green blue navy teal purple pink brown beige
cream maroon striped checked denim leather linen silk wool braid braids bun ponytail curls curly beard moustache mustache
bald hair fringe raincoat coat jacket hoodie sweater jumper shirt t-shirt kurta sari saree dupatta dress skirt jeans trousers
suit uniform apron scarf hat cap turban hijab glasses spectacles boots sneakers sandals backpack cardigan blazer
overalls vest tie bandana shawl lehenga""".split())
# where the next person's own words begin inside a description: "... and a girl of about sixteen"
NEXT_PERSON = re.compile(r"\s*(?:,|\band\b|\bwhile\b|\bas\b|\bbeside\b|\bnext to\b)\s+(?:a|an|the|his|her|their)\s+(?:[\w'-]+\s+){0,3}?(?:"
                         + "|".join(sorted(PEOPLE, key=len, reverse=True)) + r")\b", re.IGNORECASE)
WIDE = ("WS", "EWS", "")
STILL = ("static", "")
HOOK_WORDS = re.compile(r"\b(hook|close on|close-up|extreme close|macro|toward (?:the )?(?:camera|lens)|at (?:the )?(?:camera|lens)|"
                         r"bursts?|splash\w*|pours?|crack\w*|snaps?|reveal\w*|mid-?air|slams?|drops?|explod\w*|sudden\w*|pov|leaps?)\b",
                         re.IGNORECASE)
SOCIAL = re.compile(r"\b(reels?|shorts|tiktok|tik tok|stories|story post|instagram|insta|whatsapp status|social)\b", re.IGNORECASE)
# a video model asked for readable words: a sign that "reads" or "says", words in quotation marks in letters on something
# (a person who "says" words speaks them: that is sound, not text)
DRAWN = re.compile(r"(\b(reads?|(sign|banner|board|poster|screen|label|card|title)s? (that )?says|spells?|written|lettering|letters|"
                    r"caption\w*|headline|slogan|subtitle\w*|on-?screen text|text that|the words?)\b[^.]{0,40}[\"“'‘][^\"”'’]{2,}[\"”'’])"
                    r"|([\"“][^\"”]{2,40}[\"”]\s+(in|on)\s+(large|big|bold|neon|painted|white|red|gold)?\s*(letters|lettering|type|text|neon))",
                    re.IGNORECASE)


def _shots(steps, kind=None):
    """The steps that generate a picture or a video ("video" or "image" by their workflow), in order."""
    found = []
    for step in steps if isinstance(steps, list) else []:
        if not isinstance(step, dict) or (step.get("tool") or "generate") != "generate":
            continue
        made = str(step.get("workflow") or "").split("/", 1)[0]
        if kind is None or made == kind:
            found.append(step)
    return found


def _place_words(place):
    return {w for w in re.findall(r"[a-z]+", str(place or "").lower()) if w not in ("the", "a", "an", "of", "in", "at", "on")}


def continuity_gate(steps, book=()):
    """The same person or place described differently from shot to shot, when NeuralCore does not carry it: a place
    written two ways ("rainy night market", "the night market in the rain"), or a person whose description changes
    ("a girl with a black braid" then "a girl in a red coat"). A shot that uses a NeuralCore entry or a reference is
    left out: the reference carries the look."""
    shots = [s for s in _shots(steps) if not s.get("uses")]
    if len(shots) < 2:
        return None
    found = []
    places = list(dict.fromkeys(" ".join(str(s.get("place") or "").split()) for s in shots if str(s.get("place") or "").strip()))
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            wa, wb = _place_words(a), _place_words(b)
            if a.lower() != b.lower() and wa and wb and len(wa & wb) / len(wa | wb) >= 0.5 and not (wa < wb or wb < wa):
                found.append("the place is written two ways, “{}” and “{}”: write one place the same way in every shot".format(a, b))
    # a character NeuralCore attaches to every shot ("always") carries the look: its people are not compared
    carried = any(e.get("type") == "character" and e.get("always") for e in book or [])
    described = {}   # the person's noun -> [(the words of their look, as written)]
    for step in [] if carried else shots:
        for who, how in DESCRIBED.findall(str(step.get("prompt") or "")):
            how = NEXT_PERSON.split(how)[0]   # "... in a grey cardigan and a girl of about sixteen ...": his words only
            said = re.findall(r"[\w'-]+", how.lower())
            look = [w for w in said if w in LOOK]
            if look:   # shown up to its last word of a look: "with a black braid and a yellow raincoat"
                described.setdefault(who.lower().split()[-1], []).append(
                    (frozenset(look), " ".join(said[:max(i for i, w in enumerate(said) if w in LOOK) + 1])))
    for noun, ways in described.items():
        other = next((w for w in ways if w[0] != ways[0][0]), None)
        if other:
            found.append("the {} is described differently across shots (“{}” and “{}”): repeat one description word for word, "
                         "or keep the {} in NeuralCore first".format(noun, ways[0][1], other[1], noun))
    return "Continuity: " + "; ".join(found[:3]) + "." if found else None


def variety_gate(steps):
    """A video plan of three shots or more whose sizes are all the same (counting only the shots that give one)."""
    sizes = [str(s.get("shot_size") or "") for s in _shots(steps, "video")]
    given = [z for z in sizes if z]
    if len(sizes) < 3 or len(given) < 3 or len(set(given)) > 1:
        return None
    return ("Coverage: every shot is {}. Vary the sizes with the story (a wide to place us, a medium for the action, a close-up "
            "for the feeling, an insert for the detail).".format(given[0]))


def hook_gate(steps, instruction=""):
    """A social video plan (portrait, or for Reels, Shorts, TikTok, Stories) of two shots or more whose first shot does
    not hook: a static wide with no hook in its words. A first shot that gives neither its size nor its move is not
    judged."""
    shots = _shots(steps, "video")
    if len(shots) < 2:
        return None
    social = any(s.get("orientation") == "portrait" for s in shots) or bool(SOCIAL.search(str(instruction or "")))
    first = shots[0]
    size, move = str(first.get("shot_size") or ""), str(first.get("move") or "")
    if not social or (not size and not move):
        return None
    words = "{} {}".format(first.get("name") or "", first.get("prompt") or "")
    if size in WIDE and move in STILL and not HOOK_WORDS.search(words):
        return ("The hook: for social video the first one or two seconds decide whether anyone stays, and shot 1 is a static {}. "
                "Open on motion, a face close to the camera, or the product's most striking moment.".format(size or "wide"))
    return None


def video_text_gate(steps):
    """A video shot that asks the video model for readable words (a sign that reads "OPEN", a title in big letters)."""
    asked = [s for s in _shots(steps, "video") if DRAWN.search(str(s.get("prompt") or ""))]
    if not asked:
        return None
    return ("Words in a video: {} asks the video model for readable words, which come out garbled. Put the words on screen as "
            "a designed page (render_html) over the clip, or keep the sign far off or soft.".format(
                ", ".join("“{}”".format(str(s.get("name") or "a shot")) for s in asked[:3])))


def quality_hints(steps, instruction="", book=()):
    """Every quality gate's hint for a plan, in order (continuity, variety, the hook, words in a video); [] when all pass."""
    return [h for h in (continuity_gate(steps, book), variety_gate(steps), hook_gate(steps, instruction), video_text_gate(steps)) if h]
