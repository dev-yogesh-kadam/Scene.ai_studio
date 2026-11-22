"""Skills: how the agent does one kind of work (a short film, an ad, a character sheet), written as text, not code.

Each skill is a Markdown file in skills/ that starts with a few "key: value" lines and a line of three dashes:

    id: short-film
    title: A short film or a story
    version: 1
    words: \\b(film|story|scene)\\b
    ---
    The steps, in plain words.

A skill is given to the agent only when the user picks it (/<id>, or the panel), the run already follows it, or the
skill in use hands on to it or calls for it. A message that asks for a video, with no skill picked, gets the default
skill (DEFAULT, story-to-screen), which hands on to the craft skills. "words" is a regular expression: the user naming
a skill in words ("use the director skill") is found by it, and the console keeps it. The files are read on every
message, so a change to one counts at once.

Three more keys a skill may have:

    next: director, sound-pass     the skills it hands on to when its own steps are done (read_skill loads them)
    craft: true                    a craft skill (directing, coverage, continuity, the sound pass): never picked by its
                                   words alone, only loaded by a skill that names it, or by the user with /<id>
    auto: story                    loaded on its own for multi-shot film and story work (wants_directing): the
                                   director, beside whatever else the message has. Never for a single shot, an edit or
                                   motion graphics, and never beside a long skill the user named (that skill calls it)

A skill drafted in a chat ("make this a skill", skill_draft) waits in skills/drafts/ until an admin publishes it: the
agent never reads a draft.
"""

import re
import time
from pathlib import Path

FOLDER = Path(__file__).parent / "skills"
DRAFTS = "drafts"   # the folder under FOLDER where drafts wait for an admin
MAX_CHARS = 150_000   # the most of one skill that goes to a hosted model (about 40,000 tokens); a longer one is cut here, and the agent says so
DEFAULT = "story-to-screen"   # the skill of a message that asks for a video when the user picked none
# A message that asks for a video to be made: a verb of making, then within a few words a video, film, reel... that is
# not one already there ("make the video shorter" is an edit, not a new video).
MAKES_VIDEO = re.compile(
    r"\bscript[- ]to[- ]video\b"
    r"|\b(make|making|create|creating|generate|produce|shoot|build|turn|convert|animate|want|need|like|do)\b[^.?!\n]{0,60}?"
    r"(?<!\bthis )(?<!\bthat )(?<!\bthe )(?<!\bthese )(?<!\bthose )(?<!\bit )(?<!\bmy )"
    r"\b(video|videos|film|films|movie|movies|reel|reels|animation|cartoon|episode|trailer|short film)\b",
    re.IGNORECASE)
# ...said as a request now: an order ("make…", also after a comma: "here is my script, turn it…"), or "can you",
# "please", "I want", "let's"...
REQUEST = re.compile(
    r"(^|[.,;:!?\n]\s*)(please\s+)?(make|create|generate|produce|shoot|build|turn|convert|animate|do|direct)\b"
    r"|\bscript[- ]to[- ]video\b|\b(can|could|would|will) you\b|\bplease\b|\b(i|we) (want|need)\b|\b(i|we)('d| would) like\b"
    r"|\blet'?s\b|\bhelp me\b|\bi'?m (trying|looking) to\b",
    re.IGNORECASE)
# ...not what the user does as a rule, or did ("I always make Reels", "I made a film last week")
HABIT = re.compile(r"\b(i|we)\s+(always|usually|often|sometimes|never|generally|normally|mostly|typically|mainly)\b"
                   r"|\b(i|we)\s*('ve| have)?\s+(made|created|shot|produced)\b", re.IGNORECASE)
# ...and more than one clip: a length of a clip at most (15 s), or "a clip" / "one shot", is made without the skill
ONE_CLIP_SECONDS = 15
SECONDS = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*-?\s*(s|sec|secs|second|seconds)\b", re.IGNORECASE)
ONE_CLIP = re.compile(r"\b(a|one|single|quick|short) (short |quick |little )?(clip|shot)\b", re.IGNORECASE)
LONGER = re.compile(r"\b(minutes?|mins?|scenes|episodes?|story|script|series|several|many)\b", re.IGNORECASE)
MATERIAL = ("audio", "text")   # an attached sound or script: the work of this skill, whatever the length said
# ...and not a video of words and shapes: motion graphics are pages the agent designs (the render_html tool), not a
# film of shots made from a script.
MOTION_DEFAULT = "brand-motion"   # the skill of a message that asks for a brand's motion graphics, when the user picked none
# A message that asks for a brand's motion graphics: a logo reveal, an ident, a brand reel, a promo, a teaser, an
# explainer of words and shapes, anything made "with HyperFrames".
BRAND_MOTION = re.compile(
    r"\bhyper\s?frames?\b|\bmotion[- ]?graphic\w*|\blogo (reveal|animation|intro|outro|sting|build)s?\b"
    r"|\b(animate|animated) (the |our |my |a )?logo\b|\b(ident|sting|sizzle( reel)?|brand (reel|video|film|promo|teaser|story))s?\b"
    r"|\b(launch|product|app|service) (teaser|promo|video)s?\b|\bteaser\b|\bpromo\b|\b(services?|product) explainer\b"
    r"|\bexplainer (video|animation)\b",
    re.IGNORECASE)
MOTION_GRAPHICS = re.compile(
    r"\bhyper\s?frames?\b|\bmotion[- ]?graphic\w*|\bkinetic (type|typography|text)\b|\btypograph\w* (video|animation)\b"
    r"|\b(animated|moving) (text|titles?|typography|infographics?|charts?)\b|\btext animation\b|\btitle (card|sequence)s?\b"
    r"|\blower[- ]thirds?\b|\blyric video\b|\binfographic (video|animation)\b|\bexplainer (animation|motion)\b|\bhtml\b",
    re.IGNORECASE)


def _pairs(block):
    """The "key: value" lines of a header, keys lower-cased, values without the quotes a YAML header puts round them."""
    meta = {}
    for line in block.splitlines():
        key, colon, value = line.partition(":")
        if colon and key.strip() and " " not in key.strip():
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            meta[key.strip().lower()] = value
    return meta


def parse(raw):
    """A skill file as (meta, steps). The header is "key: value" lines, then a line of three dashes. Skills written for
    other tools come as a YAML header between two lines of dashes, sometimes twice in a row; every header is read, the
    first value of a key wins (name, label, description, user_description are understood as id, title and desc)."""
    text = raw.replace("\r\n", "\n").lstrip("\ufeff")
    meta = {}
    if text.startswith("---\n"):
        text = text[4:]
    head, sep, rest = text.partition("\n---\n")
    if sep and all(":" in line or not line.strip() for line in head.splitlines()):
        meta = _pairs(head)
        text = rest
    elif not sep:
        return {}, text.strip()
    # more headers straight after the first (a nested "---" block), or a lone separator
    while True:
        text = text.lstrip("\n")
        if text.startswith("---\n"):
            body = text[4:]
            block, sep, rest = body.partition("\n---\n")
            if sep and all(":" in line or not line.strip() for line in block.splitlines()) and block.strip():
                for key, value in _pairs(block).items():
                    meta.setdefault(key, value)
                text = rest
                continue
            text = body
            continue
        break
    return meta, text.strip()


QUOTED = re.compile(r"[\"“]([^\"”]{4,60})[\"”]")


def triggers_from(description):
    """A pattern for the phrases a description puts in quotes ('when the user says "pocket motion v2"'), or "" when it has none."""
    phrases = []
    for phrase in QUOTED.findall(description or ""):
        phrase = " ".join(phrase.split()).strip(" .")
        if len(phrase.split()) >= 2 and phrase.lower() not in (p.lower() for p in phrases):
            phrases.append(phrase)
    return r"\b(" + "|".join(r"\s+".join(re.escape(w) for w in p.split()) for p in phrases) + r")\b" if phrases else ""


def _short(text, limit=160):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:. ") + "…"


def ids_in(value):
    """The skill ids of a "next:" line ("director, sound-pass"), in order, each once."""
    return list(dict.fromkeys(w for w in re.split(r"[\s,;]+", str(value or "").lower()) if SLUG.match(w)))


def is_on(value):
    return str(value or "").strip().lower() in ("true", "yes", "1", "on")


def load(folder=FOLDER):
    """Every skill in the folder: [{"id", "title", "version", "desc", "words", "text", "next", "craft"}], in file-name
    order. A draft (in DRAFTS) is not one of them."""
    found = []
    for path in sorted(Path(folder).glob("*.md")):
        meta, text = parse(path.read_text(encoding="utf-8"))
        slug = re.sub(r"[^a-z0-9]+", "-", (meta.get("id") or meta.get("name") or path.stem).lower()).strip("-") or path.stem
        title = meta.get("title") or meta.get("label") or path.stem
        if title == slug and meta.get("label"):
            title = meta["label"]
        pattern = meta.get("words") or ""
        if not pattern.strip() or pattern.strip() == "(?!)":
            pattern = triggers_from(meta.get("description") or "")   # a skill that says when it applies, in quotes, is found by those words
        try:
            words = re.compile(pattern or r"(?!)", re.IGNORECASE)
        except re.error:
            continue   # a skill whose words can't be read is left out rather than breaking the agent
        found.append({"id": slug, "title": title, "version": meta.get("version") or "1",
                      "desc": meta.get("desc") or _short(meta.get("user_description") or meta.get("description")), "words": words, "text": text,
                      "next": [n for n in ids_in(meta.get("next")) if n != slug], "craft": is_on(meta.get("craft")),
                      "guide": is_on(meta.get("guide")), "loads_for": str(meta.get("auto") or "").strip().lower()})
    return found


CRAFT_PREFIX = "craft-"   # how the skills once named each other ("craft-director"): read as the id after it
# The skills renamed on 2026-11-22 (docs/skill-names.md), old id -> new id, so a run, a saved pick or a typed /command
# from before still finds its skill.
RENAMED = {"script-to-video": "story-to-screen", "script-writer": "narrative", "asset-designer": "look-book",
           "director": "shot-planner", "anchor": "blocking", "continuity-board": "still-grid",
           "continuity-chain": "clip-relay", "continuity-recall": "callback-frames",
           "prompter-seedance-2": "seedance-2-shots", "prompter-seedance-2-5": "seedance-2-5-shots",
           "prompter-wan-3": "wan-3-shots", "prompter-minimax-h3": "minimax-h3-shots"}


def find(skill_id, folder=FOLDER):
    """The one skill with this id, or None. Used when the user asks for a skill by name with /<id>. An old name
    ("director", "craft-director": RENAMED) finds the skill it became when no skill has that whole name."""
    found = load(folder)
    for wanted in (skill_id, canonical(skill_id)):
        for skill in found:
            if skill["id"] == wanted:
                return skill
    return None


def canonical(skill_id):
    """A skill's id as this studio names it now: "craft-anchor" and "anchor" are "blocking" (RENAMED)."""
    said = str(skill_id or "").strip().lower()
    said = said[len(CRAFT_PREFIX):] if said.startswith(CRAFT_PREFIX) else said
    return RENAMED.get(said, said)


SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _line(value):
    """A header value kept to one line: newlines would break the "key: value" format."""
    return " ".join(str(value or "").split())


def save(meta, folder=FOLDER):
    """Write a skill file from fields (id, title, desc, version, words, text, and next and craft) and return the saved
    skill. Admin only (the caller checks). Raises ValueError on a bad id or a words pattern that is not a valid regular
    expression. A skill saved again without "next" or "craft" (the console's form has neither) keeps the ones it had."""
    sid = _line(meta.get("id")).lower()
    if not SLUG.match(sid):
        raise ValueError("The id must be lower-case letters, numbers and hyphens, and start with a letter or number.")
    words = _line(meta.get("words"))
    try:
        re.compile(words or r"(?!)", re.IGNORECASE)
    except re.error as err:
        raise ValueError("The trigger words are not a valid regular expression: {}".format(err))
    head = "id: {}\ntitle: {}\n".format(sid, _line(meta.get("title")) or sid)
    desc = _line(meta.get("desc"))
    if desc:
        head += "desc: {}\n".format(desc)
    head += "version: {}\nwords: {}\n".format(_line(meta.get("version")) or "1", words)
    before = find(sid, folder) or {}
    given = meta.get("next")
    after = ids_in(", ".join(given) if isinstance(given, list) else given if isinstance(given, str) else ", ".join(before.get("next") or []))
    if after:
        head += "next: {}\n".format(", ".join(after))
    if is_on(meta["craft"]) if "craft" in meta else before.get("craft"):
        head += "craft: true\n"
    if before.get("loads_for"):   # the console's form has no "auto": a skill saved again keeps it
        head += "auto: {}\n".format(before["loads_for"])
    path = Path(folder) / (sid + ".md")
    path.write_text(head + "---\n" + str(meta.get("text") or "").strip() + "\n", encoding="utf-8")
    return find(sid, folder)


def remove(skill_id, folder=FOLDER):
    """Delete a skill file. Returns True when one was there to delete."""
    if not SLUG.match(_line(skill_id)):
        return False
    path = Path(folder) / (_line(skill_id) + ".md")
    if path.is_file():
        path.unlink()
        return True
    return False


def pick(instruction, history=(), folder=FOLDER, force=()):
    """The skills of a message: the ones the user chose (`force`: from a /command, the panel, or the run's own skill),
    in that order. A message's words never pick a skill.

    `instruction` and `history` are kept for the callers; the default skill is wants_video()'s to decide."""
    found = {s["id"]: s for s in load(folder)}
    named = [i if i in found else canonical(i) for i in force or []]
    chosen = [found[i] for i in dict.fromkeys(named) if i in found]
    # the one exception to "only the user picks": a skill marked "auto: story" (the director) comes on its own for
    # multi-shot film and story work, marked "auto" so the route treats it as a craft beside the work, never a run's skill
    if wants_directing(instruction, history):
        chosen += [dict(s, auto=True) for s in found.values() if s.get("loads_for") == "story" and s["id"] not in named]
    return chosen


# Multi-shot film and story work, which the director plans (wants_directing): a story, a script, a scene of several
# shots, a short film, a music video, a shot list...
STORY = re.compile(
    r"\b(story|stories|script|screenplay|short film|film|movie|episode|drama|music video|trailer|scenes|shot list|"
    r"storyboard|direct(ing)? (this|the|my|it|a)|plan the shots|break (it|this|the script) down|breakdown|narrative)\b",
    re.IGNORECASE)
# ...not work on what is there already: an edit, a retake, a new shape, captions
EDITING = re.compile(r"\b(trim|split|cut (it|this|the)|join|merge|shorten|halve|retake|upscale|reframe|crop|subtitles?|"
                     r"captions?|lip ?sync)\b", re.IGNORECASE)
ONE_SHOT = re.compile(r"\b(a|one|single) (single |quick |short )?(shot|still|picture|image|photo|frame)\b", re.IGNORECASE)


def wants_directing(instruction, history=()):
    """Whether a message is multi-shot film or story work, which the director skill plans: a story, a script, a short
    film, a scene of several shots (STORY), and not a single shot (a clip of 15 s at most, "one shot", "a picture"), an
    edit of what exists (EDITING) or motion graphics. A short follow-up is about the work of the message before."""
    said = str(instruction or "")
    last = history[-1] if isinstance(history, list) and history and isinstance(history[-1], dict) else {}
    if len(said) < 60 and last.get("instruction"):
        said += "\n" + str(last["instruction"])
    if not STORY.search(said) or HABIT.search(said) or MOTION_GRAPHICS.search(said) or BRAND_MOTION.search(said):
        return False
    if EDITING.search(str(instruction or "")):
        return False
    lengths = [float(n) for n, _ in SECONDS.findall(said)]
    single = (lengths and max(lengths) <= ONE_CLIP_SECONDS) or ONE_CLIP.search(said) or ONE_SHOT.search(said)
    return not (single and not LONGER.search(said))


def wants_motion(instruction, history=()):
    """Whether a message asks for a brand's motion graphics to be made now (BRAND_MOTION, as a request), so the
    default motion skill runs when the user picked none. A short follow-up is about the work of the message before."""
    said = str(instruction or "")
    last = history[-1] if isinstance(history, list) and history and isinstance(history[-1], dict) else {}
    if len(said) < 60 and last.get("instruction"):
        said += "\n" + str(last["instruction"])
    return bool(BRAND_MOTION.search(said)) and not HABIT.search(said) and bool(REQUEST.search(said) or MAKES_VIDEO.search(said))


def wants_video(instruction, history=(), attached=()):
    """Whether a message asks for a film to be made now, so the default skill runs when the user picked none: a video
    asked for, as a request, not a habit, and more than one clip. attached: the kinds of the files attached ("audio",
    "text", "image"...); a sound or a script attached makes it a request for the skill's work, at any length said.
    A short follow-up ("yes, portrait") is about the same work as the message before it, so that message counts too."""
    said = str(instruction or "")
    last = history[-1] if isinstance(history, list) and history and isinstance(history[-1], dict) else {}
    if len(said) < 60 and last.get("instruction"):
        said += "\n" + str(last["instruction"])
    if not MAKES_VIDEO.search(said) or HABIT.search(said) or MOTION_GRAPHICS.search(said) or BRAND_MOTION.search(said):
        return False
    if any(kind in MATERIAL for kind in attached or ()):
        return True
    if not REQUEST.search(said):
        return False
    lengths = [float(n) for n, _ in SECONDS.findall(said)]
    one_clip = (lengths and max(lengths) <= ONE_CLIP_SECONDS) or ONE_CLIP.search(said)
    return not (one_clip and not LONGER.search(said))


PART = re.compile(r"(?m)^#{2,3} \S")   # a part of a skill begins at a heading of the second or third level
PAGE = 39_000                          # characters of a part read at a time: one read fits in read_skill's result (agent.SKILL_RESULT)
READ_WHOLE = 39_000                    # a skill read_skill gives comes whole up to this, in one result; a longer one as its opening and parts
OPENING_SHARE = 0.75                   # of the room a model has for a skill, what its opening may take


def parts(text):
    """A skill as its parts: [(heading, text)], the opening first (heading "", everything before the first ## heading)."""
    starts = [m.start() for m in PART.finditer(text)]
    if not starts or starts[0] > 0:
        starts = [0] + starts
    found = []
    for a, b in zip(starts, starts[1:] + [len(text)]):
        chunk = text[a:b].strip("\n")
        heading = chunk.splitlines()[0].lstrip("#").strip() if PART.match(chunk) else ""
        found.append((heading, chunk))
    return found


def catalogue(given=(), folder=FOLDER):
    """Every skill not given with this message, one line each ("id: when to use it"), for the agent to load with
    read_skill when the message fits one the words did not find. A craft skill is marked so: it is loaded for a skill in
    use that calls for it, or when the user asks for exactly that work, never because a message's words fit it."""
    taken = {s["id"] for s in given}
    return "\n".join("- {}{}: {}".format(s["id"], " (craft: for a skill in use that calls for it, or when the user asks for exactly this)"
                                         if s["craft"] else "", s["desc"] or s["title"]) for s in load(folder) if s["id"] not in taken)


def hand_off(skill):
    """The line that ends a skill which names the skills after it, or ""."""
    if not skill.get("next"):
        return ""
    return ("[When this skill's own steps are done, hand on to {}: load it with read_skill (op its id, query 0) and follow it "
            "from its first step. Say so to the user in one line.]").format(" then ".join(skill["next"]))


def guide(picked, limit=MAX_CHARS):
    """The picked skills as one text for the model, or "" when none fits. A skill longer than `limit` characters is never
    cut: the model is given its opening and a list of its parts, and reads each part with the read_skill tool when it comes
    to it (read_part). limit None: every skill whole."""
    out = []
    for s in picked:
        text = s["text"]
        if limit is not None and len(text) > limit:
            text = outline(s, limit)
        ending = hand_off(s)
        out.append("{} (skill {} v{}):\n{}{}".format(s["title"], s["id"], s["version"], text, "\n" + ending if ending else ""))
    return "\n\n".join(out)


def outline(skill, limit):
    """A long skill as a model with `limit` characters of room is given it: its opening (whole, or as much as fits, the
    rest to be read as part 0), then every part by number, heading and size."""
    found = parts(skill["text"])
    opening = found[0][1] if not found[0][0] else ""
    room = int(limit * OPENING_SHARE)
    shown = opening if len(opening) <= room else opening[:room].rsplit("\n", 1)[0]
    listed = ["  {}. {} ({:,} characters)".format(n, heading or "The opening, continued", len(chunk))
              for n, (heading, chunk) in enumerate(found) if heading or len(opening) > room]
    return "{}\n\n[This skill is {:,} characters, more than you are given at once, so above is its opening and below its parts. " \
           "Read each part with read_skill (op: \"{}\", query: its number or heading) when you come to that step, before you act on " \
           "it; a long part comes a page at a time. Never guess a part you have not read.]\nParts:\n{}".format(
               shown, len(skill["text"]), skill["id"], "\n".join(listed))


def read_part(skill, query, offset=0):
    """One part of a skill, by its number (0 is the opening) or words of its heading, a page at a time from `offset`.
    Returns (text, None) or (None, why not)."""
    found = parts(skill["text"])
    query = " ".join(str(query or "").split()).lower()
    pick = None
    if query.isdigit() and int(query) < len(found):
        pick = int(query)
    elif query:
        pick = next((n for n, (heading, _) in enumerate(found) if heading and query in heading.lower()), None)
        if pick is None:   # "5" for "## 5 — Generate", or the heading's first words
            pick = next((n for n, (heading, _) in enumerate(found) if heading and heading.lower().split(" ")[0].strip(".") == query), None)
    if pick is None:
        return None, "No part of “{}” is called “{}”. Its parts: {}.".format(
            skill["title"], query, "; ".join("{} {}".format(n, h or "the opening") for n, (h, _) in enumerate(found)))
    heading, chunk = found[pick]
    offset = max(0, int(offset or 0))
    page = chunk[offset:offset + PAGE]
    more = "" if offset + len(page) >= len(chunk) else "\n[{:,} of {:,} characters of this part: read_skill again with offset {}.]".format(
        offset + len(page), len(chunk), offset + len(page))
    return page + more, None


# ---------------------------------------------------------------- drafts: skills written in a chat, for an admin to publish

DRAFT_CHARS = 60_000   # the most of a draft's steps that is kept


def _drafts(folder):
    return Path(folder) / DRAFTS


def slug_of(title):
    """A skill id made from a title ("Hindi wedding reel" -> "hindi-wedding-reel")."""
    return re.sub(r"[^a-z0-9]+", "-", str(title or "").lower()).strip("-")[:48].strip("-")


def save_draft(fields, by, folder=FOLDER):
    """Keep a skill drafted in a chat: fields {"id"?, "title", "desc" (when to use it), "text" (the steps), "words"?}.
    by: {"id", "name"} of who drafted it. A draft never replaces a skill or another draft: its id gets a number.
    Returns the draft as drafts() lists it. Raises ValueError when there is no title or no steps."""
    title, text = _line(fields.get("title"))[:120], str(fields.get("text") or "").strip()[:DRAFT_CHARS]
    if not title or not text:
        raise ValueError("A draft needs a title and its steps.")
    words = _line(fields.get("words"))
    try:
        re.compile(words or r"(?!)", re.IGNORECASE)
    except re.error:
        words = ""
    base = slug_of(fields.get("id") or title) or "skill"
    if not SLUG.match(base):
        base = "skill-" + base
    place = _drafts(folder)
    place.mkdir(parents=True, exist_ok=True)
    sid, n = base, 1
    while find(sid, folder) or (place / (sid + ".md")).is_file():
        n += 1
        sid = "{}-{}".format(base, n)
    head = "id: {}\ntitle: {}\ndesc: {}\nversion: 1\nwords: {}\ndrafted_by: {}\ndrafted_by_name: {}\ndrafted: {}\n".format(
        sid, title, _line(fields.get("desc"))[:300], words, int(by.get("id") or 0), _line(by.get("name"))[:80], int(time.time()))
    (place / (sid + ".md")).write_text(head + "---\n" + text + "\n", encoding="utf-8")
    return next(d for d in drafts(folder) if d["id"] == sid)


def _number(value):
    return int(value) if str(value or "").isdigit() else 0


def drafts(folder=FOLDER):
    """The skills drafted in chats, waiting: [{"id", "title", "desc", "words", "text", "by", "by_name", "at"}], newest first."""
    found = []
    for path in sorted(_drafts(folder).glob("*.md")) if _drafts(folder).is_dir() else []:
        meta, text = parse(path.read_text(encoding="utf-8"))
        found.append({"id": path.stem, "title": meta.get("title") or path.stem, "desc": meta.get("desc") or "",
                      "words": meta.get("words") or "", "text": text, "by": _number(meta.get("drafted_by")),
                      "by_name": meta.get("drafted_by_name") or "", "at": _number(meta.get("drafted"))})
    return sorted(found, key=lambda d: -d["at"])


def publish(draft_id, changes=None, folder=FOLDER):
    """Make a draft a skill the agent uses (admins only: the caller checks), with any changes the admin made to its
    fields. Returns the skill. Raises ValueError when there is no such draft or its id is a skill's already."""
    sid = _line(draft_id).lower()
    path = _drafts(folder) / (sid + ".md")
    if not SLUG.match(sid) or not path.is_file():
        raise ValueError("There is no draft “{}”.".format(sid))
    if find(sid, folder):
        raise ValueError("A skill with the id “{}” already exists.".format(sid))
    draft = next(d for d in drafts(folder) if d["id"] == sid)
    fields = {k: draft[k] for k in ("title", "desc", "words", "text")}
    fields.update({k: v for k, v in (changes or {}).items() if k in ("title", "desc", "words", "text", "next", "craft")})
    saved = save(dict(fields, id=sid, version="1"), folder)
    path.unlink()
    return saved


def discard(draft_id, folder=FOLDER):
    """Throw a draft away. Returns True when there was one."""
    sid = _line(draft_id).lower()
    path = _drafts(folder) / (sid + ".md")
    if SLUG.match(sid) and path.is_file():
        path.unlink()
        return True
    return False
