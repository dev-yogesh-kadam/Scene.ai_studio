"""An asset sheet: a table of a production's references, as a spreadsheet exports it (CSV, or TSV), one row an entry:
its type, its name, a link to its picture, and notes. Each row's picture is fetched from its link (fetch.py: public
links only, checked as any link is) and kept in a project's NeuralCore under its name and type, with the notes as how
to use it; NeuralCore describes the picture itself. A row named as a look of another ("Maya - torn sleeve", "Kitchen -
night") is linked to it, as kit.py links any entry so named.

The columns are found by what they are called ("name", "title"; "image_link", "link", "url"; "type", "category";
"notes", "description"), and the links by what they hold when no column is called so.
"""

import asyncio
import csv
import io
import re

from . import fetch, kit

ROWS_MOST = 200
AT_ONCE = 6        # pictures fetched at once
# What each column may be called in the sheets people make, the likeliest first.
COLUMNS = {"name": ("name", "title", "asset name", "asset", "label", "entry"),
           "link": ("image link", "image url", "image", "link", "url", "reference", "ref", "picture", "photo", "file"),
           "type": ("type", "asset type", "category", "kind", "group"),
           "notes": ("notes", "note", "description", "about", "details", "comments", "comment", "continuity")}
# A group's look that says it is the base, when no row is named as the base alone: "Maya - Face Reference".
BASE_LOOK = re.compile(r"^(face\s+)?(ref|reference)$|^(face|base|main|default|master)(\s+(ref|reference|sheet|look))?$", re.IGNORECASE)
LINK = re.compile(r"^https?://\S+$", re.IGNORECASE)
SCENE = re.compile(r"\b(?:scenes?|sc\.?)\s*(\d{1,4})", re.IGNORECASE)   # "(Scenes 2–3)", "Scene 4": the first scene a look is in


class SheetError(ValueError):
    pass


def _said(text):
    return " ".join(str(text or "").replace("_", " ").lower().split())


def parse(text):
    """The rows of a sheet: ([{"row", "type", "name", "link", "notes"}], [{"row", "name", "reason"}] of the rows left
    out). "row" is its row in the spreadsheet, the header being row 1. Raises SheetError when it is not an asset sheet:
    no column of names, or none of links."""
    text = str(text or "").lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    table = [cells for cells in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in cells)]
    if len(table) < 2:
        raise SheetError("The sheet has no rows under its header.")
    head = [_said(c) for c in table[0]]

    def column(what):
        names = COLUMNS[what]
        for name in names:   # a column called exactly so, the likeliest name first
            if name in head:
                return head.index(name)
        for i, said in enumerate(head):   # then one whose name holds it ("Character name", "Reference image")
            if any(re.search(r"\b{}\b".format(re.escape(name)), said) for name in names):
                return i
        return None

    found = {what: column(what) for what in COLUMNS}
    holding = [sum(1 for cells in table[1:] if i < len(cells) and LINK.match(cells[i].strip())) for i in range(len(head))]
    if found["link"] is None or not holding[found["link"]]:   # the column that holds the links, whatever it is called
        best = max(range(len(head)), key=lambda i: holding[i])
        found["link"] = best if holding[best] else None
    if found["link"] is None:
        raise SheetError("No column of the sheet holds links to pictures (http:// or https://).")
    if found["name"] is None or found["name"] == found["link"]:
        raise SheetError("No column of the sheet is the entries' names: call it name or title.")
    rows, left, seen = [], [], {}
    for n, cells in enumerate(table[1:], start=2):
        cell = lambda what: cells[found[what]].strip() if found[what] is not None and found[what] < len(cells) else ""
        name, link = kit.clean_name(cell("name")), cell("link")
        if not name or not LINK.match(link):
            left.append({"row": n, "name": name, "reason": "it has no name" if not name else "its link is not a web link"})
        elif name.lower() in seen:
            left.append({"row": n, "name": name, "reason": "row {} has the same name".format(seen[name.lower()])})
        else:
            seen[name.lower()] = n
            rows.append({"row": n, "type": kit.tag_of(cell("type")), "name": name, "link": link, "notes": cell("notes")})
    if len(rows) > ROWS_MOST:
        raise SheetError("The sheet has {} rows; bring in at most {} at once.".format(len(rows), ROWS_MOST))
    return rows, left


def looks(rows, entries, of_row=None):
    """Which rows are looks of which entry: {row name: (the base's entry, the look's words)}. entries: NeuralCore's, the
    rows among them; of_row: {row name, lower-case: its entry} (by default the entry of that name). A row named
    "<base> - <look>" of a type that has looks is a look of the entry named <base>; when there is none, of the row of
    its group whose look says it is the base ("Maya - Face Reference"), if the group has more than it. Any other row
    stays alone."""
    bases = {(e["tag"], e["name"].lower()): e for e in entries if not e.get("look_of")}
    by_name = of_row or {e["name"].lower(): e for e in entries}
    groups = {}
    for row in rows:
        found = kit.LOOK_NAME.match(row["name"])
        if found and row["type"] in kit.HAS_LOOKS:
            groups.setdefault((row["type"], found.group(1).strip().lower()), []).append((row, found.group(2).strip()))
    out = {}
    for key, members in groups.items():
        base = bases.get(key)
        if base is None:
            heads = [m for m in members if BASE_LOOK.match(m[1])]
            if not heads or len(members) < 2:
                continue
            base = by_name.get(heads[0][0]["name"].lower())
            members = [m for m in members if m is not heads[0]]
        for row, variant in members:
            if base is not None and row["name"].lower() != base["name"].lower():
                out[row["name"]] = (base, variant[:kit.VARIANT_CHARS])
    return out


async def bring_in(db, folder, user_id, project, rows, fetcher=None):
    """Fetch each row's picture and keep it in the project's NeuralCore (user_id: whose NeuralCore it is), then link the
    looks. All the pictures are fetched first, AT_ONCE at a time; a row whose link fails is reported, never guessed. A
    row whose name and type an entry has already is that entry ("new" False), fetched no more.
    Returns {"added": [{"row", "asset", "name", "type", "new"}], "failed": [{"row", "name", "reason"}],
    "looks": [{"name", "look_of", "variant"}]}."""
    fetcher = fetcher or fetch.fetch
    gate = asyncio.Semaphore(AT_ONCE)

    async def one(row):
        async with gate:
            try:
                return row, await fetcher(row["link"]), ""
            except fetch.FetchError as error:
                return row, None, str(error)

    present = kit.entries(db, user_id, project)
    before = {e["id"] for e in present}
    named = {(e["tag"], e["name"].lower()): e for e in present}
    # A row whose entry is there already by its name and type is not fetched again: a CDN may send the same picture
    # as other bytes, and the entry (which shots may use) is never replaced from here.
    there = [(row, named[(row["type"], row["name"].lower())]) for row in rows if (row["type"], row["name"].lower()) in named]
    added = [{"row": row["row"], "asset": e["id"], "name": e["name"], "type": e["type"], "new": False} for row, e in there]
    failed, skip = [], {row["row"] for row, _ in there}
    for row, got, error in await asyncio.gather(*(one(r) for r in rows if r["row"] not in skip)):
        if got is None:
            failed.append({"row": row["row"], "name": row["name"], "reason": error})
            continue
        data, kind, final = got
        tag = "voice" if kind == "audio" else row["type"]
        asset = kit.add(db, folder, user_id, project, data, fetch.filename_for(final, kind, data), kind, row["name"], tag,
                        use_note=row["notes"], origin="import")
        current = kit.entry(db, user_id, asset)
        if asset in before and row["notes"] and not current["use_note"]:
            # the same picture was there already: it keeps its name, and takes the sheet's notes when it had none
            current = kit.update(db, user_id, asset, {"use_note": row["notes"]})
        added.append({"row": row["row"], "asset": asset, "name": current["name"], "type": current["type"], "new": asset not in before})
    entries = kit.entries(db, user_id, project)
    row_at, entry_of = {r["row"]: r for r in rows}, {e["id"]: e for e in entries}
    of_row = {row_at[a["row"]]["name"].lower(): entry_of[a["asset"]] for a in added}   # each row's entry, by the row's name
    linked = []
    for name, (base, variant) in looks([r for r in rows if r["name"].lower() in of_row], entries, of_row).items():
        current = of_row[name.lower()]
        if current.get("look_of") or current["id"] == base["id"]:
            continue   # linked already (when it was added, or by hand): left as it is
        asset = current["id"]
        scene = SCENE.search(current.get("use_note") or "")   # the scene the notes first put the look in
        try:
            kit.update(db, user_id, asset, {"look_of": base["id"], "variant": variant,
                                            **({"from_scene": int(scene.group(1))} if scene and int(scene.group(1)) else {})})
        except ValueError:
            continue
        linked.append({"name": name, "look_of": base["name"], "variant": variant,
                       **({"from_scene": int(scene.group(1))} if scene and int(scene.group(1)) else {})})
    return {"added": added, "failed": failed, "looks": linked}


def told(done, left, called):
    """What the agent is told of a sheet brought in with a message: the entries now in NeuralCore and what failed."""
    by_type = {}
    for a in done["added"]:
        by_type.setdefault(a["type"], []).append(a["name"])
    new = sum(1 for a in done["added"] if a["new"])
    parts = ["an asset sheet: its rows are now this module's NeuralCore entries ({} new, {} there already): {}".format(
        new, len(done["added"]) - new, "; ".join("{}: {}".format(t, ", ".join(n)) for t, n in by_type.items()))]
    if done["looks"]:
        parts.append("looks linked: " + "; ".join("{} is the look \"{}\" of {}{}".format(
            l["name"], l["variant"], l["look_of"], ", from scene {}".format(l["from_scene"]) if l.get("from_scene") else "")
            for l in done["looks"]))
    misses = done["failed"] + left
    if misses:
        parts.append("not brought in: " + "; ".join("row {} {}: {}".format(m["row"], m["name"] or "(no name)", m["reason"]) for m in misses))
    parts.append("These are the references of this module's work: give each shot the entries its scene needs, by their "
                 "names (each character's look for that scene, its location, the props in it), as their notes say. "
                 "Tell the user in a line what came in from {}, and what did not.".format(called))
    return ". ".join(parts) + "."
