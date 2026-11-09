"""NeuralCore's memory: what one module (or a project's main canvas) keeps, and the asset catalogue it reads.

The memory is a tree of paths (runs.py keeps the rows). It belongs to the module the agent is open in and to no other:
every agent tab of that module and every member of the project read and write the same tree, and a second module of
the project has a tree of its own. It is kept under the project's owner, as NeuralCore's entries are (kit.keeper_of).

- /cast/<name>: the project's NeuralCore entries as this module uses them (read only here: book_save changes them).
- /assets: the catalogue. Every picture, clip, sound and file of the module, and every entry of the cast, is a record
  at /assets/<id>, where <id> is twelve random hex digits. Nothing is copied there; /assets/<id>/facts is the one part
  written to it, and "$state:/assets/<id>/url" stands for the file itself.
- /skill, /attached, /claude: the agent tab's own (runs.PROTECTED), set by the studio only.
- anything else: the module's own notes, as the agent and its skills write them (/motion/clips/c1, /plan/scenes/2).
Outside a project the tab's own run holds everything, as it always did.

A reference "$state:/path" stands for the value kept at that path; resolve() gives it, and fill_text() puts the values
of the references inside a longer text such as a prompt.
"""

import contextlib
import json
import mimetypes
import re
import secrets
import time

from . import runs, sharing
from .db import as_everyone

EPISODE = "ep-{}"   # the run name of a module's memory; a tab's run is base36 with no dash, so never this
CATALOGUE = "/assets"
CAST = "/cast"
FACT_KEYS = {"photoreal": bool, "has_person": bool, "subjects": dict, "scene": str, "description": str, "tags": dict}
MAX_FACTS = 4000    # characters of one record's facts, as JSON
CATALOGUE_MOST = 1000
WRITE_ROLES = ("owner", "manager", "creator")
PUBLIC = re.compile(r"[0-9a-f]{12}")
# What an item was made from, by the settings that name it: the first of these that holds a library id.
SOURCE_KEYS = ("video", "image", "audio", "parent", "item", "start_from", "source_item")

REFERENCE = re.compile(r"^\$state:(/[a-z0-9_./-]+?)(/\*)?$")
# Inside a longer text a reference ends at whitespace, a quote, a bracket or a comma (a path holds none of them).
IN_TEXT = re.compile(r"\$state:(/[a-z0-9_./-]*[a-z0-9_-])")


class Place:
    """Where a path lives: whose rows (user_id), which run, the path inside it, whether this user may write there."""

    def __init__(self, user_id, run, path, writable, label, shared):
        self.user_id, self.run, self.path, self.writable, self.label, self.shared = user_id, run, path, writable, label, shared

    def rows(self):
        """Another user's rows (the owner's, in a shared project) are read past the request's own-rows guard."""
        return as_everyone() if self.shared else contextlib.nullcontext()


class Core:
    """The memory as one agent conversation sees it: `user` (its id), the tab's `run` ("" when it keeps none) and the
    project or module it is open in (0 for none)."""

    def __init__(self, db, user_id, run, project=0):
        self.db, self.user_id, self.run, self.project = db, user_id, run or "", int(project or 0)
        self.role, self.here, self.top = sharing.role_in(db, user_id, self.project) if self.project else (None, None, None)
        if self.project and self.role is None:
            raise runs.RunError("No such project.")
        self.owner = self.top["user_id"] if self.top else user_id

    # -- where a path lives --------------------------------------------------------------------------------------

    @property
    def keeps_state(self):
        return bool(self.project or self.run)

    def episode(self):
        """The module's own memory, at its root."""
        if self.project:
            return Place(self.owner, EPISODE.format(self.project), "/", self.role in WRITE_ROLES, "module", self.owner != self.user_id)
        if self.run:
            return Place(self.user_id, self.run, "/", True, "run", False)
        raise runs.RunError("This conversation keeps no memory: open a project, or start the skill again from the Agent tab.")

    def locate(self, path):
        """The Place a path given by the agent (or the studio) is in. Raises RunError for a path that cannot be."""
        path = str(path or "").strip()
        if path.startswith("@"):
            raise runs.RunError("Memory belongs to this module alone; another module's or project's cannot be read. "
                                "A path starts with /, like /plan/scenes/1.")
        clean = runs.clean_path(path)
        if runs._protected(clean):
            if not self.run:
                raise runs.RunError("{} belongs to an agent tab, and this conversation has none.".format(clean))
            return Place(self.user_id, self.run, clean, False, "tab", False)
        place = self.episode()
        place.path = clean
        return place

    # -- reading and writing ---------------------------------------------------------------------------------------

    def read(self, path, offset=0, limit=runs.PAGE):
        if _under(path, CATALOGUE):
            return self.catalogue_read(path, offset)
        if _under(path, CAST):
            return self.cast_read(path)
        place = self.locate(path)
        with place.rows():
            found = runs.read(self.db, place.user_id, place.run, place.path, offset, limit)
        return dict(found, scope=place.label)

    def write(self, path, value, writer="agent"):
        if _under(path, CATALOGUE):
            return self.catalogue_write(path, value)
        place = self._writable(path)
        with place.rows():
            written = runs.write(self.db, place.user_id, place.run, place.path, value, writer)
        return dict(written, scope=place.label)

    def write_many(self, folder, values, writer="agent", replace=False):
        place = self._writable(folder)
        with place.rows():
            written = runs.write_many(self.db, place.user_id, place.run, place.path, values, writer, replace)
        return dict(written, scope=place.label)

    def delete(self, path):
        place = self._writable(path)
        with place.rows():
            return runs.delete(self.db, place.user_id, place.run, place.path)

    def leaves(self, folder):
        if _under(folder, CAST):
            found = self.cast_read(folder)
            value = found.get("value") if not found.get("missing") else None
            return sorted(value.items(), key=lambda kv: runs._natural(kv[0])) if isinstance(value, dict) else []
        place = self.locate(folder)
        with place.rows():
            return runs.leaves(self.db, place.user_id, place.run, place.path)

    def coverage(self, path, against):
        here, there = self.locate(path), self.locate(against)
        with here.rows():
            have = runs.children(self.db, here.user_id, here.run, here.path)
        with there.rows():
            need = runs.children(self.db, there.user_id, there.run, there.path)
        missing = [n for n in need if n not in set(have)]
        return {"ok": not missing and bool(need), "missing": missing, "extra": sorted(set(have) - set(need), key=runs._natural),
                "count": len(need)}

    def _writable(self, path):
        if _under(path, CATALOGUE):
            raise runs.RunError("Only /assets/<id>/facts is written in the catalogue.")
        if _under(path, CAST):
            raise runs.RunError("/cast is the project's NeuralCore entries: change one with book_save, not state_write.")
        place = self.locate(path)
        if not place.writable:
            if place.label == "tab":
                raise runs.RunError("{} is kept by the studio: the agent cannot set it.".format(place.path))
            raise runs.RunError("This module's memory is read only for you.")
        return place

    def tree(self, limit=runs.MAX_PATHS):
        """Every leaf of the module's memory, in path order, for NeuralCore's Memory view: {"total", "writable",
        "leaves": [{"path", "value", "writer", "updated"}]}. The tab's own paths are left out."""
        place = self.episode()
        with place.rows():
            rows = self.db.all("SELECT path, value, writer, updated FROM run_state WHERE user_id = ? AND run = ? ORDER BY path",
                               (place.user_id, place.run))
        rows = [r for r in rows if not runs._protected(r["path"])]
        return {"total": len(rows), "writable": place.writable,
                "leaves": [{"path": r["path"], "value": json.loads(r["value"]), "writer": r["writer"], "updated": r["updated"]}
                           for r in rows[:limit]]}

    def saved_since(self, since):
        """Whether the agent saved anything to the module's memory after `since` (the studio's own writes do not count)."""
        if not self.keeps_state:
            return False
        place = self.episode()
        with place.rows():
            found = self.db.one("SELECT MAX(updated) AS last FROM run_state WHERE user_id = ? AND run = ? AND writer <> 'studio'",
                                (place.user_id, place.run))
        return bool(found and found["last"] and found["last"] > since)

    def saved_any(self):
        return self.saved_since(0)

    def adopt(self):
        """What a tab kept for itself before modules kept their memory moves into the module's, once, when the module
        has none yet: a run under way carries on where it was. The tab keeps its own paths (/skill, ...)."""
        if not (self.project and self.run):
            return 0
        place = self.episode()
        with place.rows():
            if self.db.one("SELECT 1 FROM run_state WHERE user_id = ? AND run = ? LIMIT 1", (place.user_id, place.run)):
                return 0
        rows = self.db.all("SELECT path FROM run_state WHERE user_id = ? AND run = ?", (self.user_id, self.run))
        moving = [r["path"] for r in rows if not runs._protected(r["path"])]
        if not moving:
            return 0
        with as_everyone():
            for path in moving:
                self.db.run("UPDATE run_state SET user_id = ?, run = ? WHERE user_id = ? AND run = ? AND path = ?",
                            (place.user_id, place.run, self.user_id, self.run, path))
        return len(moving)

    # -- references --------------------------------------------------------------------------------------------------

    def resolve(self, reference, depth=0):
        """What "$state:/path" stands for. A value {"item": id} or a bare id gives the id; a record of the catalogue
        (/assets/<id> or /assets/<id>/url) gives its library id, or {"asset": id} for an entry; "$state:/folder/*"
        every leaf of the folder, each with "n" (its name) added. A value that is itself a reference is followed.
        Raises RunError naming the path when nothing is written there."""
        match = REFERENCE.match(str(reference or ""))
        if not match:
            raise runs.RunError("A state reference is written $state:/path/to/leaf, or $state:/folder/* for all of a folder.")
        path = match.group(1)
        if _under(path, CATALOGUE):
            parts = [p for p in path.split("/") if p][1:]
            row, key = self._record(parts[0]) if parts else (None, None)
            if row is None:
                raise runs.RunError("state_reference_unresolved: nothing is in the catalogue at {}.".format(path))
            if len(parts) == 1 or parts[1] in ("url", "file", "item"):
                return row["id"] if key == "item" else {"asset": row["id"]}
            found = self.catalogue_read(path)
            if found.get("missing"):
                raise runs.RunError("state_reference_unresolved: the record at /assets/{} has no {}.".format(parts[0], parts[1]))
            return found["value"]
        if match.group(2):
            found = self.leaves(path)
            if not found:
                raise runs.RunError("state_reference_unresolved: nothing is written under {} yet.".format(path))
            name = lambda n: int(n) if n.isdigit() else n
            return [dict(value, n=name(n)) if isinstance(value, dict) else {"n": name(n), "value": value} for n, value in found]
        found = self.read(path)
        if found.get("missing") or found.get("folder"):
            raise runs.RunError("state_reference_unresolved: nothing is written at {} yet.".format(path))
        value = found["value"]
        if isinstance(value, str) and value.startswith("$state:") and depth < 3:
            return self.resolve(value, depth + 1)
        return value.get("item", value) if isinstance(value, dict) else value

    def resolve_all(self, value):
        """Every whole-value reference in a structure replaced by what it stands for (an operation's settings)."""
        if isinstance(value, str) and value.startswith("$state:"):
            return self.resolve(value)
        if isinstance(value, list):
            return [self.resolve_all(v) for v in value]
        if isinstance(value, dict):
            return {k: self.resolve_all(v) for k, v in value.items()}
        return value

    def fill_text(self, text):
        """A text (a prompt) with each reference inside it replaced in place by the words kept there: a text value as it
        is, a record by its "visual", "description" or "text", anything else as JSON. Raises RunError for one not there."""
        def words(match):
            path = match.group(1)
            if _under(path, CATALOGUE) and path.count("/") == 2:   # a record of the catalogue: what it shows
                found = self.catalogue_read(path)
                if found.get("missing"):
                    raise runs.RunError("state_reference_unresolved: nothing is in the catalogue at {}.".format(path))
                value = found["value"]
            else:
                value = self.resolve("$state:" + path)
            if isinstance(value, dict):
                value = value.get("visual") or value.get("description") or value.get("shows") or value.get("text") \
                    or json.dumps(value, ensure_ascii=False)
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return IN_TEXT.sub(words, str(text or ""))

    # -- other projects' NeuralCore entries (copied in by book_save; their memory is never read) ---------------------------

    def projects(self):
        """[(id, name, ref)] of every project the user owns or is in, but this one."""
        own = self.db.all("SELECT id, name, ref FROM projects WHERE user_id = ? AND parent_id IS NULL ORDER BY id", (self.user_id,))
        shared = sharing.shared_ids(self.db, self.user_id)
        with as_everyone():
            others = self.db.all("SELECT id, name, ref FROM projects WHERE parent_id IS NULL AND id IN ({}) ORDER BY id".format(
                ", ".join("?" * len(shared))), shared) if shared else []
        here = self.top["id"] if self.top else None
        return [(r["id"], r["name"], r["ref"]) for r in own + others if r["id"] != here]

    def search_projects(self, query, limit=12):
        """NeuralCore entries of the user's other projects whose name, type, description, note or facts hold every word
        of `query`: [{"asset", "name", "type", "kind", "shows", "facts"?, "project", "project_id"}]."""
        from . import kit   # kit imports this module's neighbours; imported here to keep the import order plain
        words = str(query or "").lower().split()
        found = []
        for project_id, name, ref in self.projects():
            for row in kit.entries(self.db, self.user_id, project_id):
                text = json.dumps([row["name"], row["type"], row["about"], row["use_note"], row.get("facts") or ""], ensure_ascii=False).lower()
                if all(w in text for w in words):
                    found.append({"asset": row["id"], "name": row["name"], "type": row["type"], "kind": row["kind"],
                                  "shows": row["about"][:200], **({"facts": _facts(row)} if _facts(row) else {}),
                                  "project": "{} ({})".format(name, ref), "project_id": project_id})
                    if len(found) >= limit:
                        return found
        return found

    def entry_elsewhere(self, asset_id):
        """A NeuralCore entry of another project the user is in (a row of assets), or None."""
        with as_everyone():
            row = self.db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
        if row is None or not row["project_id"] or (self.top and self._root_of(row["project_id"]) == self.top["id"]):
            return None
        return row if sharing.role_in(self.db, self.user_id, row["project_id"])[0] else None

    def _root_of(self, project_id):
        with as_everyone():
            row = self.db.one("SELECT id, parent_id FROM projects WHERE id = ?", (project_id,))
        return (row["parent_id"] or row["id"]) if row else None

    # -- the cast: this module's NeuralCore entries ----------------------------------------------------------------------

    def cast_entries(self):
        """The entries of this module's NeuralCore, each with "public_id" given."""
        if not self.project:
            return []
        from . import kit
        rows = kit.entries(self.db, self.user_id, self.project)
        ids = public_ids(self.db, "assets", [r["id"] for r in rows])
        return [dict(r, public_id=ids.get(r["id"], "")) for r in rows]

    def cast(self):
        """{name: {"type", "visual", "ref", "always", "use"?, "entry", and how it hangs together:
        "look_of"? and "variant"? (a look or a time of day, by the base's name), "from_scene"?, "looks"? (a base's,
        by name), "palette"?, "relatives"? ([{"name", "relation", "blood"}])}} with names in snake_case."""
        from . import kit
        rows = self.cast_entries()
        names = {}
        for row in rows:
            name = slug(row["name"]) or "entry"
            while name in names.values():
                name += "_{}".format(row["id"])
            names[row["id"]] = name
        out = {}
        for row in rows:
            looks = [names[r["id"]] for r in kit.looks(rows, row["id"]) if r["id"] in names]
            kin = [{"name": names.get(k["entry"], slug(k["name"])), "relation": k["relation"], "blood": k["blood"]}
                   for k in kit.family(rows, row["id"])]
            out[names[row["id"]]] = {
                "type": row["type"], "visual": row["about"], "ref": "$state:/assets/{}/url".format(row["public_id"]),
                "always": bool(row["always"]), **({"use": row["use_note"]} if row["use_note"] else {}),
                "entry": row["id"],
                **({"look_of": names.get(row["look_of"], ""), "variant": row["variant"]} if row.get("look_of") else {}),
                **({"from_scene": row["from_scene"]} if row.get("from_scene") else {}),
                **({"looks": looks} if looks else {}), **({"palette": row["palette"]} if row.get("palette") else {}),
                **({"relatives": kin} if kin else {})}
        return out

    def cast_read(self, path):
        parts = [p for p in str(path).split("/") if p][1:]
        value = self.cast()
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                return {"path": path, "missing": True}
            value = value[part]
        return {"path": path, "value": value, "scope": "cast"}

    # -- the asset catalogue -------------------------------------------------------------------------------------------

    def catalogue(self, offset=0, limit=CATALOGUE_MOST):
        """Every record of the module, newest first: its library items (working files of its runs too) and the cast's
        entries. {"total", "offset", "records": [record]}."""
        offset, limit = max(0, int(offset or 0)), max(1, min(int(limit or CATALOGUE_MOST), CATALOGUE_MOST))
        where, params = ("project_id = ?", [self.project]) if self.project else ("user_id = ? AND project_id IS NULL", [self.user_id])
        with as_everyone() if self.project else contextlib.nullcontext():   # every member's work in the module
            rows = self.db.all("SELECT * FROM generations WHERE " + where + " ORDER BY id DESC", params)
        ids = public_ids(self.db, "generations", [r["id"] for r in rows])
        sources = public_ids(self.db, "generations", [s for s in (_source(r) for r in rows) if s])
        records = [record_of(dict(r, public_id=ids.get(r["id"], "")), "item", sources) for r in rows]
        cast = self.cast_entries()
        made = public_ids(self.db, "generations", [e["made_from"] for e in cast if e["made_from"]])
        records += [record_of(e, "asset", made) for e in cast]
        return {"total": len(records), "offset": offset, "records": records[offset:offset + limit]}

    def catalogue_read(self, path, offset=0):
        """/assets: the module's records, a page at a time, each as a leaf. /assets/<id>: one record; /assets/<id>/<field>:
        one field of it."""
        parts = [p for p in str(path).split("/") if p][1:]
        if not parts:
            page = self.catalogue(offset, runs.PAGE)
            return {"path": CATALOGUE, "folder": True, "total": page["total"], "offset": page["offset"], "scope": "catalogue",
                    "leaves": [{"path": "/assets/" + r["id"], "value": {k: r[k] for k in ("name", "kind", "origin") if k in r}}
                               for r in page["records"]]}
        row, key = self._record(parts[0])
        if row is None:
            return {"path": path, "missing": True}
        source = _source(row) if key == "item" else row["made_from"]
        record = record_of(row, key, public_ids(self.db, "generations", [source] if source else []))
        if len(parts) > 1:
            if parts[1] not in record or len(parts) > 2:
                return {"path": path, "missing": True}
            return {"path": path, "value": record[parts[1]], "scope": "catalogue"}
        return {"path": path, "value": record, "scope": "catalogue"}

    def catalogue_write(self, path, value):
        """/assets/<id>/facts: its facts, merged into what it has. Nothing else of a record is written."""
        parts = [p for p in str(path).split("/") if p][1:]
        if len(parts) != 2 or parts[1] != "facts":
            raise runs.RunError("In the catalogue only /assets/<id>/facts is written.")
        if not isinstance(value, dict):
            raise runs.RunError("facts is an object, like {\"has_person\": true, \"scene\": \"night market\"}.")
        row, key = self._record(parts[0])
        if row is None:
            raise runs.RunError("There is nothing at /assets/{}.".format(parts[0]))
        if self.project and self.role not in WRITE_ROLES:
            raise runs.RunError("The catalogue is read only for you in this project.")
        facts = dict(_facts(row), **clean_facts(value))
        text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        if len(text) > MAX_FACTS:
            raise runs.RunError("These facts are too long ({:,} characters; at most {:,}).".format(len(text), MAX_FACTS))
        table = "assets" if key == "asset" else "generations"
        with as_everyone():
            self.db.run("UPDATE {} SET facts = ? WHERE id = ?".format(table), (text, row["id"]))
        return {"path": "/assets/{}/facts".format(parts[0]), "characters": len(text), "scope": "catalogue"}

    def _record(self, name):
        """(row, "item" or "asset") for /assets/<name>, when this user may see it, else (None, None). <name> is a record's
        twelve-hex id; a library id (42) or an entry's (a42), as the agent's other tools name them, is taken too."""
        name = str(name or "")
        found = None
        with as_everyone():
            if PUBLIC.fullmatch(name):
                for table, key in (("generations", "item"), ("assets", "asset")):
                    row = self.db.one("SELECT * FROM {} WHERE public_id = ?".format(table), (name,))
                    if row is not None:
                        found = (row, key)
                        break
            if found is None:
                match = re.fullmatch(r"(a?)(\d{1,12})", name)
                if match:
                    table, key = ("assets", "asset") if match.group(1) else ("generations", "item")
                    row = self.db.one("SELECT * FROM {} WHERE id = ?".format(table), (int(match.group(2)),))
                    found = (row, key) if row is not None else None
        if found is None:
            return None, None
        row, key = found
        if not row["public_id"]:
            row = dict(row, public_id=public_ids(self.db, "generations" if key == "item" else "assets", [row["id"]])[row["id"]])
        if row["user_id"] == self.user_id:
            return row, key
        place = row["project_id"] if "project_id" in row.keys() else None
        if place and sharing.role_in(self.db, self.user_id, place)[0]:
            return row, key
        return None, None


def _under(path, folder):
    path = str(path or "").strip()
    return path == folder or path.startswith(folder + "/")


def slug(name):
    """A name as a path part: "Violet (pajamas)" -> violet_pajamas."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(name or "").lower())).strip("_")[:40]


def public_ids(db, table, ids):
    """{id: public id} for these rows of `table` (generations or assets), giving each that has none a new one."""
    ids = sorted({int(i) for i in ids if isinstance(i, int) or str(i).isdigit()})
    if not ids:
        return {}
    out = {}
    with as_everyone():
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            for row in db.all("SELECT id, public_id FROM {} WHERE id IN ({})".format(table, ", ".join("?" * len(chunk))), chunk):
                out[row["id"]] = row["public_id"]
        for row_id, given in list(out.items()):
            if not given:
                given = _new_public_id(db)
                db.run("UPDATE {} SET public_id = ? WHERE id = ? AND public_id = ''".format(table), (given, row_id))
                out[row_id] = db.one("SELECT public_id FROM {} WHERE id = ?".format(table), (row_id,))["public_id"]
    return out


def _new_public_id(db):
    while True:
        found = secrets.token_hex(6)
        if not any(db.one("SELECT 1 FROM {} WHERE public_id = ?".format(t), (found,)) for t in ("generations", "assets")):
            return found


def _facts(row):
    try:
        found = json.loads(row["facts"] or "{}")
    except (ValueError, KeyError, IndexError):
        return {}
    return found if isinstance(found, dict) else {}


def clean_facts(value):
    """The facts given, with the suggested keys checked for their kind; other keys are kept as they are (short)."""
    facts = {}
    for key, fact in value.items():
        key = re.sub(r"[^a-z0-9_]", "", str(key).lower())[:40]
        if not key:
            continue
        kind = FACT_KEYS.get(key)
        if kind is dict and isinstance(fact, list):   # a set given as a list: {"name": true} for each
            fact = {str(v): True for v in fact}
        if kind and not isinstance(fact, kind):
            raise runs.RunError("{} is {}.".format(key, {bool: "true or false", dict: "an object", str: "a text"}[kind]))
        facts[key] = fact
    return facts


def _source(row):
    """The library id an item was made from (a frame from a video, a trim of a clip, a clip that starts on a picture)."""
    settings = _json(row["settings"])
    for key in SOURCE_KEYS:
        value = settings.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def origin_of(workflow):
    """How an item came to be, by what it was filed under: generated, upload, import, or the edit that made it."""
    workflow = str(workflow or "")
    if workflow == "upload/file":
        return "upload"
    if workflow == "upload/link":
        return "import"
    if workflow.startswith("edit/"):
        return workflow.split("/", 1)[1]
    return "generated"


def record_of(row, key, sources=None):
    """A catalogue record, as Frameo's memory keeps one: its id, what it is, how it was made and from what, its file and
    what is known about it. `sources`: {library id: public id} to name what it was made from."""
    sources = sources or {}
    # The file's own name, without what the studio put before it when it was stored ("upload_20261031_092446_").
    name = re.sub(r"^upload_\d{8}_\d{6}_", "", str(row["filename"] or "").replace("\\", "/").rsplit("/", 1)[-1])
    mime = mimetypes.guess_type(name)[0] or ""
    if key == "asset":
        return {"id": row["public_id"], "entry": row["id"], "name": row["name"], "kind": row["kind"], "origin": "neuralcore",
                "type": TYPE_NAMES.get(row["tag"], row["tag"]), "visual": row["about"], "use": row["use_note"],
                "always": bool(row["always"]), "made_from": sources.get(row["made_from"], "") if row["made_from"] else "",
                "filename": name, "mime_type": mime, "url": "/api/kit/{}/file".format(row["id"]),
                "made": _when(row["created"]), "facts": _facts(row)}
    settings, context = _json(row["settings"]), _json(row["context"])
    review = _json(row["review"]) if row["review"] else {}
    source = _source(row)
    workflow = row["workflow"]
    origin = origin_of(workflow)
    record = {"id": row["public_id"], "item": row["id"], "name": row["name"], "kind": row["kind"],
              "origin": origin, "tool": workflow,
              "model": str(settings.get("workflow_title") or workflow.rsplit("/", 1)[-1]) if origin == "generated" else "",
              "source_asset_id": sources.get(source, "") if source else "",
              "prompt": str(settings.get("prompt") or _first_prompt(settings))[:1500], "shows": row["about"],
              "filename": name, "mime_type": mime, "url": "/api/library/{}/file".format(row["id"]),
              "duration": context.get("duration"), "size": row["size"],
              "review": review.get("summary") or ("passed" if review.get("passed") else review.get("problem") or ""),
              "rating": {1: "liked", -1: "disliked"}.get(row["rating"], ""), "run": row["run"] or "",
              "made": _when(row["created"]), "facts": _facts(row)}
    return {k: v for k, v in record.items() if v not in (None, "", {}) or k in ("id", "name", "kind", "origin")}


TYPE_NAMES = {"character": "character", "background": "location", "prop": "prop", "outfit": "outfit", "voice": "voice",
              "style": "style", "script": "script"}


def _when(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(seconds or 0))


def _first_prompt(settings):
    values = settings.get("values") if isinstance(settings.get("values"), dict) else {}
    return next((v for v in values.values() if isinstance(v, str) and len(v) > 20), "")


def _json(text):
    try:
        found = json.loads(text or "{}")
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


# -- takes: a step's result kept where the agent said (a plan step's "save_to") ------------------------------------------

def slot_of(core_, path):
    """What a step keeps to know where its result goes, checked now: {"user", "run", "path"}. Raises RunError."""
    place = core_._writable(path)
    return {"user": place.user_id, "run": place.run, "path": place.path}


def keep_take(db, job_user_id, slot, item_id, writer="studio"):
    """A finished job's result at slot's path: <path>/item = {"url", "item", "at"}, "url" a reference to its record in
    the catalogue; what was there before moves to <path>/takes/<k>, so earlier tries stay. The slot is checked again here,
    for the job's user. Returns the path written, or None when the slot is not one this user may write."""
    if not isinstance(slot, dict):
        return None
    run, owner, path = str(slot.get("run") or ""), slot.get("user"), str(slot.get("path") or "")
    found = re.fullmatch(r"ep-(\d{1,12})", run)
    if found:
        role, _, top = sharing.role_in(db, job_user_id, int(found.group(1)))
        if role not in WRITE_ROLES or top["user_id"] != owner:
            return None
    elif owner != job_user_id or not runs.RUN.match(run):
        return None
    try:
        path = runs.clean_path(path)
        if runs._protected(path) or _under(path, CATALOGUE) or _under(path, CAST):
            return None
        public = public_ids(db, "generations", [item_id]).get(item_id, "")
        with as_everyone():
            before = runs.read(db, owner, run, path + "/item")
            if before.get("value") is not None:
                taken = runs.children(db, owner, run, path + "/takes")
                runs.write(db, owner, run, "{}/takes/{}".format(path, len(taken) + 1), before["value"], writer)
            runs.write(db, owner, run, path + "/item", {"url": "$state:/assets/{}/url".format(public), "item": item_id,
                                                        "at": round(time.time())}, writer)
    except runs.RunError:
        return None
    return path + "/item"
