"""The library a page at a time (limit, cursor), what one job made (job), and one item on its own (GET /api/library/{id}),
for the studio's pages that show only part of it. Without them the list is what it always was."""

import time

from conftest import a_job

from test_api import register


def fill(client, me, count, same_time=False):
    now = time.time()
    for n in range(3):
        a_job(client.app.state.db, "job{}".format(n), me["id"])
    for n in range(count):
        client.app.state.db.run(
            "INSERT INTO generations (user_id, job_id, workflow, kind, name, filename, settings, context, created) "
            "VALUES (?, ?, 'image/x', 'image', ?, ?, '{\"prompt\": \"p\"}', '{}', ?)",
            (me["id"], "job{}".format(n % 3), "Frame {}".format(n), "f{}.png".format(n), now if same_time else now + n))


def test_pages_cover_the_whole_list_once_newest_first(client):
    me = register(client)
    fill(client, me, 25)
    seen, cursor = [], ""
    while True:
        page = client.get("/api/library?limit=10" + ("&cursor=" + cursor if cursor else "")).json()
        assert len(page["items"]) <= 10 and "settings" in page["items"][0] and page["items"][0]["mine"] is True
        seen += [i["name"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["Frame {}".format(n) for n in range(24, -1, -1)]
    # Without a limit: the list as before, with no cursor.
    assert set(client.get("/api/library").json()) == {"items"}


def test_items_made_at_the_same_moment_are_neither_skipped_nor_repeated(client):
    me = register(client)
    fill(client, me, 7, same_time=True)
    first = client.get("/api/library?limit=3").json()
    rest = client.get("/api/library?limit=10&cursor=" + first["next_cursor"]).json()
    names = [i["name"] for i in first["items"] + rest["items"]]
    assert sorted(names) == sorted("Frame {}".format(n) for n in range(7)) and rest["next_cursor"] is None


def test_a_page_has_at_most_200_and_a_bad_cursor_is_refused(client):
    me = register(client)
    fill(client, me, 205)
    assert len(client.get("/api/library?limit=5000").json()["items"]) == 200
    assert client.get("/api/library?limit=5&cursor=nonsense").status_code == 400


def test_what_one_job_made(client):
    me = register(client)
    fill(client, me, 6)
    made = client.get("/api/library?job=job1&limit=10").json()["items"]
    assert {i["name"] for i in made} == {"Frame 1", "Frame 4"}


def test_one_item_as_the_list_gives_it(client):
    me = register(client)
    fill(client, me, 2)
    listed = client.get("/api/library").json()["items"][0]
    one = client.get("/api/library/{}".format(listed["id"]))
    assert one.status_code == 200 and one.json() == listed
    assert client.get("/api/library/999999").status_code == 404


def test_someone_elses_item_is_not_found(client):
    me = register(client)
    fill(client, me, 1)
    item = client.get("/api/library").json()["items"][0]["id"]
    client.post("/api/auth/logout")
    register(client, email="other@local.test", name="Other")
    assert client.get("/api/library/{}".format(item)).status_code == 404


def test_the_whole_list_is_written_out_as_it_was_without_walking_every_value(client, monkeypatch):
    """GET /api/library (and all=1, the canvas) is written as JSON directly, off the event loop: FastAPI's
    jsonable_encoder took two thirds of the time of a list of 20,000 items. What is sent is the same."""
    import json as _json
    from fastapi import encoders, routing
    from scene.api import library

    me = register(client)
    client.app.state.db.run(
        "INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, seconds, created) "
        "VALUES (?, 'image/x', 'image', 'Café ☕', 'c.png', ?, ?, 2.5, ?)",
        (me["id"], _json.dumps({"values": {"100:value": "naïve", "n": [1, 2.5, None, True]}}), _json.dumps({"width": 64}), time.time()))
    walked = []
    real = routing.jsonable_encoder
    monkeypatch.setattr(routing, "jsonable_encoder", lambda value, *a, **k: walked.append(1) or real(value, *a, **k))
    for query in ("", "?all=1", "?limit=5"):
        response = client.get("/api/library" + query)
        assert response.headers["content-type"] == "application/json" and "Café ☕".encode() in response.content
        item = response.json()["items"][0]
        assert item["settings"] == {"values": {"100:value": "naïve", "n": [1, 2.5, None, True]}} and item["context"] == {"width": 64}
        assert item["mine"] is True and "made_by" not in item and "user_id" not in item and item["seconds"] == 2.5
        expected = encoders.jsonable_encoder({"items": [library._shown(dict(row), me) for row in client.app.state.db.all(
            "SELECT g.*, j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
            "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id WHERE g.user_id = ?", (me["id"],))]})
        assert response.json()["items"] == expected["items"]
    assert response.json()["next_cursor"] is None
    assert walked == []   # no item went through jsonable_encoder
