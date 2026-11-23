"""An agent tab's conversation is kept in rows (conversations, one row per turn in conversation_messages; migration
0010) and still read and written as the board "agent-<tab>": the same JSON in, the same JSON out."""

import psycopg

from conftest import POSTGRES
from scene import schema
from test_api import register
from test_schema import scratch  # noqa: F401  (the fixture)

TAB = "agent-mvf2djh7ad4l"
CONVERSATION = {
    "runs": [
        {"instruction": "A chai stall at dawn", "reply": "Here is the plan.", "state": "done", "steps": [{"name": "Shot 1"}],
         "total": 40, "at": 1794140574.2, "ui": {"open": True}, "parts": [], "chips": {}},
        {"instruction": "Make it longer", "reply": "Two more shots.", "state": "proposed", "steps": [{"name": "Shot 2"}, {}],
         "total": 80, "at": 1794140600.5, "question": None},
    ],
    "direction": {"look": "warm, filmic", "cast": ["Raju", "Meera"]},
    "folded": 1,
    "workflows": ["video/h3_all_in_one"],
}


def board(client, kind=TAB, project=0):
    answer = client.get("/api/boards/{}".format(kind), params={"project": project})
    assert answer.status_code == 200
    return answer.json()["data"]


def test_a_tabs_conversation_comes_back_as_it_was_sent_and_is_kept_as_rows(client):
    me = register(client)
    assert client.put("/api/boards/" + TAB, json={"project": 0, "data": CONVERSATION}).json() == {"ok": True}
    assert board(client) == CONVERSATION
    db = client.app.state.db
    kept = db.one("SELECT id, tab, project_id, has_runs FROM conversations WHERE user_id = ?", (me["id"],))
    assert kept["tab"] == TAB[len("agent-"):] and kept["project_id"] is None and kept["has_runs"]
    turns = db.all("SELECT position, state FROM conversation_messages WHERE conversation_id = ? ORDER BY position", (kept["id"],))
    assert [(t["position"], t["state"]) for t in turns] == [(0, "done"), (1, "proposed")]
    assert not db.one("SELECT 1 FROM boards WHERE kind = ?", (TAB,))   # no blob any more

    shorter = dict(CONVERSATION, runs=CONVERSATION["runs"][:1], folded=0)   # a turn taken back: the rows follow
    client.put("/api/boards/" + TAB, json={"project": 0, "data": shorter})
    assert board(client) == shorter
    assert db.one("SELECT COUNT(*) AS n FROM conversation_messages")["n"] == 1

    without_turns = {"direction": {"look": "noir"}}   # a tab that has no turns yet keeps having none
    client.put("/api/boards/" + TAB, json={"project": 0, "data": without_turns})
    assert board(client) == without_turns


def test_each_project_and_user_has_its_own_and_a_deleted_tab_takes_its_turns(client):
    register(client)
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    client.put("/api/boards/" + TAB, json={"project": project, "data": CONVERSATION})
    assert board(client, project=project) == CONVERSATION and board(client) == {}   # all work: another conversation
    client.cookies.clear()
    register(client, name="Eve", email="eve@example.com")
    assert board(client) == {}                                                       # someone else's: not found
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    assert client.delete("/api/boards/{}".format(TAB), params={"project": project}).json() == {"ok": True}
    assert board(client, project=project) == {}
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM conversation_messages")["n"] == 0


def test_the_phone_lists_the_newest_turn_waiting_for_approval(client):
    register(client)
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    client.put("/api/boards/agent", json={"project": project, "data": {"tabs": [{"id": TAB[len("agent-"):], "name": "Shots"}]}})
    client.put("/api/boards/" + TAB, json={"project": project, "data": CONVERSATION})
    waiting = client.get("/api/mobile/waiting").json()["plans"]
    assert [(w["tab_name"], w["instruction"], w["steps"], w["total"]) for w in waiting] == [("Shots", "Make it longer", 2, 80)]


def test_boards_become_conversations_and_go_back_with_what_was_said_since(scratch):  # noqa: F811
    import json
    schema.upgrade(scratch, "0009")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        user = conn.execute("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', now()) "
                            "RETURNING id").fetchone()[0]
        conn.execute("INSERT INTO boards (user_id, project_id, kind, data, updated) VALUES (%s, NULL, %s, %s, now())",
                     (user, TAB, json.dumps(CONVERSATION)))
    schema.upgrade(scratch, "0010")
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        assert conn.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0] == 2
        conn.execute("UPDATE conversations SET meta = meta || '{\"folded\": 2}'")   # said after the upgrade
    schema.downgrade(scratch, "0009")
    with psycopg.connect(scratch) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        data = conn.execute("SELECT data FROM boards WHERE kind = %s", (TAB,)).fetchone()[0]
    assert data == dict(CONVERSATION, folded=2)


def test_two_saves_of_one_tab_at_once_keep_one_of_them_never_both(client):
    """write() is one statement whose DELETE sees the turns as they were when it began: a save that waited for another
    (here both wait for a lock a third connection holds on the conversation) kept its turns and the other's too."""
    import threading
    import time
    from scene import conversations
    me = register(client)
    db = client.app.state.db
    conversations.write(db, me["id"], 0, "race", {"runs": [{"n": 0}]})
    found = db.one("SELECT id FROM conversations WHERE tab = 'race'")["id"]
    holder = psycopg.connect(POSTGRES)
    holder.execute("SELECT set_config('app.user_id', %s, false)", (str(me["id"]),))
    assert holder.execute("SELECT id FROM conversations WHERE id = %s FOR UPDATE", (found,)).fetchall()
    failed = []

    def save(n):
        try:
            conversations.write(db, me["id"], 0, "race", {"runs": [{"n": n}, {"n": n}]})
        except Exception as error:
            failed.append(error)
    savers = [threading.Thread(target=save, args=(n,)) for n in (1, 2)]
    for saver in savers:
        saver.start()
    time.sleep(0.5)
    holder.commit()
    holder.close()
    for saver in savers:
        saver.join(10)
    turns = conversations.read(db, me["id"], 0, "race")["runs"]
    assert not failed and turns in ([{"n": 1}, {"n": 1}], [{"n": 2}, {"n": 2}])


def test_an_older_copy_never_writes_over_a_newer_one(client):
    """A window left open at the first turn (or a save that arrived late) is refused (409, with the kept version), so
    the conversation is not lost; the same save sent again (a retry) is kept once; an old page without a version is
    refused once there is one."""
    register(client)
    first = dict(CONVERSATION, runs=CONVERSATION["runs"][:1], rev=1, writer="studio-a")
    assert client.put("/api/boards/" + TAB, json={"project": 0, "data": first}).json() == {"ok": True}
    whole = dict(CONVERSATION, rev=2, writer="studio-a")
    assert client.put("/api/boards/" + TAB, json={"project": 0, "data": whole}).json() == {"ok": True}
    assert client.put("/api/boards/" + TAB, json={"project": 0, "data": whole}).json() == {"ok": True}   # retried

    stale = dict(first, rev=2, writer="phone-b")   # loaded at rev 1 elsewhere: its next save is 2 as well
    answer = client.put("/api/boards/" + TAB, json={"project": 0, "data": stale})
    assert answer.status_code == 409 and answer.json()["rev"] == 2 and answer.json()["writer"] == "studio-a"
    unversioned = client.put("/api/boards/" + TAB, json={"project": 0, "data": CONVERSATION["runs"] and {"runs": []}})
    assert unversioned.status_code == 409
    assert board(client) == whole


def test_a_nul_character_in_a_turn_does_not_stop_the_save(client):
    """PostgreSQL's jsonb refuses \u0000: it is left out, and the rest is kept."""
    register(client)
    data = dict(CONVERSATION, runs=[dict(CONVERSATION["runs"][0], reply="ffmpeg said: a\x00b")], rev=1, writer="w")
    assert client.put("/api/boards/" + TAB, json={"project": 0, "data": data}).json() == {"ok": True}
    assert board(client)["runs"][0]["reply"] == "ffmpeg said: ab"
