"""What the agent remembers of a user in one module (a project's module, or its main canvas): how they like to work
there (pref.), what they keep using (ptr.: a voice, a character, a logo, by its id), lessons in the agent's own words
(note.) and what they are (profile.). Each module keeps its own; nothing of it is shared with another module or project,
and a conversation in no project keeps none. A digest of the module's goes with every message there; it fills gaps and
never overrides what the user asks now, a skill's rules or the module's own facts (NeuralCore keeps those).

A reply the memory shaped ends with "[from memory: pref.framing, ptr.voice_maya]": the studio takes that line off and
shows the keys as chips under the reply.
"""

import re
import time

KEY = re.compile(r"^(pref|ptr|note|profile)\.[a-z0-9_]{1,40}$")
MAX_VALUE = 400        # characters of one entry
MOST = 60              # entries a user may have in one module
DIGEST_CHARS = 3000    # how much of it goes with a message
USED = re.compile(r"\n?\s*\[from memory:\s*([^\]]*)\]\s*$", re.IGNORECASE)


class RecallError(ValueError):
    pass


NO_MODULE = "Memory belongs to a module: open a project first."


def _module(project):
    """The module's id, or a RecallError when there is none (memory is never kept outside one)."""
    if not project:
        raise RecallError(NO_MODULE)
    return int(project)


def clean_key(key):
    key = str(key or "").strip().lower()
    if not KEY.match(key):
        raise RecallError("A memory key is namespace.name: pref.<name> for a preference or correction, ptr.<name> for "
                          "something they keep using (its id), note.<name> for a lesson, profile.<name> for who they are.")
    return key


def remember(db, user_id, project, key, value):
    project = _module(project)
    key, value = clean_key(key), " ".join(str(value or "").split())[:MAX_VALUE]
    if not value:
        raise RecallError("Give what to remember in value.")
    if not db.one("SELECT 1 FROM user_memory WHERE user_id = ? AND project_id = ? AND key = ?", (user_id, project, key)) and             db.one("SELECT COUNT(*) AS n FROM user_memory WHERE user_id = ? AND project_id = ?", (user_id, project))["n"] >= MOST:
        raise RecallError("The memory of this module holds {} entries, the most: forget one first.".format(MOST))
    db.run("INSERT INTO user_memory (user_id, project_id, key, value, updated) VALUES (?, ?, ?, ?, ?) "
           "ON CONFLICT(user_id, project_id, key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
           (user_id, project, key, value, time.time()))
    return {"key": key, "value": value}


def forget(db, user_id, project, key):
    project = _module(project)
    return bool(db.change("DELETE FROM user_memory WHERE user_id = ? AND project_id = ? AND key = ?", (user_id, project, clean_key(key))))


def entries(db, user_id, project):
    """The module's entries, by key. None outside a module."""
    if not project:
        return []
    return db.all("SELECT key, value, updated FROM user_memory WHERE user_id = ? AND project_id = ? ORDER BY key", (user_id, int(project)))


def recall(db, user_id, project, query=""):
    words = str(query or "").lower().split()
    return [e for e in entries(db, user_id, project) if all(w in (e["key"] + " " + e["value"]).lower() for w in words)]


def digest(db, user_id, project):
    """The module's memory as it goes with a message: one "key: value" line each, newest kept when it is long. "" outside
    a module."""
    rows = sorted(entries(db, user_id, project), key=lambda e: -e["updated"])
    lines, size = [], 0
    for row in rows:
        line = "{}: {}".format(row["key"], row["value"])
        if size + len(line) > DIGEST_CHARS:
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(sorted(lines))


def used_in(reply, known):
    """(the reply without its "[from memory: ...]" line, the keys it names that the user's memory has)."""
    found = USED.search(reply or "")
    if not found:
        return reply, []
    keys = [k.strip().lower() for k in found.group(1).split(",") if k.strip()]
    return reply[:found.start()].rstrip(), [k for k in dict.fromkeys(keys) if k in known]


RULES = """Memory (what you know of this user in this module, and in no other; it is in "Memory" in the message):
- It fills gaps; it never overrides. What wins, in order: this message and what is attached to it, the rules of a skill
  in use, the module's facts (NeuralCore and its state), then memory, then your own defaults. When an entry goes
  against a skill's rule, follow the skill and ask in one line whether to use their saved preference instead.
- Use it out loud and naturally when it drives a choice ("portrait, as you make Reels", "wide shots, as you prefer"),
  never saying "memory" or that you remembered.
- The memory tool: "op" "remember" with "path" the key and "value" what to keep, when the user states a preference,
  corrects you, or keeps using one thing (a voice, a character, a logo: keep its id, never a copy); "recall" with
  "value" words to look for, when the digest is not enough; "forget" with "path", when they ask you to drop something
  or push back on a choice an entry made ("why is the hair different?"): forget it, then do it their way. Keys:
  pref.<name> for a preference or a correction, ptr.<name> for what they keep using, note.<name> for a lesson in your
  own words, profile.<name> for who they are and what they make. Keep what they said or used, never a guess, never a
  fact of the story (that goes in NeuralCore) and never a look meant for one film as if it were how they always work.
  It is this module's alone: another module of the project, or another project, has its own and cannot read this one.
- When any entry shaped what you did or said, end "reply" with one line exactly like [from memory: pref.framing,
  profile.use_case], naming every key that applied, copied exactly as the Memory shows it, nothing after it. Leave
  the line out when none applied."""
