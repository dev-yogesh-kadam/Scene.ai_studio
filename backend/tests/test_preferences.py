"""A user's choices kept on the server (preferences.py): the agent's model, effort, permission and explain switch, and
the studio's last workflows, kind, project and skills. They follow the user to another browser; an automatic approval
of a plan is held to the permission."""

from test_api import ADMIN, register
from test_plans import USER, step, studio  # noqa: F401  (the fixture)


def test_agent_preferences_start_as_before_and_keep_what_is_set(client):
    register(client)
    first = client.get("/api/agent/preferences").json()
    assert first == {"retry_once": False, "model": None, "effort": {}, "permission": "always", "explain": {}}
    saved = client.put("/api/agent/preferences", json={"model": "claude-x", "effort": {"claude-x": "high"},
                                                       "permission": "videos", "explain": {"main": True}}).json()
    assert (saved["model"], saved["effort"], saved["permission"], saved["explain"]) == ("claude-x", {"claude-x": "high"}, "videos", {"main": True})
    # one field at a time: the others stay
    client.put("/api/agent/preferences", json={"effort": {"other": "low"}})
    again = client.get("/api/agent/preferences").json()
    assert again["effort"] == {"claude-x": "high", "other": "low"} and again["permission"] == "videos"
    # retry_once alone answers as it always did, with the rest beside it
    assert client.put("/api/agent/preferences", json={"retry_once": True}).json()["retry_once"] is True


def test_bad_agent_preferences_are_refused_and_change_nothing(client):
    register(client)
    assert client.put("/api/agent/preferences", json={"permission": "sometimes"}).status_code == 400
    assert client.put("/api/agent/preferences", json={"effort": ["high"]}).status_code == 400
    assert client.put("/api/agent/preferences", json={"model": "<script>"}).status_code == 400
    assert client.get("/api/agent/preferences").json()["permission"] == "always"


def test_preferences_follow_the_user_not_the_browser(client):
    register(client)
    client.put("/api/agent/preferences", json={"permission": "all"})
    client.put("/api/preferences", json={"workflows": {"image": "image/flux"}, "kind": "image", "project": 4, "skills": ["script-to-video"]})
    client.post("/api/auth/logout")
    client.cookies.clear()   # another browser: nothing of the first one's
    assert client.post("/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}).status_code == 200
    assert client.get("/api/agent/preferences").json()["permission"] == "all"
    assert client.get("/api/preferences").json() == {"workflows": {"image": "image/flux"}, "kind": "image", "project": 4,
                                                     "skills": ["script-to-video"], "seen": []}


def test_studio_preferences_are_checked(client):
    register(client)
    assert client.get("/api/preferences").json() == {"workflows": {}, "kind": None, "project": None, "skills": [], "seen": []}
    client.put("/api/preferences", json={"seen": ["canvas-tip"]})
    assert client.put("/api/preferences", json={"seen": ["canvas-tip", "other"]}).json()["seen"] == ["canvas-tip", "other"]
    assert client.put("/api/preferences", json={"project": "four"}).status_code == 400
    assert client.put("/api/preferences", json={"skills": "x"}).status_code == 400
    client.put("/api/preferences", json={"workflows": {"video": "video/a"}})
    assert client.put("/api/preferences", json={"workflows": {"image": "image/b"}}).json()["workflows"] == {"video": "video/a", "image": "image/b"}
    assert len(client.put("/api/preferences", json={"skills": [str(n) for n in range(9)]}).json()["skills"]) == 5


def test_a_plan_approved_by_the_page_itself_is_held_to_the_permission(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one")], "tab": "agent"}).json()
    # "Always ask" (the default): an automatic approval is refused and nothing is charged
    refused = studio.post("/api/agent/plans/{}/approve".format(plan["id"]), json={"auto": True})
    assert refused.status_code == 403
    assert studio.get("/api/agent/plans/{}".format(plan["id"])).json()["state"] == "waiting"
    # "Ask before videos": a plan of pictures may run by itself; one with a video may not
    studio.put("/api/agent/preferences", json={"permission": "videos"})
    video = studio.post("/api/agent/plans", json={"steps": [step("clip", kind="video")], "tab": "agent"}).json()
    assert studio.post("/api/agent/plans/{}/approve".format(video["id"]), json={"auto": True}).status_code == 403
    assert studio.post("/api/agent/plans/{}/approve".format(plan["id"]), json={"auto": True}).status_code == 200
    # the user's own Approve (no "auto") is never refused for the permission
    assert studio.post("/api/agent/plans/{}/approve".format(video["id"])).status_code in (200, 402)
