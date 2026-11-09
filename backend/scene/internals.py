"""How much of the agent's own workings a user is shown in the chat.

The rows of the agent's work ("Read the skill “Script to Video”", "Opened NeuralCore: 3 entries", "Went on with this
conversation's Claude session", "Read 70,357 tokens") say how the studio is built: which skills it has, where it keeps
its memory, which model it runs on. An admin sees them as they are, and so does anyone whose staff role may read
"internals" (staff.py: the built-in Insider role, or any role an admin gives it). Everyone else sees the same rows in
plain words that name none of it ("Used a skill", "Checked the project's references"), and none of the counts of
tokens. The thoughts and the reply the model writes are kept, with the names of the skills taken out.

Only what is sent to the browser changes: the server's own copy (the admin's Sessions page, Langfuse) stays whole.
"""

import re

from . import skills, staff

AREA = "internals"   # the staff area that shows them (staff.AREAS)


def shown_to(user):
    """Whether this user sees the agent's workings as they are."""
    return staff.sees(user.get("role") if user else None, AREA)


# A row of the work in plain words, by what it says: (pattern, the words shown instead; None leaves the row out).
# The first that matches wins; a row that matches none keeps its words, with any skill's name taken out.
PLAIN = [
    (re.compile(r"^(Read the skill|Loaded the skill|Carried on with|Handed on from|Read “.*” of “)"), "Used a skill"),
    (re.compile(r"^No skill picked"), "Used a skill"),
    (re.compile(r"is (long|loaded already)"), None),
    (re.compile(r"^(Did not load|Checked “.*”: (needs|has))"), None),
    (re.compile(r"^Drafted the skill"), "Drafted a skill for an admin to publish"),
    (re.compile(r"^Went on with this conversation's .* session"), "Picked up the conversation"),
    (re.compile(r"^Compacted this conversation's context"), "Tidied up the conversation"),
    (re.compile(r"^Asked .* for a second opinion"), "Asked for a second opinion"),
    (re.compile(r"^(Opened|Looked in) NeuralCore"), "Checked the project's references"),
    (re.compile(r"^Looked in the other projects"), "Checked the other projects' references"),
    (re.compile(r"NeuralCore"), "Kept it with the project's references"),
    (re.compile(r"^(Read|Wrote) .* of the (run|conversation|project)|^Wrote \d+ leaves"), "Updated the run's notes"),
    (re.compile(r"^Saved to memory|^Forgot "), "Updated what it remembers"),
    (re.compile(r"^Updated the direction"), "Updated the notes"),
    (re.compile(r"^Looked up presets"), "Looked up tested settings"),
    (re.compile(r"^Kept “.*” in /|into /|^Checked /"), "Updated the run's notes"),
    (re.compile(r"(nothing of the run was saved|the model said what it would do|the model stopped with nothing|"
                r"first answer said it was making something)", re.IGNORECASE), None),
]


def _titles():
    """The names a skill goes by that never stand for anything else: its title in quotes, and its id when it has a
    hyphen in it (script-to-video). A bare word ("director", "short film") is left alone: it is also plain English."""
    try:
        found = skills.load()
    except OSError:
        return None
    titles = sorted({s["title"] for s in found if len(s["title"]) > 2}, key=len, reverse=True)
    ids = sorted({s["id"] for s in found if "-" in s["id"]}, key=len, reverse=True)
    if not titles and not ids:
        return None
    quoted = r"[“\"‘']\s*(?:{})\s*[”\"’']".format("|".join(map(re.escape, titles))) if titles else None
    bare = r"(?<![\w-])(?:{})(?![\w-])".format("|".join(map(re.escape, ids))) if ids else None
    return re.compile("|".join(f for f in (quoted, bare) if f), re.IGNORECASE)


def _scrub(text, titles):
    return titles.sub("a skill", text) if titles else text


def plain(event, titles):
    """An event of the agent's work as a user who may not see its workings is shown it, or None to leave it out."""
    kind = event.get("type")
    if kind == "thought":
        return dict(event, text=_scrub(str(event.get("text") or ""), titles))
    if kind != "activity":
        return event
    if event.get("icon") == "info":   # what the model read and wrote, in tokens
        return None
    text = str(event.get("text") or "")
    for pattern, words in PLAIN:
        if pattern.search(text):
            return dict(event, text=words) if words else None
    return dict(event, text=_scrub(text, titles))


def plain_log(log, titles):
    """A whole log of work in plain words, a row that says the same as the one before it said once."""
    shown = []
    for event in log or []:
        found = plain(event, titles)
        if found is None:
            continue
        if shown and found.get("type") == "activity" and shown[-1].get("type") == "activity" and shown[-1].get("text") == found.get("text"):
            continue
        shown.append(found)
    return shown


async def for_user(events, user):
    """The events of a plan as `user` may see them: as they are for an admin or an insider, in plain words otherwise."""
    if shown_to(user):
        async for event in events:
            yield event
        return
    titles = _titles()
    last = None   # the words of the last row sent, so "Used a skill" three times running is said once
    async for event in events:
        if event.get("type") == "plan":
            yield dict(event, activity=plain_log(event.get("activity"), titles), thought=_scrub(str(event.get("thought") or ""), titles),
                       reply=_scrub(str(event.get("reply") or ""), titles))
            continue
        found = plain(event, titles)
        if found is None:
            continue
        if found.get("type") == "activity":
            if found.get("text") == last:
                continue
            last = found.get("text")
        elif found.get("type") == "thought":
            last = None
        yield found
