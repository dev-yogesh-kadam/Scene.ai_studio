"""Prompt guides: how each model wants its prompt written, one Markdown file per model family in prompters/.

A guide starts with a few "key: value" lines and a line of three dashes, like a skill:

    id: flux2
    title: FLUX.2
    workflows: ^image/image_t2i_flux2_
    length: 40 to 150 words
    limit: 300
    ---
    The structure and the rules, in plain words.

"length" is what the agent aims for; "limit" the most words the model reads well (its text encoder loses the rest, or
blurs it): a step whose prompt is longer goes back to the agent to be shortened (agent.too_long). "workflows" is a regular expression on workflow ids ("image/image_t2i_flux2_dev"); the first file in name order that
matches a workflow is its guide. The agent is told each offered workflow's guide id ("prompt_guide") and given the
guides of the workflows it is offered, each once; a step's prompt follows its workflow's guide, which wins over the
studio's general prompt structure (agent.STRUCTURE_GUIDE). The files are read on every message, so a change counts at
once.
"""

import re
from pathlib import Path

from . import skills

FOLDER = Path(__file__).parent / "prompters"


def load(folder=FOLDER):
    """Every guide: [{"id", "title", "length", "limit" (words, 0 for none), "workflows" (a compiled pattern), "text"}],
    in file-name order. A guide whose "workflows" can't be read is left out rather than breaking the agent."""
    found = []
    for path in sorted(Path(folder).glob("*.md")):
        meta, text = skills.parse(path.read_text(encoding="utf-8"))
        try:
            pattern = re.compile(meta.get("workflows") or r"(?!)")
        except re.error:
            continue
        limit = meta.get("limit") or ""
        found.append({"id": meta.get("id") or path.stem, "title": meta.get("title") or path.stem, "length": meta.get("length") or "",
                      "limit": int(limit) if limit.isdigit() else 0, "workflows": pattern, "text": text})
    return found


def for_workflow(workflow_id, guides=None):
    """The guide of one workflow, or None when no guide is for it."""
    return next((g for g in (load() if guides is None else guides) if g["workflows"].search(str(workflow_id or ""))), None)


def part(workflow_ids, folder=FOLDER):
    """The guides of these workflows as one text for the model, each guide once with the workflows it is for; "" when
    none of them has one."""
    guides = load(folder)
    used = {}
    for wid in workflow_ids:
        guide = for_workflow(wid, guides)
        if guide:
            used.setdefault(guide["id"], (guide, []))[1].append(wid)
    return "\n\n".join("{} (prompt_guide {}; for {}; length: {}{}):\n{}".format(
        g["title"], g["id"], ", ".join(ids), g["length"] or "as the shot needs",
        "; never more than {} words".format(g["limit"]) if g["limit"] else "", g["text"]) for g, ids in used.values())


def words(text):
    """The words of a prompt, as the limits count them."""
    return len(str(text or "").split())
