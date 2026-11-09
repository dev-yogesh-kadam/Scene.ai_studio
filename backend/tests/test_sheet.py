"""An asset sheet brought into NeuralCore (sheet.py): its columns found by name or by what they hold, each row's picture
fetched and kept under its name and type with its notes, looks linked, and what failed said with its row."""

import asyncio
import json
import struct
import zlib

import pytest

from scene import fetch, kit, sheet
from test_agent_shots import hosted
from test_api import register

SHEET = """type,name,image_link,notes
character,Maya Rao - Face Reference,https://cdn.example.com/a.png,"Base face reference, no mask"
character,Maya Rao - Mask Reference,https://cdn.example.com/b.jpeg,Silver half-mask over the left eye
character,Maya Rao - Party Servant,https://cdn.example.com/c.png,"Gray servant dress + mask (Scenes 2–5)"
character,Young Maya - Age 9 (Flashback),https://cdn.example.com/d.png,Birthday frock
character,House Maid,https://img.example.com/?output=webp&url=x,Ties the mask (Scene 1)
character,Guest 2,https://cdn.example.com/gone.png,Spreads the rumour
location,Rao Garden - Night,https://cdn.example.com/e.png,"Aftermath: overturned chairs"
location,Maya's Attic Room - Night,https://cdn.example.com/f.png,Iron cot
location,Maya's Attic Room - Day (Flashback),https://cdn.example.com/g.png,Golden memory
prop,Captain's Sword,https://cdn.example.com/h.png,"Wolf-head pommel, black scabbard (Scene 3)"
prop,Captain's Sword,https://cdn.example.com/h2.png,the same name again
prop,No Link Here,,nothing to fetch
"""


def png(seed):
    """A tiny PNG of its own for each link, so no two are one picture."""
    raw = b"\x00" + bytes([seed % 256, (seed * 7) % 256, (seed * 13) % 256])
    chunk = lambda tag, data: struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24


async def fake_fetch(url, client=None):
    if "gone" in url:
        raise fetch.FetchError("The link answered 404.")
    return (WEBP if "webp" in url else png(sum(map(ord, url)))), "image", url


def test_the_columns_are_found_by_their_names_or_by_what_they_hold():
    rows, left = sheet.parse(SHEET)
    assert [r["name"] for r in rows][:2] == ["Maya Rao - Face Reference", "Maya Rao - Mask Reference"]
    assert {r["type"] for r in rows} == {"character", "background", "prop"}   # a location is kept as NeuralCore's "background"
    assert rows[0]["notes"] == "Base face reference, no mask" and rows[0]["row"] == 2
    assert [(l["row"], l["reason"]) for l in left] == [(12, "row 11 has the same name"), (13, "its link is not a web link")]
    # other names for the columns, tabs between them, and links in a column called something else
    tabbed, _ = sheet.parse("Asset Name\tCategory\tReference image\tDescription\nMaya\tCharacter\thttps://x.com/m.png\tRed scarf\n")
    assert tabbed == [{"row": 2, "type": "character", "name": "Maya", "link": "https://x.com/m.png", "notes": "Red scarf"}]
    found, _ = sheet.parse("title,where\nKitchen,https://x.com/k.png\n")
    assert found[0]["link"] == "https://x.com/k.png" and found[0]["type"] == "other"
    with pytest.raises(sheet.SheetError, match="links"):
        sheet.parse("name,notes\nMaya,red scarf\n")
    with pytest.raises(sheet.SheetError, match="no rows"):
        sheet.parse("name,link\n")


def test_a_group_with_no_base_entry_hangs_on_its_face_reference():
    rows, _ = sheet.parse(SHEET)
    entries = [{"id": i, "name": r["name"], "tag": r["type"]} for i, r in enumerate(rows, start=1)]
    found = {name: (base["name"], variant) for name, (base, variant) in sheet.looks(rows, entries).items()}
    assert found == {"Maya Rao - Mask Reference": ("Maya Rao - Face Reference", "Mask Reference"),
                     "Maya Rao - Party Servant": ("Maya Rao - Face Reference", "Party Servant")}
    # an entry named as the base itself wins, and then every row of the group is its look
    entries.append({"id": 99, "name": "Maya Rao", "tag": "character"})
    found = sheet.looks(rows, entries)
    assert {base["id"] for base, _ in found.values()} == {99} and len(found) == 3


def test_a_sheet_comes_into_neuralcore_with_its_names_types_notes_and_looks(client, monkeypatch):
    me = register(client)
    project = client.post("/api/projects", json={"name": "Opening"}).json()["id"]
    monkeypatch.setattr(sheet.fetch, "fetch", fake_fetch)
    response = client.post("/api/kit/sheet", files={"file": ("assets.csv", SHEET.encode("utf-8"), "text/csv")},
                           data={"project_id": str(project)})
    assert response.status_code == 200, response.text
    done = response.json()
    assert len(done["added"]) == 9 and all(a["new"] for a in done["added"])
    assert done["failed"] == [{"row": 7, "name": "Guest 2", "reason": "The link answered 404."}]
    assert len(done["left_out"]) == 2 and len(done["looks"]) == 2
    entries = {e["name"]: e for e in kit.entries(client.app.state.db, me["id"], project)}
    face = entries["Maya Rao - Face Reference"]
    assert entries["Maya Rao - Party Servant"]["look_of"] == face["id"]
    assert entries["Maya Rao - Party Servant"]["variant"] == "Party Servant"
    assert entries["Maya Rao - Party Servant"]["from_scene"] == 2   # "(Scenes 2–5)": the look from scene 2
    assert entries["Maya Rao - Mask Reference"]["from_scene"] is None   # its notes name no scene
    assert entries["Captain's Sword"]["type"] == "prop" and entries["Rao Garden - Night"]["type"] == "location"
    assert entries["House Maid"]["use_note"].endswith("Ties the mask (Scene 1)")
    assert entries["House Maid"]["filename"].endswith(".webp")   # named by what it is, not by the link
    assert entries["House Maid"]["origin"] == "import"
    # the same sheet again adds nothing new and fetches nothing, even where the CDN would now send other bytes
    asked = []

    async def other_bytes(url, client=None):
        asked.append(url)
        return png(len(asked) + 500), "image", url
    monkeypatch.setattr(sheet.fetch, "fetch", other_bytes)
    again = client.post("/api/kit/sheet", json={"project_id": project, "text": SHEET}).json()
    assert [a["name"] for a in again["added"] if a["new"]] == ["Guest 2"] and len(kit.entries(client.app.state.db, me["id"], project)) == 10
    assert asked == ["https://cdn.example.com/gone.png"]   # only the row that failed before is tried again, and comes in now
    # outside a project there is no NeuralCore to bring it into
    assert client.post("/api/kit/sheet", json={"text": SHEET}).status_code == 400


def attach(client, me, project, name="assets.csv", text=SHEET):
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, project_id, workflow, kind, name, filename, settings, context, created, about) "
        "VALUES (?, ?, 'upload/file', 'text', 'Asset sheet', ?, '{}', '{}', 1, 'A table.')", (me["id"], project, name))


def test_a_sheet_attached_to_a_message_is_the_modules_references_before_the_agent_plans(client, monkeypatch):
    me = register(client)
    module = client.post("/api/projects", json={"name": "Opening"}).json()["id"]
    sheet_id = attach(client, me, module)
    monkeypatch.setattr(sheet.fetch, "fetch", fake_fetch)
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "In.", "steps": []})
    # the words never point at the file: it is brought in all the same
    plan = client.post("/api/agent/plan", json={"instruction": "make scene 2", "project_id": module, "selection": [sheet_id]}).json()
    entries = {e["name"]: e for e in kit.entries(client.app.state.db, me["id"], module)}
    assert len(entries) == 9 and entries["Maya Rao - Party Servant"]["from_scene"] == 2
    asked = "\n".join(m["content"] for m in seen[-1] if m["role"] == "user")
    line = next(json.loads(l) for l in asked.splitlines() if l.startswith("{") and '"sheet"' in l)
    assert "9 new" in line["sheet"] and "Maya Rao - Party Servant is the look \"Party Servant\" of Maya Rao - Face Reference, from scene 2" in line["sheet"]
    assert "row 7 Guest 2: The link answered 404." in line["sheet"]
    assert '"look_of": "Maya Rao - Face Reference"' in asked and '"from_scene": 2' in asked   # NeuralCore says whose look it is
    assert any("Brought 9 entries from Asset sheet into NeuralCore" in a.get("text", "") for a in plan["activity"])
    # the next message with it brings nothing new and fetches only the row that failed
    async def only_the_failed(url, client=None):
        assert "gone" in url, url
        return await fake_fetch(url)
    monkeypatch.setattr(sheet.fetch, "fetch", only_the_failed)
    client.post("/api/agent/plan", json={"instruction": "go on", "project_id": module, "selection": [sheet_id]})
    assert len(kit.entries(client.app.state.db, me["id"], module)) == 9


def test_the_agent_brings_in_a_pasted_sheet_with_its_tool(client, monkeypatch):
    me = register(client)
    module = client.post("/api/projects", json={"name": "Opening"}).json()["id"]
    monkeypatch.setattr(sheet.fetch, "fetch", fake_fetch)
    seen = hosted(monkeypatch, client, {"tool": "book_import", "value": SHEET}, {"tool": "finish", "reply": "In.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "these are our assets", "project_id": module})
    told = next(m["content"] for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Result of book_import"))
    found = json.loads(told.split("\n", 1)[1])
    assert len(found["added"]) == 9 and found["failed"][0]["name"] == "Guest 2" and len(found["looks_linked"]) == 2
    assert len(kit.entries(client.app.state.db, me["id"], module)) == 9


def test_a_table_that_is_no_asset_sheet_stays_an_attached_text(client, monkeypatch):
    me = register(client)
    module = client.post("/api/projects", json={"name": "Opening"}).json()["id"]
    shots = attach(client, me, module, "shots.csv", "shot,action,seconds\n1,Maya runs,4\n2,Maya hides,3\n")
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "use @1", "project_id": module, "selection": [shots]})
    assert not kit.entries(client.app.state.db, me["id"], module)
    assert '"sheet"' not in "\n".join(m["content"] for m in seen[-1] if m["role"] == "user")


def test_a_csv_is_taken_as_a_text_when_it_is_attached():
    from scene.references import text_kind
    assert text_kind("Asset sheet 1.3 full - Sheet1.csv") == "text" and text_kind("shots.tsv") == "text"
    assert fetch.filename_for("https://img.example.com/?output=webp&url=x", "image", WEBP) == "image.webp"
    assert fetch.filename_for("https://cdn.example.com/a.png", "image", WEBP) == "a.png"   # a link's own name is kept
