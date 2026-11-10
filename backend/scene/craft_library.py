"""The creative director's library (docs/creative-director.md): short craft notes (craft/*.md) the agent finds with the
craft_search tool, and gold examples (gold/*.json) of strong work, the two closest of which go with a big job's message.

A craft note is a Markdown file with a header of "key: value" lines and a line of three dashes, as a skill's:

    id: social-hooks
    title: Hooks for social video (Reels, Shorts, TikTok)
    tags: hook, social, reels, ...
    when: one line on when the note applies
    ---
    the note

A gold example is one JSON object: {"id", "status", "brief", "context": {"platform", "audience"}, "concept",
"plan_outline": [one line a shot], "why": [the craft reasons], "tags"}. "status" is "draft" (written, waiting for a human
creative's review), "approved" or "rejected". Drafts and approved ones are used; a rejected one never is. Candidates
the harvest finds (evals/harvest.py) wait in gold/candidates/ and are never read here: a human moves them over.

Ranking is BM25 over a note's words, its title, tags and "when" counting more, in Python, with no other service. The
files are read on every call, so a change to one counts at once."""

import json
import math
import re
from pathlib import Path

from . import skills

NOTES = Path(__file__).parent / "craft"
GOLD = Path(__file__).parent / "gold"
USED = ("approved", "draft")   # the gold examples' statuses that are used; "rejected" never is
MOST_NOTES = 3     # craft_search gives at most this many notes
CLOSE = 0.5        # ...each scoring at least this share of the best one
EXAMPLES = 2       # the gold examples a big job's message carries
WEIGHTS = {"title": 3.0, "tags": 3.0, "when": 2.0, "text": 1.0}   # how much a word counts in each part
K1, B = 1.4, 0.75
STOP = frozenset("""a an and are as at be but by for from has have i in is it its me my of on or our so that the their this
to us we with you your make made want need please can could would should some something just about into than then
keep keeps get gets look like good really very one do does done how what why when which who will all any also not""".split())
WORD = re.compile(r"\w+", re.UNICODE)


def stem(w):
    """A word cut to a rough root, so "breaking", "breaks" and "break" meet: an English -ing, -ed or plural -s off."""
    for end in ("ing", "ed"):
        if len(w) > len(end) + 3 and w.endswith(end):
            return w[:-len(end)]
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def words(text):
    """The words of a text for ranking: lower-cased, no stop words, each cut to its rough root (stem)."""
    return [stem(w) for w in WORD.findall(str(text or "").lower()) if w not in STOP and len(w) > 1]


def _tags(value):
    if isinstance(value, list):
        return [str(t).strip().lower() for t in value if str(t).strip()]
    return [t.strip().lower() for t in str(value or "").split(",") if t.strip()]


# ---------------------------------------------------------------- craft notes

def notes(folder=NOTES):
    """Every craft note: [{"id", "title", "tags", "when", "text"}], in file-name order."""
    found = []
    for path in sorted(Path(folder).glob("*.md")):
        meta, text = skills.parse(path.read_text(encoding="utf-8"))
        found.append({"id": meta.get("id") or path.stem, "title": meta.get("title") or path.stem, "tags": _tags(meta.get("tags")),
                      "when": " ".join(str(meta.get("when") or "").split()), "text": text})
    return found


def _fields(note):
    return {"title": words(note.get("title")), "tags": words(" ".join(note.get("tags") or [])),
            "when": words(note.get("when")), "text": words(note.get("text") or note.get("body") or "")}


def rank(query, documents, tags=()):
    """[(score, document)] best first, of the documents with any word of the query (or any of `tags`) in them. BM25 over
    each document's parts (WEIGHTS), its tags' words counting as tags."""
    asked = words(query) + words(" ".join(tags or []))
    if not asked or not documents:
        return []
    parts = [_fields(d) for d in documents]
    lengths = [sum(len(p[f]) * w for f, w in WEIGHTS.items()) for p in parts]
    mean = sum(lengths) / len(lengths) or 1.0
    n = len(documents)
    scored = []
    for document, fields, length in zip(documents, parts, lengths):
        score = 0.0
        for term in dict.fromkeys(asked):
            has = sum(1 for p in parts if any(term in p[f] for f in WEIGHTS))
            idf = math.log(1 + (n - has + 0.5) / (has + 0.5))
            tf = sum(fields[f].count(term) * w for f, w in WEIGHTS.items())
            if tf:
                score += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / mean))
        if score > 0:
            scored.append((round(score, 4), document))
    return sorted(scored, key=lambda pair: -pair[0])


def search(query, tags=(), most=MOST_NOTES, folder=NOTES):
    """The craft notes that fit best: at most `most`, each scoring at least CLOSE of the best one."""
    ranked = rank(query, notes(folder), tags)
    if not ranked:
        return []
    best = ranked[0][0]
    return [note for score, note in ranked[:most] if score >= best * CLOSE]


def best(query, folder=NOTES):
    """The one note that fits best, or None."""
    found = search(query, (), 1, folder)
    return found[0] if found else None


def note_text(note):
    return "Craft note {} ({}). When: {}\n\n{}".format(note["id"], note["title"], note["when"], note["text"])


def for_tool(query, tags=(), folder=NOTES):
    """What craft_search gives the model: the notes that fit, whole, best first; or what to search instead."""
    found = search(query, tags, MOST_NOTES, folder)
    if not found:
        return "No craft note fits “{}”. The notes: {}.".format(" ".join(str(query or "").split())[:80], ", ".join(
            "{} ({})".format(n["id"], n["title"]) for n in notes(folder)))
    return "\n\n---\n\n".join(note_text(n) for n in found)


def pointer(query, folder=NOTES):
    """The line a big job's message carries about the note that fits it best ("" when none does)."""
    note = best(query, folder)
    if not note:
        return ""
    return "Craft note that fits this job: {} ({}). When: {} Read it with craft_search when it helps.".format(
        note["id"], note["title"], note["when"])


# ---------------------------------------------------------------- gold examples

def examples(folder=GOLD, statuses=USED):
    """The gold examples of the given statuses, in file-name order. A file that cannot be read is left out."""
    found = []
    for path in sorted(Path(folder).glob("*.json")):
        try:
            example = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(example, dict) and example.get("status") in statuses and example.get("brief"):
            found.append(example)
    return found


def _as_document(example):
    context = example.get("context") or {}
    return {"id": example.get("id"), "title": example.get("brief"), "tags": _tags(example.get("tags")),
            "when": "{} {}".format(context.get("platform") or "", context.get("audience") or ""),
            "text": "{} {} {}".format(example.get("concept") or "", " ".join(example.get("plan_outline") or []),
                                     " ".join(example.get("why") or [])),
            "example": example}


def closest(query, most=EXAMPLES, folder=GOLD):
    """The `most` gold examples nearest a message (BM25 over their brief, tags, context and plan)."""
    return [d["example"] for _, d in rank(query, [_as_document(e) for e in examples(folder)])[:most]]


def example_text(example):
    context = example.get("context") or {}
    return "\n".join(["Brief: {}".format(example.get("brief")),
                      "Context: {}; for {}".format(context.get("platform") or "-", context.get("audience") or "-"),
                      "Concept: {}".format(example.get("concept")),
                      "Plan outline:", *("  " + line for line in example.get("plan_outline") or []),
                      "Why it works:", *("  - " + line for line in example.get("why") or [])])


def examples_part(query, most=EXAMPLES, folder=GOLD):
    """The examples a big job's message carries, or "" when none fits."""
    found = closest(query, most, folder)
    if not found:
        return ""
    return EXAMPLES_HEAD + "\n\n".join(example_text(e) for e in found)


EXAMPLES_HEAD = "Examples of strong work (adapt, never copy):\n"

RULES = """Craft library: craft_search finds the studio's craft notes, each short and practical: hooks for social video, ad
structures, shot grammar and coverage, screen direction and continuity, camera moves, lighting, colour and grading,
pacing and cutting to music, genre conventions, product hero shots, character consistency, typography and motion
graphics, aspect ratios and platform specs, and what the image and video models do badly with the workarounds. Search
it with the words of the job ("cafe ad reels hook") when the work leans on a craft you have not used in this
conversation, before a big job's plan, and whenever a shot keeps failing; take what serves this piece's idea, never as a
checklist. A big job's message may name the note that fits it best ("Craft note that fits this job").
A big job's message may also carry "Examples of strong work (adapt, never copy)": briefs a senior creative answered
well, each with its concept, an outline of its shots and why it works. They show the standard and the thinking; learn
from how they move from intent to one idea to shots. Never copy their concept, their words or their shots: this brief,
this audience and this user's material decide."""
