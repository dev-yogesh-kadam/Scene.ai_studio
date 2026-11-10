"""Canvas placement (placement.py): numbered shots, boards made by name on first use, stacks of re-renders on a board;
and the resolutions an admin switches off for a kind or a workflow (credits.allowed_resolutions, fit_resolution)."""

import asyncio
import json

import pytest
from fastapi import HTTPException

from scene import db as database, placement
from scene.api import studio
from scene.comfy import workflows
from test_api import JOB, console, post_job, register

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def project(client, name="Film"):
    return client.post("/api/projects", json={"name": name}).json()["id"]


def finish(client, tmp_path, user_id, project_id, name, workflow="image/z", **settings):
    """A job that has just finished, recorded as jobs.py records one. Returns the id of the library item it made."""
    target = tmp_path / (name + ".png")
    target.write_bytes(PNG)
    job = {"id": name, "user_id": user_id, "workflow": workflow, "name": name, "summary": "", "started": 0,
           "project_id": project_id, "settings": dict(settings)}
    client.app.state.db.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, status, created, project_id) "
                            "VALUES (?, ?, ?, ?, 'image', '{}', 'running', 0, ?) ON CONFLICT (id) DO NOTHING",
                            (name, user_id, name, workflow, project_id))   # a result is always its job's
    client.app.state.jobs._record(job, "image", target, {})
    return client.app.state.db.one("SELECT id FROM generations WHERE job_id = ?", (name,))["id"]


def test_the_settings_of_a_placement_are_cleaned():
    assert placement.clean_shot_number(3) == 3 and placement.clean_shot_number(" 12 ") == 12
    assert placement.clean_shot_number(0) is None and placement.clean_shot_number(True) is None
    assert placement.clean_shot_number(1000) is None and placement.clean_shot_number("two") is None
    assert placement.clean_board("  characters ") == "Characters"   # the usual names keep their spelling
    assert placement.clean_board("Mood   board") == "Mood board" and placement.clean_board("<b>") == "b"
    assert placement.clean_board("") is None and placement.clean_board(5) is None
    assert len(placement.clean_board("x" * 90)) == placement.MAX_NAME
    assert placement.clean_group("step 3!") == "step3" and placement.clean_group(None) is None
    # What a result is a version of: its group, else its shot, else its place in the state, else its number.
    assert placement.group_of({"placement_group": "final", "shot": {"id": "s1"}}, 9) == "final"
    assert placement.group_of({"shot": {"id": "s1", "take": 2}, "shot_number": 4}, 9) == "shot:s1"
    assert placement.group_of({"save_to_state": "/videos/3"}, 9) == "state:/videos/3"
    assert placement.group_of({"shot_number": 4}, 9) == "number:4"
    assert placement.group_of({}, 9) == "item:9"


def test_a_board_is_made_on_first_use_and_a_re_render_stacks_on_it(client, tmp_path):
    me = register(client)
    film = project(client)
    hero = finish(client, tmp_path, me["id"], film, "hero", board="characters", placement_group="maya")
    assert client.get("/api/library/placement?project=%d" % film).json()["boards"][0]["name"] == "Characters"
    final = finish(client, tmp_path, me["id"], film, "cut1", board="Outputs", shot={"id": "s1", "take": 1}, shot_number=1)
    again = finish(client, tmp_path, me["id"], film, "cut2", board="Outputs", shot={"id": "s1", "take": 2}, shot_number=1)
    other = finish(client, tmp_path, me["id"], film, "cut3", board="Outputs", shot={"id": "s2", "take": 1}, shot_number=2)
    plain = finish(client, tmp_path, me["id"], film, "plain")   # names no board: the canvas puts it in a shot row
    mood = finish(client, tmp_path, me["id"], film, "mood", board="Mood board")

    shown = client.get("/api/library/placement?project=%d" % film).json()
    assert shown["names"] == list(placement.BOARDS)
    boards = {b["name"]: b["stacks"] for b in shown["boards"]}
    assert list(boards) == ["Characters", "Outputs", "Mood board"]   # in the order they were first used
    assert boards["Characters"] == [{"group": "maya", "items": [hero]}]
    # The re-render of shot s1 is on top of the first; shot s2 is a card of its own.
    assert [(s["group"], s["items"], s["shot_number"]) for s in boards["Outputs"]] == [("shot:s1", [again, final], 1), ("shot:s2", [other], 2)]
    assert boards["Mood board"] == [{"group": "item:%d" % mood, "items": [mood]}]
    assert all(plain not in s["items"] for stacks in boards.values() for s in stacks)

    # A deleted take leaves its stack; the stack that is left empty goes, the board stays.
    client.delete("/api/library/%d" % again)
    client.delete("/api/library/%d" % mood)
    boards = {b["name"]: b["stacks"] for b in client.get("/api/library/placement?project=%d" % film).json()["boards"]}
    assert boards["Outputs"][0]["items"] == [final] and boards["Mood board"] == []


def test_the_whole_film_goes_on_final_video_and_a_new_cut_stacks_on_it(client, tmp_path):
    me = register(client)
    film = project(client)
    first = finish(client, tmp_path, me["id"], film, "film1", workflow="edit/film", run="abcdefghijkl")
    again = finish(client, tmp_path, me["id"], film, "film2", workflow="edit/assemble", board="Outputs")   # Outputs: still its own board
    finish(client, tmp_path, me["id"], film, "trim1", workflow="edit/trim")   # a working file: on no board
    boards = client.get("/api/library/placement?project=%d" % film).json()["boards"]
    assert [b["name"] for b in boards] == ["Final video"]
    assert boards[0]["stacks"] == [{"group": "final", "items": [again, first]}]
    named = finish(client, tmp_path, me["id"], film, "film3", workflow="edit/film", board="Cuts")   # a board it names wins
    assert [b["name"] for b in client.get("/api/library/placement?project=%d" % film).json()["boards"]] == ["Final video", "Cuts"]
    assert named


def test_a_runs_film_is_listed_and_its_working_files_are_not(client, tmp_path):
    me = register(client)
    film = project(client)
    run = "abcdefghijkl"
    whole = finish(client, tmp_path, me["id"], film, "film1", workflow="edit/film", run=run)
    placed = finish(client, tmp_path, me["id"], film, "subs1", workflow="edit/subtitles", run=run, board="Outputs")
    trim = finish(client, tmp_path, me["id"], film, "trim1", workflow="edit/trim", run=run)
    listed = lambda **params: [i["id"] for i in client.get("/api/library", params=params).json()["items"]]
    assert set(listed(project=film)) == {whole, placed}
    assert listed(run=run) == [trim]
    # a film made before this was filed under its run, and comes back when the studio starts
    client.app.state.db.run("UPDATE generations SET run = ? WHERE id = ?", (run, whole))
    assert whole not in listed(project=film)
    database._films_shown(client.app.state.db)
    assert whole in listed(project=film)


def test_placement_is_the_project_owners_and_goes_with_the_project(client, tmp_path):
    me = register(client)
    film, other = project(client), project(client, "Other")
    finish(client, tmp_path, me["id"], film, "a", board="Props")
    assert client.get("/api/library/placement?project=%d" % other).json()["boards"] == []
    assert client.get("/api/library/placement?project=999").status_code == 404
    row = client.app.state.db.one("SELECT user_id FROM boards WHERE kind = 'placement' AND project_id = ?", (film,))
    assert row["user_id"] == me["id"]
    client.delete("/api/projects/%d" % film)
    assert client.app.state.db.one("SELECT 1 FROM boards WHERE kind = 'placement' AND project_id = ?", (film,)) is None


def test_a_job_keeps_its_shot_number_and_board_cleaned(client):
    register(client)
    job_id = post_job(client, shot_number="4", board="  outputs ", placement_group="shot 4", shot={"id": "S4", "take": 2}).json()["id"]
    settings = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job_id)["settings"]
    assert (settings["shot_number"], settings["board"], settings["placement_group"]) == (4, "Outputs", "shot4")
    assert settings["shot"] == {"id": "s4", "take": 2}
    job_id = post_job(client, shot_number=-1, board=12).json()["id"]
    settings = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job_id)["settings"]
    assert settings["shot_number"] is None and settings["board"] is None


# ---------------------------------------------------------------- resolutions switched off

def test_switched_off_resolutions_step_down_or_up(client):
    credits = client.app.state.credits
    assert credits.allowed_resolutions("video/x") == [480, 720, 768, 1080]
    credits.set_resolutions_off("video", ["1080"])
    credits.set_resolutions_off("video/x", ["720", "nonsense"])
    assert credits.resolutions_off() == {"video": ["1080"], "video/x": ["720"]}
    assert credits.allowed_resolutions("video/x") == [480] and credits.allowed_resolutions("video/y") == [480, 720, 768]
    assert credits.allowed_resolutions("image/z") == [480, 720, 768, 1080]   # another kind is not touched
    assert credits.fit_resolution("video/y", 720) == (720, "")
    used, note = credits.fit_resolution("video/y", 1080)
    assert used == 768 and note == "1080p is switched off for this workflow, so it is made at 768p."
    assert credits.fit_resolution("video/y", 1080, [480, 720, 1080])[0] == 720
    assert credits.fit_resolution("video/x", 720)[0] == 480
    credits.set_resolutions_off("video/x", ["480", "720"])
    assert credits.fit_resolution("video/x", 1440, [480, 1080, 1440]) == (1440, "")   # a size with no tier is not switched
    credits.set_resolutions_off("video", [])
    assert credits.fit_resolution("video/x", 480)[0] == 1080   # nothing below: the smallest above
    credits.set_resolutions_off("video", ["1080"])
    with pytest.raises(ValueError):
        credits.fit_resolution("video/x", 480)
    credits.set_resolutions_off("video/x", [])
    assert credits.resolutions_off() == {"video": ["1080"]}


def test_a_job_at_a_resolution_switched_off_is_made_at_the_next_and_says_so(client):
    register(client)   # the first account: the admin
    desk = console(client)
    assert desk.put("/api/admin/workflows/resolutions", json={"key": "video/h3_all_in_one", "off": ["1080"]}).json() == \
        {"key": "video/h3_all_in_one", "off": ["1080"]}
    assert desk.put("/api/admin/workflows/resolutions", json={"key": "video", "off": ["480", "720", "1080"]}).status_code == 400
    assert desk.put("/api/admin/workflows/resolutions", json={"key": "video/nope", "off": []}).status_code == 404
    assert desk.put("/api/admin/workflows/resolutions", json={"key": "video", "off": ["2160"]}).status_code == 400
    assert desk.get("/api/admin/workflows/resolutions").json()["off"] == {"video/h3_all_in_one": ["1080"]}
    report = desk.get("/api/admin/workflows").json()
    assert next(w for w in report["workflows"] if w["id"] == "video/h3_all_in_one")["resolutions_off"] == ["1080"]

    form = client.get("/api/workflows/video/h3_all_in_one").json()
    assert form["resolutions"] == [480, 720, 768] and form["resolutions_off"] == [1080]
    asked = dict(JOB, values={**JOB["values"], "501:value": 1080})
    quote = client.post("/api/estimate", json=asked).json()
    assert quote["resolution_note"] == "1080p is switched off for this workflow, so it is made at 768p."
    reply = post_job(client, values=asked["values"]).json()
    assert reply["resolution_note"] == quote["resolution_note"]
    settings = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == reply["id"])["settings"]
    assert settings["values"]["501:value"] == 768 and settings["resolution_note"] == reply["resolution_note"]
    assert post_job(client).json()["resolution_note"] == ""   # 720, the default, is on


def test_a_workflow_of_a_fixed_size_steps_down_too(client):
    state = client.app.state
    schema = workflows.describe(asyncio.run(state.catalog.load("video/video_v2v_ltx23_iclora")))
    assert schema["size"]["resolution"] == 720
    state.credits.set_resolutions_off("video", ["720"])
    settings = {"resolution": None}
    assert studio.fit_resolution(state, schema, settings) == "720p is switched off for this workflow, so it is made at 480p."
    assert settings["resolution"] == 480 and settings["resolution_note"]
    settings = {"resolution": 1080}
    assert studio.fit_resolution(state, schema, settings) == "" and settings["resolution"] == 1080 and "resolution_note" not in settings
    state.credits.set_resolutions_off("video", ["480", "720", "1080"])   # (the console refuses this; the studio says so)
    with pytest.raises(HTTPException):
        studio.fit_resolution(state, schema, {"resolution": 720})
    audio = workflows.describe(asyncio.run(state.catalog.load("audio/audio_transcribe")))
    assert studio.fit_resolution(state, audio, {}) == ""   # no resolution to change
