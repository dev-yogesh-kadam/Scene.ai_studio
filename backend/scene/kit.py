"""The kit of a project: every character, location, prop, outfit, voice, style and script it is made from, by name.

One store for what the cast and the shared memory were. Each entry is a row of `assets` with the project's id: a copy
of its file, a name, a type (the tag), what it shows (written by the agent's model looking at it, or by the user), a
note on how to use it, its place in the kit, and whether it is always on.

- An always-on entry goes into every shot of the project that has a slot meant for it (what the cast did): the
  characters in their order into the character slots, the location into the background slot, and so on.
- Every entry is known to the agent by name and id, which uses it where a shot needs it, and to the user's pickers.
- An entry attached without a name (named = 0) is one the agent asks the user about.

Entries come in from everywhere work is done: named in an agent message ("Maya - @3"), kept from what a step made
(keep_made), saved by the agent (its book_save tool), dropped into a job's reference slot (keep_upload), and added by
the user in the panel or from a result on the canvas.

A kit belongs to one project (its modules share it): nothing is kept outside a project, and nothing is shared between
projects. The assets saved before kits existed, with no project, are not used at all.
"""

import contextlib
import hashlib
import re
import time
from .db import as_everyone
from pathlib import Path

from .references import safe_name

# The types of entry, as tags (as stored) and as the user and the agent read them.
TYPES = {"character": "character", "background": "location", "outfit": "outfit", "prop": "prop", "voice": "voice",
         "style": "style", "script": "script", "other": "other"}
TAG_OF = {said: tag for tag, said in TYPES.items()}   # "location" -> "background"
NOTE_CHARS = 600
NAME_CHARS = 60
VARIANT_CHARS = 40
PALETTE_CHARS = 200
RELATION_CHARS = 30
MOST_RELATIVES = 12
# A look of an entry is named after it: "Maya - torn sleeve", "Kitchen – night" (the base, a dash, the look's words).
LOOK_NAME = re.compile(r"^(.+?)\s+[-–—]\s+(.+)$")
HAS_LOOKS = ("character", "background", "prop")   # the types whose entries have looks (a location's are its times of day)
# The other side of a relation: "Ira is Maya's mother" says that Maya is Ira's child. A relation not here is said as it is.
INVERSE = {"mother": "child", "father": "child", "parent": "child", "son": "parent", "daughter": "parent", "child": "parent",
           "brother": "sibling", "sister": "sibling", "sibling": "sibling", "twin": "twin", "cousin": "cousin",
           "grandmother": "grandchild", "grandfather": "grandchild", "grandparent": "grandchild", "grandson": "grandparent",
           "granddaughter": "grandparent", "grandchild": "grandparent", "aunt": "niece or nephew", "uncle": "niece or nephew",
           "niece": "aunt or uncle", "nephew": "aunt or uncle", "wife": "spouse", "husband": "spouse", "spouse": "spouse",
           "stepmother": "stepchild", "stepfather": "stepchild", "stepson": "step-parent", "stepdaughter": "step-parent",
           "mother-in-law": "child-in-law", "father-in-law": "child-in-law", "son-in-law": "parent-in-law",
           "daughter-in-law": "parent-in-law", "brother-in-law": "sibling-in-law", "sister-in-law": "sibling-in-law"}
IN_LAW = re.compile(r"in-law|^step|^(wife|husband|spouse)$")   # never blood, whatever is said

# What a slot of each type is called in a workflow's labels; the kind of file it takes; and what each kind of slot can be
# filled with (a video gives a picture slot its last frame, and a voice slot its sound).
SLOT_WORDS = (("character", r"character|main character|second person|\bperson\b"),
              ("background", r"background|location"),
              ("outfit", r"outfit|costume|clothing"),
              ("prop", r"\bprop\b|product"),
              ("voice", r"voice sample"),
              ("style", r"\bstyle\b"))
OTHER_ANGLE = re.compile(r"same person|another angle|other angle", re.IGNORECASE)   # a second picture of the first character
SLOT_KIND = {"voice": "audio"}
FITS = {"image": ("image", "video"), "video": ("video",), "audio": ("audio", "video")}
# How a prompt names each always-on entry, so the model ties the words to the reference instead of inventing a look.
PEOPLE = ("the main character", "the second person", "the third person", "the fourth person")
SAID_AS = {"background": "the background", "outfit": "the outfit", "prop": "the prop", "voice": "the voice", "style": "the style"}


def tag_of(said):
    """The stored tag of a type as anyone says it ("location", "Character", "background"), or "other"."""
    said = str(said or "").strip().lower()
    return said if said in TYPES else TAG_OF.get(said, "other")


def clean_name(name):
    return " ".join(str(name or "").split())[:NAME_CHARS]


def clean_note(text):
    return " ".join(str(text or "").split())[:NOTE_CHARS]


def relations_of(row):
    """An entry's relatives as stored: [{"to", "relation", "blood"}]."""
    import json
    try:
        found = json.loads(row.get("relations") or "[]")
    except ValueError:
        return []
    return [r for r in found if isinstance(r, dict) and isinstance(r.get("to"), int)] if isinstance(found, list) else []


def family(rows, asset_id):
    """The relatives of one entry among `rows` (a kit), both ways: those it names and those that name it, the latter in
    the other side's words ("Ira is Maya's mother": Maya is Ira's child). [{"entry", "name", "relation", "blood"}]."""
    by_id = {r["id"]: r for r in rows}
    me = by_id.get(asset_id)
    if me is None:
        return []
    out, seen = [], set()
    for rel in relations_of(me):
        other = by_id.get(rel["to"])
        if other and other["id"] not in seen:
            seen.add(other["id"])
            out.append({"entry": other["id"], "name": other["name"], "relation": rel["relation"], "blood": rel["blood"]})
    for other in rows:
        if other["id"] in seen or other["id"] == asset_id:
            continue
        rel = next((r for r in relations_of(other) if r["to"] == asset_id), None)
        if rel:
            seen.add(other["id"])
            out.append({"entry": other["id"], "name": other["name"], "relation": INVERSE.get(rel["relation"], "related ({} of them)".format(rel["relation"])),
                        "blood": rel["blood"]})
    return out


def looks(rows, asset_id):
    """The looks of one entry (a character's changed looks, a location's times of day), by the scene they start in."""
    return sorted((r for r in rows if r.get("look_of") == asset_id), key=lambda r: (r.get("from_scene") or 0, r["variant"]))


def _links(db, user_id, row, changes):
    """The checked link fields of `changes` for entry `row`: look_of, variant, from_scene, palette, relations.
    Raises ValueError with the reason when one is wrong."""
    import json
    fields = {}
    kit = {r["id"]: r for r in entries(db, user_id, row["project_id"])} if row.get("project_id") else {}
    if "look_of" in changes:
        base = changes["look_of"] or None
        if base is not None:
            other = kit.get(base) if isinstance(base, int) and not isinstance(base, bool) else None
            if other is None or other["id"] == row["id"]:
                raise ValueError("look_of is another entry of this project's NeuralCore.")
            if other.get("look_of"):
                raise ValueError("“{}” is itself a look; give the entry it is a look of.".format(other["name"]))
            if other["tag"] not in HAS_LOOKS:
                raise ValueError("Only a character, a location or a prop has looks.")
        fields["look_of"] = base
    if "variant" in changes:
        fields["variant"] = " ".join(str(changes["variant"] or "").split())[:VARIANT_CHARS]
    if "from_scene" in changes:
        scene = changes["from_scene"]
        if scene not in (None, 0) and (isinstance(scene, bool) or not isinstance(scene, int) or not 1 <= scene <= 10000):
            raise ValueError("from_scene is the number of the scene the look starts in (1, 2, 3...), or 0.")
        fields["from_scene"] = scene or None
    if "palette" in changes:
        fields["palette"] = " ".join(str(changes["palette"] or "").split())[:PALETTE_CHARS]
    if "relations" in changes:
        given = changes["relations"] or []
        if not isinstance(given, list) or len(given) > MOST_RELATIVES:
            raise ValueError("relations is a list of up to {} relatives: {{\"to\", \"relation\", \"blood\"}}.".format(MOST_RELATIVES))
        out = []
        for rel in given:
            other = kit.get(rel.get("to")) if isinstance(rel, dict) else None
            words = " ".join(str((rel or {}).get("relation") or "").lower().split())[:RELATION_CHARS] if isinstance(rel, dict) else ""
            if other is None or other["id"] == row["id"] or other["tag"] != "character" or other.get("look_of"):
                raise ValueError("Each relative is another character of this project's NeuralCore (its base entry, not a look).")
            if not words:
                raise ValueError("Say how they are related: \"mother\", \"brother\", \"mother-in-law\"...")
            if any(o["to"] == other["id"] for o in out):
                continue
            out.append({"to": other["id"], "relation": words, "blood": bool(rel.get("blood", True)) and not IN_LAW.search(words)})
        fields["relations"] = json.dumps(out) if out else ""
    return fields


def _own_look(db, user_id, asset_id):
    """An entry named as a look of another ("Maya - torn sleeve") is linked to it when that entry is in the same kit
    and the link was not set otherwise. A name with a dash that names no entry stays as it is."""
    row = entry(db, user_id, asset_id)
    found = LOOK_NAME.match(row["name"]) if row and not row.get("look_of") and row["tag"] in HAS_LOOKS else None
    if not found or not row.get("project_id"):
        return
    base = next((e for e in entries(db, user_id, row["project_id"]) if e["id"] != row["id"] and not e.get("look_of")
                 and e["tag"] == row["tag"] and e["name"].lower() == found.group(1).strip().lower()), None)
    if base:
        db.run("UPDATE assets SET look_of = ?, variant = ? WHERE id = ?", (base["id"], found.group(2).strip()[:VARIANT_CHARS], asset_id))


def root(db, project):
    """The project whose kit a project uses: a module shares the kit of the project it is in."""
    if not project:
        return project
    row = db.one("SELECT parent_id FROM projects WHERE id = ?", (project,))
    return row["parent_id"] if row and row["parent_id"] else project


def _where(project):
    return ("project_id = ?", (project,))


def entries(db, user_id, project, hidden=False):
    """The kit of a project, in order: the always-on entries first, then the rest. Each a row of assets with "type".
    Outside a project there is none. In a project shared with the user it is the owner's kit (sharing.py).
    In a module, what the module changed for itself is put in (overrides()): an entry it hid is left out (kept, with
    "hidden": True, when `hidden`), and its own always, use note and preferred picture replace the project's."""
    module = project
    project = root(db, project)
    if not project:
        return []
    keeper = keeper_of(db, user_id, project)
    where, params = _where(project)
    with as_everyone() if keeper != user_id else contextlib.nullcontext():
        rows = db.all("SELECT id, name, tag, kind, filename, size, about, use_note, origin, made_from, always, position, named, created, facts, public_id, "
                      "project_id, look_of, variant, from_scene, palette, relations "
                      "FROM assets WHERE user_id = ? AND " + where + " ORDER BY always DESC, position, created", (keeper, *params))
    rows = [dict(row, type=TYPES.get(row["tag"], "other")) for row in rows]
    if module and module != project:
        rows = _in_module(rows, overrides(db, keeper, module), hidden)
    return rows


def _in_module(rows, changed, hidden):
    out = []
    for row in rows:
        mine = changed.get(row["id"])
        if mine:
            if mine["removed"]:
                if not hidden:
                    continue
                row = dict(row, hidden=True)
            if mine["always"] is not None:
                row = dict(row, always=mine["always"])
            if mine["use_note"] is not None:
                row = dict(row, use_note=mine["use_note"])
            if mine["preferred_item"]:
                row = dict(row, preferred_item=mine["preferred_item"])
            row = dict(row, changed_here=True)
        out.append(row)
    return sorted(out, key=lambda r: (not r["always"], r["position"], r["created"]))


def overrides(db, keeper, module):
    """{asset id: what this module changed of it}."""
    with as_everyone():
        rows = db.all("SELECT asset_id, removed, always, use_note, preferred_item FROM kit_overrides WHERE user_id = ? AND module_id = ?",
                      (keeper, module))
    return {r["asset_id"]: r for r in rows}


def override(db, user_id, module, asset_id, changes):
    """Change an entry of the project's kit for one module only: {"removed"?, "always"?, "use_note"?, "preferred_item"?};
    a None value goes back to the project's. Returns the entry as the module sees it, or None when it is not there.
    Every member who may make things in the project may do it (the caller checks the role)."""
    project = root(db, module)
    if not project or project == module:
        return None
    keeper = keeper_of(db, user_id, project)
    found = next((e for e in entries(db, user_id, module, hidden=True) if e["id"] == asset_id), None)
    if found is None:
        return None
    with as_everyone():
        now = db.one("SELECT removed, always, use_note, preferred_item FROM kit_overrides WHERE module_id = ? AND asset_id = ?",
                     (module, asset_id)) or {"removed": 0, "always": None, "use_note": None, "preferred_item": None}
        fields = dict(now)
        if "removed" in changes:
            fields["removed"] = 1 if changes["removed"] else 0
        if "always" in changes:
            fields["always"] = None if changes["always"] is None else (1 if changes["always"] else 0)
        if "use_note" in changes:
            fields["use_note"] = None if changes["use_note"] is None else clean_note(changes["use_note"])
        if "preferred_item" in changes:
            fields["preferred_item"] = int(changes["preferred_item"]) if changes["preferred_item"] else None
        if not fields["removed"] and all(fields[k] is None for k in ("always", "use_note", "preferred_item")):
            db.run("DELETE FROM kit_overrides WHERE module_id = ? AND asset_id = ?", (module, asset_id))
        else:
            db.run("INSERT INTO kit_overrides (user_id, module_id, asset_id, removed, always, use_note, preferred_item, updated) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(module_id, asset_id) DO UPDATE SET removed = excluded.removed, "
                   "always = excluded.always, use_note = excluded.use_note, preferred_item = excluded.preferred_item, updated = excluded.updated",
                   (keeper, module, asset_id, fields["removed"], fields["always"], fields["use_note"], fields["preferred_item"], time.time()))
    return next((e for e in entries(db, user_id, module, hidden=True) if e["id"] == asset_id), None)


def keeper_of(db, user_id, project):
    """Whose kit a project's is for this user: their own, or the owner's of a project shared with them."""
    from . import sharing
    role, _, top = sharing.role_in(db, user_id, project)
    return top["user_id"] if role and role != "owner" else user_id


def entry(db, user_id, asset_id):
    row = db.one("SELECT * FROM assets WHERE id = ? AND user_id = ?", (asset_id, user_id))
    return dict(row, type=TYPES.get(row["tag"], "other")) if row else None


def _next_position(db, user_id, project):
    project = root(db, project)
    where, params = _where(project)
    found = db.one("SELECT MAX(position) AS last FROM assets WHERE user_id = ? AND " + where, (user_id, *params))
    return (found["last"] or 0) + 1 if found else 1


def add(db, folder, user_id, project, data, filename, kind, name, tag="other", always=False, named=True, about="",
        use_note="", made_from=None, origin="kit"):
    """Add a file to a project's kit and return its id. The same file added again to the same project is the entry it
    already is: a name, a type and always-on given now fill in what it lacked (an entry without a name gets one).
    None outside a project: a kit belongs to a project and is never kept for all work."""
    project = root(db, project)
    if not project:
        return None
    digest = hashlib.sha1(data).hexdigest()[:10]
    stored = "{}_{}".format(digest, safe_name(filename))
    where, params = _where(project)
    # the same content, whatever the file was called (its stored name starts with the content's digest)
    before = next((r for r in db.all("SELECT id, named, tag, always, filename FROM assets WHERE user_id = ? AND " + where, (user_id, *params))
                   if r["filename"].startswith(digest + "_")), None)
    name, tag = clean_name(name) or "Untitled", tag_of(tag)
    if before:
        changes = {}
        if named and not before["named"]:
            changes.update(name=name, named=1)
        if tag != "other" and before["tag"] == "other":
            changes["tag"] = tag
        if always and not before["always"]:
            changes["always"] = 1
        if changes:
            db.run("UPDATE assets SET {} WHERE id = ?".format(", ".join(k + " = ?" for k in changes)), (*changes.values(), before["id"]))
        return before["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored).write_bytes(data)
    asset = db.run("INSERT INTO assets (user_id, name, tag, kind, filename, size, created, origin, project_id, about, use_note, "
                   "made_from, always, position, named) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (user_id, name, tag, kind, stored, len(data), time.time(), origin, project or None, clean_note(about),
                    clean_note(use_note), made_from, 1 if always else 0, _next_position(db, user_id, project), 1 if named else 0))
    if named:
        _own_look(db, user_id, asset)
    return asset


def add_item(db, folder, outputs, user_id, project, item_id, name="", tag="other", always=False, named=True, about=""):
    """Add a library item (a result on the canvas, an attached file) to a project's kit. None if there is no such item."""
    row = db.one("SELECT id, name, kind, filename, about FROM generations WHERE id = ? AND user_id = ?", (item_id, user_id))
    source = outputs / row["filename"] if row else None
    if not source or not source.is_file():
        return None
    return add(db, folder, user_id, project, source.read_bytes(), Path(row["filename"]).name, row["kind"], name or row["name"], tag, always,
               named, about or row["about"] or "", made_from=row["id"])


def update(db, user_id, asset_id, changes):
    """Change an entry: name, type, about, use_note, always, position, and how it hangs together with the others:
    look_of (the entry it is a look or a time of day of, or 0), variant ("torn sleeve", "night"), from_scene (the scene
    a changed look starts in), palette (a location's) and relations ([{"to", "relation", "blood"}], a character's).
    Returns the entry, or None if it is not the user's. Raises ValueError, with the reason, for a link that is wrong."""
    row = entry(db, user_id, asset_id)
    if row is None:
        return None
    fields = _links(db, user_id, row, changes)
    if "name" in changes and clean_name(changes["name"]):
        fields.update(name=clean_name(changes["name"]), named=1)
    if "type" in changes or "tag" in changes:
        fields["tag"] = tag_of(changes.get("type", changes.get("tag")))
    for key in ("about", "use_note"):
        if key in changes:
            fields[key] = clean_note(changes[key])
    if "always" in changes:
        fields["always"] = 1 if changes["always"] else 0
    if isinstance(changes.get("position"), (int, float)) and not isinstance(changes.get("position"), bool):
        fields["position"] = float(changes["position"])
    if fields:
        db.run("UPDATE assets SET {} WHERE id = ?".format(", ".join(k + " = ?" for k in fields)), (*fields.values(), asset_id))
    if "name" in fields and "look_of" not in changes:
        _own_look(db, user_id, asset_id)
    return entry(db, user_id, asset_id)


def reorder(db, user_id, project, ids):
    """Put a project's entries in the order given (ids); the ones not named keep their place after them."""
    project = root(db, project)
    mine = {row["id"] for row in entries(db, user_id, project)}
    for position, asset_id in enumerate([i for i in ids if i in mine], start=1):
        db.run("UPDATE assets SET position = ? WHERE id = ?", (position, asset_id))


def remove(db, folder, user_id, asset_id):
    row = entry(db, user_id, asset_id)
    if row is None:
        return False
    db.run("DELETE FROM assets WHERE id = ?", (asset_id,))
    if row.get("project_id"):   # its looks become entries of their own; relatives that named it forget it
        import json
        db.run("UPDATE assets SET look_of = NULL WHERE user_id = ? AND look_of = ?", (user_id, asset_id))
        for other in entries(db, user_id, row["project_id"]):
            kept = [r for r in relations_of(other) if r["to"] != asset_id]
            if len(kept) != len(relations_of(other)):
                db.run("UPDATE assets SET relations = ? WHERE id = ?", (json.dumps(kept) if kept else "", other["id"]))
    if not db.one("SELECT 1 FROM assets WHERE user_id = ? AND filename = ?", (user_id, row["filename"])):
        try:
            (folder / row["filename"]).unlink(missing_ok=True)   # another project may have the same file: then it stays
        except OSError:
            pass   # held open for the moment (a download of it): the entry is gone, the file goes with the next cleanup
    return True


# ---------------------------------------------------------------- always on: what goes into every shot

def always(db, user_id, project):
    """The always-on entries of a project, in order. A look ("Maya - torn sleeve") is never always on: a shot that
    needs it names it, and its base entry stands for the person or place in every other shot."""
    return [e for e in entries(db, user_id, project) if e["always"] and not e.get("look_of")]


def fills(schema, on, taken=(), used=(), left_out=(), used_items=()):
    """The reference slots of a workflow that the always-on entries fill:
    [{"id": 0, "asset", "name", "slot", "label", "kind", "role", "item_kind", "said_as"}].

    on: always(), in order. taken: slot ids that have a file already; used: asset ids already in the job; left_out:
    asset ids a shot leaves out (a close-up on white has no location); used_items: library ids already in the job (an
    entry kept from one of them is in it already). The characters go into the character slots in
    their order (a slot for the same person from another angle takes a second picture under the first one's name), the
    rest into the slot for their type. First frame, last frame and voice track are never filled from the kit."""
    special = set((schema.get("slots") or {}).values())
    taken, used, left_out, used_items = set(taken), set(used), set(left_out), set(used_items)
    slots = [r for r in schema["refs"] if r["id"] not in special and r["id"] not in taken]
    out = []

    def put(slot, e, said_as):
        taken.add(slot["id"])
        used.add(e["id"])
        out.append({"id": 0, "asset": e["id"], "name": e["name"], "slot": slot["id"], "label": slot["label"].split(" (")[0],
                    "kind": slot["kind"], "role": e["tag"], "item_kind": e["kind"], "said_as": said_as})

    def fit(e, slot):
        return (e["kind"] in FITS.get(slot["kind"], ()) and e["id"] not in used and e["id"] not in left_out
                and not (e.get("made_from") and e["made_from"] in used_items))

    people = [e for e in on if e["tag"] == "character"]
    first_name = people[0]["name"].lower() if people else None
    names_seen, distinct = set(), []
    for e in people:   # the characters, one picture each, in order; more pictures of the same one are its other angles
        if e["name"].lower() not in names_seen:
            names_seen.add(e["name"].lower())
            distinct.append(e)
    angles = [e for e in people if e["name"].lower() == first_name and e not in distinct[:1]]
    order = 0
    for slot in slots:
        if slot["id"] in taken:
            continue
        label = slot["label"]
        if OTHER_ANGLE.search(label):
            e = next((a for a in angles if fit(a, slot)), None)
            if e:
                put(slot, e, PEOPLE[0])
            continue
        tag = next((t for t, words in SLOT_WORDS if SLOT_KIND.get(t, "image") == slot["kind"] and re.search(words, label, re.IGNORECASE)), None)
        if tag == "character":
            while order < len(distinct) and not fit(distinct[order], slot):
                order += 1
            if order < len(distinct):
                put(slot, distinct[order], PEOPLE[min(order, len(PEOPLE) - 1)])
                order += 1
        elif tag:
            e = next((e for e in on if e["tag"] == tag and fit(e, slot)), None)
            if e:
                put(slot, e, SAID_AS.get(tag, "the " + TYPES[tag]))
    return out


def described(on):
    """The always-on entries in words for the agent's model, or "" when there are none."""
    if not on:
        return ""
    people = []
    lines = []
    for e in on:
        if e["tag"] == "character":
            if e["name"].lower() in people:
                continue   # another angle of a character already said
            people.append(e["name"].lower())
            said = PEOPLE[min(len(people) - 1, len(PEOPLE) - 1)]
        else:
            said = SAID_AS.get(e["tag"], "the " + TYPES.get(e["tag"], "reference"))
        lines.append('- {} "{}" (asset {}): in prompts call it "{}".'.format(TYPES.get(e["tag"], "other"), e["name"], e["id"], said))
    return ("Always on: these entries of NeuralCore are attached to every shot automatically, in the slots meant for them "
            "(the characters in this order). Do not describe how they look and do not list them in \"uses\"; name them in "
            "the prompt with the words given. A shot they do not belong in leaves them out: list their asset ids in "
            "\"leave_out\".\n" + "\n".join(lines))


IN_WORDS = ("character", "background", "outfit", "prop")   # the entries a prompt describes when a model takes no pictures
IN_WORDS_CHARS = 220


def in_words(on, left_out=()):
    """The always-on entries in words, for a workflow that takes no reference pictures (text to image, text to video):
    what each shows, so the model keeps them the same from the words alone. "" when there is nothing to say."""
    left_out, seen, people, parts = set(left_out), set(), 0, []
    for e in on:
        if e["tag"] not in IN_WORDS or e["id"] in left_out or not e.get("about"):
            continue
        if e["tag"] == "character":
            if e["name"].lower() in seen or people >= 2:
                continue   # one description a person, and no more than two people: a prompt is not a cast list
            seen.add(e["name"].lower())
            said = PEOPLE[people]
            people += 1
        else:
            said = SAID_AS[e["tag"]]
        words = e["about"][:IN_WORDS_CHARS].rstrip(".")
        if e["tag"] == "background" and e.get("palette"):
            words += ", graded to " + e["palette"].rstrip(".")
        parts.append("{}: {}".format(said[0].upper() + said[1:], words))
    return ". ".join(parts) + "." if parts else ""


def mentions(schema, text, all_entries, taken=(), usable=None):
    """@names in a prompt the user wrote ("@Violet walks into @Bonfire Clearing"): each entry of the kit named so goes
    into a free reference slot that fits it, and its name in the prompt becomes the words the model ties to that slot
    ("the main character", "the background"). An entry with no slot for it (a model that takes no pictures) is said by
    what it shows. Returns (the prompt, {slot id: asset id}). taken: slots that have a file; usable: the slots the
    chosen mode reads (all when None)."""
    named = sorted((e for e in all_entries if e["name"]), key=lambda e: -len(e["name"]))
    if "@" not in str(text or "") or not named:
        return text, {}
    special = set((schema.get("slots") or {}).values())
    taken = set(taken)
    slots = [r for r in schema["refs"] if r["id"] not in special and (usable is None or r["id"] in usable)]
    people = [r for r in slots if r["kind"] == "image" and re.search(SLOT_WORDS[0][1], r["label"], re.IGNORECASE) and not OTHER_ANGLE.search(r["label"])]
    placed, words = {}, {}

    def slot_for(e):
        fits = [r for r in slots if r["id"] not in taken and e["kind"] in FITS.get(r["kind"], ())]
        if e["tag"] == "character":
            return next((r for r in people if r in fits), None)
        words_for_type = dict(SLOT_WORDS).get(e["tag"])
        return next((r for r in fits if words_for_type and re.search(words_for_type, r["label"], re.IGNORECASE)), None)

    def said(e):
        if e["id"] in words:
            return words[e["id"]]
        slot = slot_for(e)
        if slot is None:   # nowhere to put it: the model is told what it shows instead
            words[e["id"]] = (e.get("about") or e["name"])[:IN_WORDS_CHARS].rstrip(".")
            return words[e["id"]]
        taken.add(slot["id"])
        placed[slot["id"]] = e["id"]
        if e["tag"] == "character":
            words[e["id"]] = PEOPLE[min(people.index(slot), len(PEOPLE) - 1)]
        else:
            words[e["id"]] = SAID_AS.get(e["tag"], "the " + TYPES.get(e["tag"], "reference"))
        return words[e["id"]]

    pattern = re.compile(r"@(" + "|".join(re.escape(e["name"]) for e in named) + r")(?![\w])", re.IGNORECASE)
    by_name = {e["name"].lower(): e for e in named}
    out = pattern.sub(lambda m: said(by_name[m.group(1).lower()]), str(text))
    return out, placed


def copy_entry(db, assets_dir, row, user_id, project, origin="copied"):
    """An entry of another project's kit (a row of assets) copied into `project`'s kit for `user_id` (its keeper), file
    and all, with what it shows and its facts. Returns the new entry's id, or None when its file is gone."""
    try:
        data = (Path(assets_dir) / str(row["user_id"]) / row["filename"]).read_bytes()
    except OSError:
        return None
    asset = add(db, Path(assets_dir) / str(user_id), user_id, project, data, row["filename"].split("_", 1)[-1], row["kind"],
                row["name"], row["tag"], False, True, row["about"], row["use_note"], None, origin)
    if asset and row.get("facts"):
        db.run("UPDATE assets SET facts = ? WHERE id = ? AND facts = ''", (row["facts"], asset))
    return asset


def copy_entries(db, user_id, source, target):
    """The kit of project `source` again in project `target` (a duplicate of the project): the same entries, sharing
    their files, which stay until no entry uses them (remove)."""
    import json
    fields = "name, tag, kind, filename, size, about, use_note, origin, made_from, always, position, named, variant, from_scene, palette"
    new_id, links = {}, []
    for row in db.all("SELECT id, look_of, relations, " + fields + " FROM assets WHERE user_id = ? AND project_id = ? ORDER BY position, id",
                      (user_id, source)):
        row = dict(row)
        old, look_of, relations = row.pop("id"), row.pop("look_of"), row.pop("relations")
        new_id[old] = db.run("INSERT INTO assets (user_id, " + fields + ", project_id, created) VALUES (?, " + ", ".join("?" * 15) + ", ?, ?)",
                             (user_id, *row.values(), target, time.time()))
        links.append((new_id[old], look_of, relations))
    for asset, look_of, relations in links:   # the copies point at each other, never back at the source project's entries
        kept = [dict(r, to=new_id[r["to"]]) for r in relations_of({"relations": relations}) if r["to"] in new_id]
        db.run("UPDATE assets SET look_of = ?, relations = ? WHERE id = ?",
               (new_id.get(look_of), json.dumps(kept) if kept else "", asset))
