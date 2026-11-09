"""The Home page's showcase (showcase.py): an admin picks the best work, every user sees the same."""

from test_admin_tools import as_bob, with_bob
from test_api import console


def made(client, user_id, name, kind="video", filename="clip.mp4", data=b"video"):
    folder = client.app.state.outputs.folder(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_bytes(data)
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
        "VALUES (?, 'video/h3_all_in_one', ?, ?, ?, '{\"prompt\": \"A toast in the garden\", \"workflow_title\": \"H3\"}', "
        "'{\"width\": 1080, \"height\": 1920, \"seed\": 7}', 1)", (user_id, kind, name, filename))


def test_an_admin_puts_work_on_every_users_home_page_and_it_outlives_its_owner_deleting_it(client):
    bob = with_bob(client)
    item = made(client, bob["id"], "Garden toast")
    desk = console(client)
    added = desk.post("/api/admin/showcase", json={"item_id": item, "section": "Microdrama"}).json()
    assert added["sections"] == ["Microdrama"] and added["items"][0]["name"] == "Garden toast"
    key = added["items"][0]["key"]

    as_bob(client)
    home = client.get("/api/showcase").json()
    shown = home["items"][0]
    assert home["sections"] == ["Microdrama"] and shown["id"] == key and shown["section"] == "Microdrama"
    assert shown["settings"]["prompt"] == "A toast in the garden" and shown["context"] == {"width": 1080, "height": 1920}
    assert "from" not in shown and "user_email" not in shown
    assert client.get("/api/showcase/%s/file" % key).content == b"video"

    # Bob deletes his own item: the copy on the Home page stays.
    assert client.delete("/api/library/%d" % item).status_code == 200
    assert client.get("/api/showcase/%s/file" % key).content == b"video"
    assert client.put("/api/admin/showcase", json={}).status_code in (404, 405)   # the studio has no admin routes


def test_sections_order_names_and_prompts_are_the_admins_to_change(client):
    bob = with_bob(client)
    first, second = made(client, bob["id"], "One"), made(client, bob["id"], "Two", kind="image", filename="two.png", data=b"png")
    desk = console(client)
    desk.post("/api/admin/showcase", json={"item_id": first, "section": "Ads"})
    keys = [i["key"] for i in desk.post("/api/admin/showcase", json={"item_id": second, "section": "ads"}).json()["items"]]
    assert desk.get("/api/admin/showcase").json()["sections"] == ["Ads"]   # "ads" is the same section
    changed = desk.put("/api/admin/showcase", json={"sections": ["Shorts", "Shorts", " "], "items": [
        {"key": keys[1], "name": "  The second  ", "section": "Shorts", "show_prompt": False}]}).json()
    assert changed["sections"] == ["Shorts"]
    assert [i["key"] for i in changed["items"]] == [keys[1], keys[0]]          # listed first, the rest after
    assert changed["items"][0]["name"] == "The second" and changed["items"][1]["section"] == ""   # "Ads" is gone
    assert "prompt" not in client.get("/api/showcase").json()["items"][0]["settings"]

    removed = desk.delete("/api/admin/showcase/" + keys[1]).json()
    assert [i["key"] for i in removed["items"]] == [keys[0]]
    assert client.get("/api/showcase/%s/file" % keys[1]).status_code == 404
    assert desk.delete("/api/admin/showcase/" + keys[1]).status_code == 404


def test_only_pictures_and_videos_go_on_the_home_page(client):
    bob = with_bob(client)
    sound = made(client, bob["id"], "Theme", kind="audio", filename="theme.mp3", data=b"mp3")
    answer = console(client).post("/api/admin/showcase", json={"item_id": sound})
    assert answer.status_code == 400 and "pictures and videos" in answer.json()["detail"]
    assert console(client).post("/api/admin/showcase", json={"item_id": 99999}).status_code == 404
