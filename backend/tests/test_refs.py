"""Every project and module has an id of its own for its links (refs.py): PRJ... for a project, MOD... for a module.
A link with one opens that place for anyone in the project, and for no one else."""

from scene import refs
from conftest import POSTGRES
from scene.db import Database
from test_api import ADMIN
from test_sharing import BOB, as_, setup


def test_projects_and_modules_get_ids_that_their_links_find(client):
    _, film = setup(client)
    made = client.post("/api/projects", json={"name": "Episode 1", "parent_id": film}).json()
    rows = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    top, module = rows[film], rows[made["id"]]
    assert refs.looks_like(top["ref"], refs.PROJECT) and refs.looks_like(module["ref"], refs.MODULE)
    assert made["ref"] == module["ref"] and module["parent_ref"] == top["ref"] and top["parent_ref"] is None
    page = client.get("/api/projects/{}".format(film)).json()
    assert page["project"]["ref"] == top["ref"] and [m["ref"] for m in page["modules"]] == [top["ref"], module["ref"]]
    assert client.get("/api/projects/{}/analytics".format(film)).json()["project"]["ref"] == top["ref"]

    assert client.get("/api/refs/" + module["ref"]).json() == {"id": made["id"], "ref": module["ref"], "parent_id": film,
                                                               "parent_ref": top["ref"]}
    assert client.get("/api/refs/" + top["ref"]).json()["parent_id"] is None
    assert client.get("/api/refs/PRJ0000000000000").status_code == 404
    assert client.get("/api/refs/nonsense").status_code == 404

    copy = client.post("/api/projects/{}/duplicate".format(film)).json()
    assert refs.looks_like(copy["ref"], refs.PROJECT) and copy["ref"] != top["ref"]
    assert all(refs.looks_like(p["ref"]) for p in client.get("/api/projects").json()["projects"])


def test_a_link_opens_only_for_people_in_the_project(client):
    _, film = setup(client)
    ref = client.get("/api/projects").json()["projects"][0]["ref"]
    as_(client, BOB)
    assert client.get("/api/refs/" + ref).status_code == 404               # not in it: no such project
    as_(client, ADMIN)
    client.post("/api/projects/{}/members".format(film), json={"people": [{"email": BOB["email"], "role": "viewer"}]})
    as_(client, BOB)
    assert client.get("/api/refs/" + ref).json()["id"] == film


def test_pages_answer_at_addresses_with_ids(client):
    for path in ("/project/PRJabcdefghijklm", "/canvas/PRJabcdefghijklm", "/canvas/PRJabcdefghijklm/module/MODabcdefghijklm",
                 "/analytics/PRJabcdefghijklm"):
        answer = client.get(path)
        assert answer.status_code == 200 and "<html" in answer.text.lower()


def test_projects_from_before_ids_are_given_theirs(database):
    db = database
    user = db.run("INSERT INTO users (name, email, password_hash, created) VALUES ('A', 'a@example.com', 'x', 0)")
    top = db.run("INSERT INTO projects (user_id, name, created) VALUES (?, 'Old', 0)", (user,))
    module = db.run("INSERT INTO projects (user_id, name, created, parent_id) VALUES (?, 'Old module', 0, ?)", (user, top))
    db = Database(POSTGRES)   # the app starting again
    found = {r["id"]: r["ref"] for r in db.all("SELECT id, ref FROM projects")}
    assert refs.looks_like(found[top], refs.PROJECT) and refs.looks_like(found[module], refs.MODULE)
    db.close()
