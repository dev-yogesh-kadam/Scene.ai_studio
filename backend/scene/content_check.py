"""The content check: one call to the fast model over a plan's prompts and drawn words, in any language, before the
plan is shown for Approve (docs/guardrails.md). It flags what a word list cannot see:

- a real, identifiable person's likeness (a public figure, or a private person by name) the user gave no reference of;
- sexual content, and anything sexual or harmful involving minors;
- trademarked logos or brands the user did not supply;
- copyrighted characters, or a recreation of a specific existing film, game or show;
- hate, harassment, or violence beyond what a film rating would allow.

It answers {"flag": none | warn | block, "categories", "note"}. The setting content_check_mode (the console's
Guardrails card) decides what is done: "off" (no call), "warn" (the default: a flag is a one-line note on the plan card,
never a refusal) or "block" (a "block" refuses the plan with a plain message; a "warn" is a note). Every flag is written
to the moderation table (kind "content_check"), as the word list's refusals are.

The word list (moderation.py) stays as it is, and runs as well. When the call itself fails (Claude busy, down, a
malformed answer), the check fails OPEN: the plan goes on, the error is logged and kept for the console's Checks card,
so an outage of the model never stops the studio. The verdict of a plan's words is remembered (SEEN), so keeping the
same plan (POST /api/agent/plans) does not ask again."""

import hashlib
import time

from . import moderation

MODES = ("off", "warn", "block")
DEFAULT_MODE = "warn"
FLAGS = ("none", "warn", "block")
CATEGORIES = ("real_person", "sexual", "minors", "trademark", "copyrighted", "hate", "harassment", "violence")
TEXT_CHARS = 12_000   # of a plan's words looked at
SEEN_MOST = 500       # plans whose verdict is remembered
SEEN = {}             # the hash of a plan's words -> its verdict
last_error = {}       # the last time the check could not run: {"at", "error"}; the console's Checks card shows it

SYSTEM = """You check the plan of an AI image and video studio before the user approves it. You are given each step's
words (its prompt, and any words it draws on screen) and what the user supplied themselves: reference pictures, logos,
names of their own brand. Read every language. Flag only what is really there; ordinary creative work (a fight scene in
a film, a horror scene, a product ad for the user's own product, an invented character) is "none".
- "real_person": the likeness of a real, identifiable person (a public figure, a celebrity, a politician, or a private
  person named) when the user gave no reference picture of that person. A look "like" a celebrity counts.
- "sexual": sexual or nude content. "minors": anything sexual, abusive or exploitative involving a child (always block).
- "trademark": a real brand's logo, mascot or trademark the user did not supply (their own brand is fine).
- "copyrighted": a copyrighted character (from a film, show, game or comic), or a recreation of a specific existing
  film, game or show, its scenes or its look, even renamed.
- "hate", "harassment": content attacking people for who they are, or targeting a real person to demean them.
- "violence": gore or cruelty beyond what a film rating for adults would allow (a fight or a war scene is fine).
"flag": "block" for minors, sexual content, hate, harassment and extreme violence, and for a real person's likeness used
to deceive or demean; "warn" for the rest of what you flag (a likeness, a trademark, a copyrighted character); "none"
otherwise. "categories": the ones that apply ([] for none). "note": one plain sentence for the user, in the language of
their message, saying what was flagged and what to do instead ("" for none)."""

SHAPE = {"type": "object", "required": ["flag", "categories", "note"], "properties": {
    "flag": {"type": "string", "enum": list(FLAGS)},
    "categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)}},
    "note": {"type": "string"}}}

BLOCKED = "This plan can't be made here: {}"
NONE = {"flag": "none", "categories": [], "note": ""}


def mode(db):
    """content_check_mode as an admin set it (guardrails.choice), or the default."""
    from . import guardrails
    return guardrails.choice(db, "content_check_mode")


def plan_words(steps):
    """Each step's words as the check reads them: its name, then its prompt and the words it draws (moderation.prompt_of)."""
    lines = []
    for n, step in enumerate(steps if isinstance(steps, list) else [], start=1):
        if not isinstance(step, dict):
            continue
        said = moderation.prompt_of(moderation.step_settings(step)) or str(step.get("prompt") or "")
        if said.strip():
            lines.append("Step {} ({}): {}".format(n, str(step.get("name") or "")[:80], " ".join(said.split())))
    return "\n".join(lines)[:TEXT_CHARS]


def supplied(steps):
    """What the user supplied that the steps use, by name: the attached items and NeuralCore entries in their slots."""
    names = []
    for step in steps if isinstance(steps, list) else []:
        for use in (step.get("uses") or []) if isinstance(step, dict) else []:
            if isinstance(use, dict) and use.get("name"):
                names.append("{} ({})".format(use["name"], use.get("label") or use.get("slot") or "reference"))
        start = step.get("start") if isinstance(step, dict) else None
        if isinstance(start, dict) and start.get("name"):
            names.append("{} (the picture the shot starts on)".format(start["name"]))
    return list(dict.fromkeys(names))


def key_of(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean(found):
    """The model's verdict as kept: a flag of FLAGS, known categories, a one-line note."""
    if not isinstance(found, dict):
        return dict(NONE)
    flag = found.get("flag") if found.get("flag") in FLAGS else "none"
    categories = [c for c in found.get("categories") or [] if c in CATEGORIES] if isinstance(found.get("categories"), list) else []
    note = " ".join(str(found.get("note") or "").split())[:300]
    if flag == "none":
        return dict(NONE)
    return {"flag": flag, "categories": list(dict.fromkeys(categories)), "note": note or "This plan may use something it should not."}


def applied(verdict, how):
    """The verdict as the mode lets it act: in "warn" a block is only a note."""
    if verdict["flag"] == "block" and how != "block":
        return dict(verdict, flag="warn")
    return verdict


async def check(agent, db, user_id, steps, instruction=""):
    """The content check of a plan's steps: {"flag", "categories", "note"} as content_check_mode lets it act, or None
    when the mode is off or the plan has no words. Fails open: a call that fails is {"flag": "none", "error"}."""
    from .db import offload
    how = await offload(mode, db)
    text = plan_words(steps)
    if how == "off" or not text or agent is None:
        return None
    given = supplied(steps)
    key = key_of(how + "\n" + text + "\n" + "|".join(given))
    if key in SEEN:
        return SEEN[key]
    message = "The user's message:\n{}\n\nWhat the user supplied (references, logos):\n{}\n\nThe plan's words:\n{}".format(
        str(instruction or "")[:2000] or "(not given)", "\n".join(given) or "(nothing)", text)
    try:
        found = clean(await agent.check_content(SYSTEM, message, SHAPE))
    except Exception as error:   # fail open: an outage of the model must not stop the studio
        said = str(error) or type(error).__name__
        last_error.update(at=time.time(), error=said[:300])
        print("The content check could not run, so the plan goes on without it: {}".format(said))
        return dict(NONE, error=said[:300])
    verdict = applied(found, how)
    if found["flag"] != "none":
        await offload(record, db, user_id, found, text)
    SEEN[key] = verdict
    while len(SEEN) > SEEN_MOST:
        SEEN.pop(next(iter(SEEN)))
    return verdict


def record(db, user_id, found, text):
    """A flag, written to the moderation table (kind "content_check"; verdict the model's flag; words its categories)."""
    db.run("INSERT INTO moderation (kind, generation_id, user_id, verdict, words, prompt, by_name, created) "
           "VALUES ('content_check', NULL, ?, ?, ?, ?, 'content check', ?)",
           (user_id, found["flag"], ", ".join(found["categories"]) or found["note"][:120], text[:1000], time.time()))


def status():
    """For the console's Checks card: when the check last could not run, and why ({} when it has not failed)."""
    return dict(last_error)


def problem(verdict):
    """The refusal of a blocked plan, in words for the user, or None."""
    if verdict and verdict.get("flag") == "block":
        return BLOCKED.format(verdict.get("note") or "it asks for something the studio does not make.")
    return None
