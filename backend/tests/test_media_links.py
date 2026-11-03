"""The studio's own links to a result (/api/m/<public id>, library.media_link) and the files a reply hands over in the
chat ([[show:item:12]], agent.chips_in): a link opens only for someone signed in who may see the item."""

from scene import agent, core
from test_api import ADMIN, register
from test_boards_placement import PNG, finish, project

BOB = {"email": "bob@example.com", "password": "another one"}


def test_a_link_opens_the_file_for_its_owner_only(client, tmp_path):
    me = register(client)
    item = finish(client, tmp_path, me["id"], project(client), "film", workflow="edit/film")
    public = core.public_ids(client.app.state.db, "generations", [item])[item]
    assert len(public) == 12
    got = client.get("/api/m/" + public)
    assert got.status_code == 200 and got.content == PNG
    assert client.get("/api/m/{}.mp4".format(public)).status_code == 200   # a link may end in the file's extension
    assert "attachment" in client.get("/api/m/{}?download=1".format(public)).headers["content-disposition"]
    assert client.get("/api/m/000000000000").status_code == 404
    assert client.get("/api/m/not-an-id").status_code == 404
    client.post("/api/auth/logout")
    assert client.get("/api/m/" + public).status_code == 401
    client.post("/api/auth/register", json=BOB)   # another user, not in the project
    assert client.get("/api/m/" + public).status_code == 404
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]})


def test_a_reply_hands_over_a_file_and_says_when_it_cannot():
    items = {7: {"name": "Final film", "kind": "video"}}
    chips, said = agent.chips_in("Here it is:\n[[show:item:7]]", items, {})
    assert chips == {"item:7": {"name": "Final film", "kind": "video"}} and said == "Here it is:\n[[show:item:7]]"
    chips, said = agent.chips_in("Here it is: [[show:item:8]]", items, {})
    assert chips == {} and said == "Here it is:\n\n" + agent.MISSING
    assert agent.named_ids("[[item:3]] and [[show:item:4]] and [[asset:5]]") == {3, 4}
