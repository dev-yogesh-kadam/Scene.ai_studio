"""Ops and reliability (hardening pass, 10 Nov 2026): the health checks (database, Claude Code signed in, FFmpeg,
HyperFrames), the JSON logs cleaned of keys, the daily backups by the calendar, and the Docker files."""

import asyncio
import io
import json
import os
import re
import sys

import pytest

from scene import backup, health, media, motion, phone
from scene.db import offload
from scene.config import ROOT
from scene.logs import LONGEST, JsonLines
from test_api import console, register


# ---------------------------------------------------------------- JSON logs

def _logged(*writes):
    out = io.StringIO()
    stream = JsonLines(out, "error")
    for text in writes:
        stream.write(text)
    return [json.loads(line)["message"] for line in out.getvalue().splitlines()]


def test_a_json_log_line_never_holds_a_key_a_token_or_a_password():
    key = "sk-ant-api03-" + "A1b2C3d4" * 6
    lines = _logged("Claude failed with key {}\n".format(key),
                    "could not connect: postgresql://scene_app:hunter2-very-secret@localhost:5432/scene\n",
                    'the reply was {"api_key": "zz-abcdef123456"}\nAuthorization: Bearer ' + "q" * 40 + "\n")
    said = "\n".join(lines)
    for secret in (key, "hunter2-very-secret", "zz-abcdef123456", "q" * 40):
        assert secret not in said
    assert lines[0].startswith("Claude failed with key ") and "[redacted]" in lines[0]
    assert "postgresql://scene_app:[redacted]@localhost:5432/scene" in lines[1]   # where it was, without the password


def test_a_json_log_line_keeps_ordinary_words_and_cuts_a_huge_one():
    assert _logged("Scene.ai is running at http://localhost:8080\n") == ["Scene.ai is running at http://localhost:8080"]
    huge = _logged("A failure that quotes a whole prompt: " + "word " * 5000 + "\n")[0]
    assert len(huge) < LONGEST + 80 and huge.endswith("more characters not logged]")


# ---------------------------------------------------------------- health: the database

def test_a_database_that_does_not_answer_is_the_one_problem_and_reaches_the_phones(client, monkeypatch):
    register(client)
    state = client.app.state
    state.db.set_setting("phone_alerts", json.dumps({"ntfy_url": "https://ntfy.sh/scene-ops-test"}))
    sent = []

    async def fake_send(http, db, level, text):
        sent.append((level, text, (await offload(phone.config, db))["ntfy_url"]))   # the settings read while it answered
        return {}
    monkeypatch.setattr(phone, "send", fake_send)
    real = state.db.aone
    down = {"now": False}

    async def aone(sql, params=()):
        if down["now"]:
            raise OSError('connection to server at "localhost" failed: password=hunter22secret refused')
        return await real(sql, params)
    monkeypatch.setattr(state.db, "aone", aone)
    watcher = health.Watcher(state)

    async def scenario():
        assert await watcher.step([], now=900) == []
        down["now"] = True
        found = await health.problems(state)
        assert [(p["key"], p["level"]) for p in found] == [("database", "critical")]
        assert "hunter22secret" not in found[0]["text"] and "does not answer" in found[0]["text"]
        assert await watcher.step(found, now=1000) == []                      # once could be a hiccup
        assert await watcher.step(found, now=1060) == [("critical", found[0]["text"])]
        assert await watcher.step(found, now=1120) == []                      # sent once
        down["now"] = False
        said = await watcher.step([], now=1720)
        await watcher.http.aclose()
        return found[0]["text"], said
    text, said = asyncio.run(scenario())
    assert said == [("resolved", "The database answers again (after 12 min).")]
    assert sent == [("critical", text, "https://ntfy.sh/scene-ops-test"),
                    ("resolved", "The database answers again (after 12 min).", "https://ntfy.sh/scene-ops-test")]
    alerts = console(client).get("/api/admin/alerts").json()
    assert [(a["key"], a["started"], a["ended"]) for a in alerts["recent"]] == [("database", 1000, 1720)]


def test_the_database_check_says_how_long_it_took(client):
    found = asyncio.run(health.database(client.app.state))
    assert found["online"] is True and found["seconds"] < health.DATABASE_WAIT and found["detail"] == ""


# ---------------------------------------------------------------- health: Claude Code signed in

@pytest.fixture
def no_sign_in_cache():
    health._signed_in.clear()
    yield
    health._signed_in.clear()


def test_claude_code_signed_out_is_a_problem_that_says_how_to_sign_in(client, monkeypatch, no_sign_in_cache):
    register(client)
    state = client.app.state
    asked = []

    async def status(program):
        asked.append(program)
        return {"signed_in": answer["signed_in"], "plan": "max"}
    answer = {"signed_in": False}
    monkeypatch.setattr(health, "_auth_status", status)
    health.forget(state, "model")
    found = asyncio.run(health.problems(state))
    model = [p for p in found if p["key"] == "model"]
    assert model and "not signed in" in model[0]["text"] and "/login" in model[0]["text"]
    shown = console(client).get("/api/admin/system").json()["model_server"]
    assert shown["online"] is False and shown["signed_in"] is False and shown["plan"] == "max"
    assert len(asked) == 1                                                    # asked once in SIGN_IN_EVERY seconds

    answer["signed_in"] = True
    health._signed_in.clear()
    health.forget(state, "model")
    assert not [p for p in asyncio.run(health.problems(state)) if p["key"] == "model"]


def test_claude_code_that_cannot_say_whether_it_is_signed_in_is_not_called_signed_out(client, no_sign_in_cache):
    """The tests' Claude Code is a program that is not there: nothing is known, so nothing is claimed."""
    register(client)
    health.forget(client.app.state, "model")
    shown = console(client).get("/api/admin/system").json()["model_server"]
    assert shown["online"] is True and shown["signed_in"] is None


@pytest.mark.skipif(sys.platform != "win32", reason="a .cmd stands in for claude.exe on Windows")
def test_the_sign_in_is_read_from_claude_auth_status(tmp_path, no_sign_in_cache):
    def fake(name, said):
        program = tmp_path / name
        program.write_text("@echo off\r\nif \"%1 %2 %3\"==\"auth status --json\" echo {}\r\n".format(said), encoding="ascii")
        return str(program)
    out = fake("out.cmd", '{"loggedIn": false, "authMethod": "none"}')
    assert asyncio.run(health.signed_in(out)) == {"signed_in": False, "plan": ""}
    inn = fake("in.cmd", '{"loggedIn": true, "subscriptionType": "max", "email": "someone@example.com"}')
    assert asyncio.run(health.signed_in(inn)) == {"signed_in": True, "plan": "max"}   # no email kept
    odd = fake("odd.cmd", "Unknown command auth")
    assert asyncio.run(health.signed_in(odd)) == {"signed_in": None, "plan": ""}
    assert asyncio.run(health.signed_in(str(tmp_path / "none.exe"))) == {"signed_in": None, "plan": ""}


# ---------------------------------------------------------------- health: FFmpeg and HyperFrames

def test_ffmpeg_or_hyperframes_missing_is_a_problem(client, monkeypatch):
    register(client)
    state = client.app.state
    online = {"online": True, "url": "", "since": 0}

    def no_ffmpeg():
        raise media.MediaError("ffmpeg is not installed.")
    monkeypatch.setattr(media, "ffmpeg_path", no_ffmpeg)
    monkeypatch.setattr(motion, "status", lambda node="": {"ready": False, "detail": "HyperFrames is not installed."})
    found = {p["key"]: p for p in asyncio.run(health.problems(state, render=online, model={"online": True, "detail": ""}))}
    assert found["ffmpeg"]["level"] == "serious" and "ffmpeg is not installed" in found["ffmpeg"]["text"]
    assert found["motion"]["level"] == "warning" and "HyperFrames is not installed" in found["motion"]["text"]
    assert "ffmpeg" in health.RESOLVED and "motion" in health.RESOLVED

    monkeypatch.setattr(media, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(motion, "status", lambda node="": {"ready": True, "detail": ""})
    keys = [p["key"] for p in asyncio.run(health.problems(state, render=online, model={"online": True, "detail": ""}))]
    assert "ffmpeg" not in keys and "motion" not in keys


def test_every_check_in_one_answer(client):
    register(client)
    found = asyncio.run(health.checks(client.app.state))
    assert set(found) == {"database", "render", "model", "programs", "disk", "backup", "langfuse"}
    assert found["database"]["online"] is True and found["render"]["online"] is False
    assert set(found["programs"]) == {"ffmpeg", "motion"} and found["langfuse"]["in_use"] is False
    assert found["disk"]["free"] > 0 and "last" in found["backup"]


