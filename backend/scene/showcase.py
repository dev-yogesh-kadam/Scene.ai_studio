"""The showcase: the best work made on the studio, picked by an admin, shown to every user on the Home page under
"Made on Scene.ai", in sections of the admin's naming (Shorts & Reels, Microdrama, Ads…).

A picked item is copied into a folder of its own (storage/showcase), so it stays when its owner deletes it, and so the
showcase never hands out a link to anyone's library. What is kept of it: its kind, a name, its section, its shape, and,
when the admin leaves it on, its prompt and the model it was made with. Not its owner, project or references.

The list is one setting, "showcase": {"sections": [...], "items": [{key, kind, name, section, ext, width, height,
duration, prompt, show_prompt, workflow, workflow_title, from, added}]}, the items in the order they are shown."""

import json
import secrets
import shutil
import time
from pathlib import Path

from . import media

SETTING = "showcase"
MAX_ITEMS = 120
MAX_SECTIONS = 12
KINDS = ("image", "video")


class ShowcaseError(ValueError):
    pass


def load(db):
    try:
        data = json.loads(db.setting(SETTING) or "{}")
    except ValueError:
        data = {}
    return {"sections": [s for s in data.get("sections") or [] if isinstance(s, str)],
            "items": [i for i in data.get("items") or [] if isinstance(i, dict) and i.get("key")]}


def save(db, data):
    db.set_setting(SETTING, json.dumps({"sections": data["sections"], "items": data["items"]}))


def path_of(folder, item):
    return Path(folder) / (item["key"] + item["ext"])


def _name(text, limit=80):
    return " ".join(str(text or "").split())[:limit]


def clean_sections(names):
    """Section names as given, each once (whatever its case), without blanks: at most MAX_SECTIONS."""
    kept, seen = [], set()
    for name in names or []:
        name = _name(name, 40)
        if name and name.lower() not in seen:
            kept.append(name)
            seen.add(name.lower())
    return kept[:MAX_SECTIONS]


def add(db, folder, row, source, section="", name=""):
    """Copy library item `row` (its file at `source`) into the showcase, at its end. Returns the new item."""
    data = load(db)
    if row["kind"] not in KINDS:
        raise ShowcaseError("Only pictures and videos go on the Home page.")
    if len(data["items"]) >= MAX_ITEMS:
        raise ShowcaseError(f"The Home page holds {MAX_ITEMS} items at most: take one out first.")
    if not Path(source).is_file():
        raise ShowcaseError("The file of this item is missing from storage.")
    section = _name(section, 40)
    if section and section.lower() not in {s.lower() for s in data["sections"]}:
        data["sections"] = clean_sections(data["sections"] + [section])
    section = next((s for s in data["sections"] if s.lower() == section.lower()), "")
    settings = json.loads(row["settings"]) if isinstance(row["settings"], str) else row["settings"] or {}
    context = json.loads(row["context"]) if isinstance(row["context"], str) else row["context"] or {}
    item = {"key": secrets.token_hex(6), "kind": row["kind"], "name": _name(name) or _name(row["name"]) or "Untitled",
            "section": section, "ext": Path(source).suffix.lower()[:8],
            "width": context.get("width"), "height": context.get("height"), "duration": context.get("duration"),
            "prompt": str(settings.get("prompt") or "")[:4000], "show_prompt": True,
            "workflow": row.get("workflow") or "", "workflow_title": settings.get("workflow_title") or "",
            "from": row["id"], "added": time.time()}
    Path(folder).mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, path_of(folder, item))
    data["items"].append(item)
    save(db, data)
    return item


def change(db, body):
    """Sections, order and each item's name, section and whether its prompt is shown. `body`: {sections: [...],
    items: [{key, name?, section?, show_prompt?}] in the new order}. Items left out of the list keep their place after
    the listed ones; an item whose section is gone is shown under All only."""
    data = load(db)
    if "sections" in body:
        data["sections"] = clean_sections(body.get("sections"))
    known = {s.lower(): s for s in data["sections"]}
    by_key = {i["key"]: i for i in data["items"]}
    order = []
    for wanted in body.get("items") or []:
        item = by_key.pop(str((wanted or {}).get("key")), None)
        if not item:
            continue
        if "name" in wanted and _name(wanted["name"]):
            item["name"] = _name(wanted["name"])
        if "section" in wanted:
            item["section"] = _name(wanted["section"], 40)
        if "show_prompt" in wanted:
            item["show_prompt"] = bool(wanted["show_prompt"])
        order.append(item)
    order += [i for i in data["items"] if i["key"] in by_key]
    for item in order:
        item["section"] = known.get(str(item.get("section") or "").lower(), "")
    data["items"] = order
    save(db, data)
    return data


def remove(db, folder, key):
    data = load(db)
    item = next((i for i in data["items"] if i["key"] == key), None)
    if not item:
        raise ShowcaseError("No such item on the Home page.")
    data["items"].remove(item)
    save(db, data)
    media.remove_result(path_of(folder, item))
    return item


def find(db, key):
    return next((i for i in load(db)["items"] if i["key"] == key), None)


def public(item):
    """An item as every user gets it: shaped like a library item, so the studio's viewer shows it."""
    settings = {"workflow_title": item.get("workflow_title") or ""}
    if item.get("show_prompt", True) and item.get("prompt"):
        settings["prompt"] = item["prompt"]
    return {"id": item["key"], "kind": item["kind"], "name": item["name"], "section": item.get("section") or "",
            "workflow": item.get("workflow") or "", "settings": settings, "created": item.get("added") or 0,
            "context": {k: item[k] for k in ("width", "height", "duration") if item.get(k)}}
