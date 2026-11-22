"""The generation server as the studio's gateway, by keys (docs/servers.md, "Providers and keys"): several keys pasted
at once, what each key unlocks, What makes what with a test key alone, and the provider's voices (for Create and the
agent's voices tool). Each test with a provider adds its own (no_models): the test studio's is studio_models.py's.
(What makes what with keys: test_providers.py.)"""

import json

import pytest

from fake_v1 import SEEDANCE, SPEECH, FakeV1
from scene import agent_tools
from scene.providers import registry, router as router_module
from test_api import console, register

TRANSCRIBE = {"id": "transcribe", "name": "Transcription", "capability": "transcribe", "best_for": "A transcript with times.",
              "input_schema": {"type": "object", "required": ["audio"], "properties": {
                  "audio": {"type": "string", "x-file": "audio"},
                  "language": {"type": "string", "enum": ["auto", "en", "hi"], "default": "auto"}}},
              "limits": {}, "pricing": {"unit": "job", "credits": 0}, "typical_seconds": 60, "can_cancel": False}


def through(monkeypatch, fake):
    """The studio's v1 adapter talks to the fake server."""
    from scene.providers.v1 import V1
    monkeypatch.setattr(router_module, "V1", lambda base_url: V1(base_url, http=fake.client()))


def add_key(desk, secret, **more):
    body = dict({"kind": "scene_provider_v1", "base_url": "fake-v1", "name": "Generation server", "secret": secret}, **more)
    return desk.post("/api/admin/providers/keys", json=body).json()


# ---------------------------------------------------------------- several keys at once

def test_a_paste_is_read_one_key_a_line():
    found = registry.parse_keys("# made on the generation server\nScene.ai · Video · Seedance 2.5\tsa_live_aaaaaaaa1111\n\n"
                                "sa_test_bbbbbbbb2222\r\nVoiceover: sa_live_cccccccc3333\nstudio B sa_live_dddddddd4444\n")
    assert [(k["line"], k["label"], k["secret"]) for k in found] == [
        (2, "Scene.ai · Video · Seedance 2.5", "sa_live_aaaaaaaa1111"), (4, "", "sa_test_bbbbbbbb2222"),
        (5, "Voiceover", "sa_live_cccccccc3333"), (6, "studio B", "sa_live_dddddddd4444")]
    for text, words in (("", "at least one"), ("label\tshort", "Line 1 holds no key"),
                        ("sa_live_aaaaaaaa1111\nsa_live_aaaaaaaa1111", "twice"),
                        ("\n".join("sa_live_{:012d}".format(n) for n in range(51)), "At most 50")):
        with pytest.raises(ValueError, match=words):
            registry.parse_keys(text)


@pytest.mark.no_models
def test_several_keys_are_checked_saved_and_labelled_and_never_given_back(client, monkeypatch):
    fake = FakeV1(models=(SEEDANCE, SPEECH, TRANSCRIBE), live=("sa_live_alpha1234", "sa_live_gamma9999"))
    fake.labels["sa_live_gamma9999"] = "Scene.ai prod · Voiceover"
    through(monkeypatch, fake)
    register(client)
    desk = console(client)
    text = "Video key\tsa_live_alpha1234\nsa_live_gamma9999\nsa_live_wrong0000\n"
    bad = desk.post("/api/admin/providers/keys/many", json={"kind": "scene_provider_v1", "base_url": "fake-v1", "text": text,
                                                            "max_concurrent": "lots"})
    assert bad.status_code == 400 and "not a whole number" in bad.json()["detail"]
    got = desk.post("/api/admin/providers/keys/many", json={"kind": "scene_provider_v1", "base_url": "fake-v1",
                                                            "name": "Generation server", "text": text, "max_concurrent": 3}).json()
    assert got["saved"] == 2
    lines = {r["line"]: r for r in got["results"]}
    assert (lines[1]["label"], lines[1]["saved"]) == ("Video key", True)
    assert (lines[2]["label"], lines[2]["saved"]) == ("Scene.ai prod · Voiceover", True)   # the provider's label
    assert lines[3]["saved"] is False and "not known" in lines[3]["check"]["error"]
    provider = next(p for p in got["providers"] if p["kind"] == "scene_provider_v1")
    assert provider["name"] == "Generation server" and [k["max_concurrent"] for k in provider["keys"]] == [3, 3]
    unlocks = provider["keys"][0]["unlocks"]
    assert [(u["capability"], u["words"], [m["name"] for m in u["models"]]) for u in unlocks] == [
        ("text_to_video", "Video", ["Seedance 2.5"]), ("speech", "Voiceover", ["Speech"]),
        ("transcribe", "Transcription", ["Transcription"])]
    again = desk.post("/api/admin/providers/keys/many", json={"provider_id": provider["id"], "text": "sa_live_alpha1234"}).json()
    assert again["saved"] == 0 and again["results"][0]["words"] == "Already here as Video key"
    for answer in (got, again, desk.get("/api/admin/providers").json()):
        assert "alpha1234" not in json.dumps(answer) and "gamma9999" not in json.dumps(answer)
    assert desk.get("/api/admin/audit").json()["entries"][0]["action"] == "Added provider keys"


def test_on_this_pc_and_claude_keys_are_not_pasted_in_bulk(client):
    import sys
    client.app.state.settings.local_tools_python = sys.executable   # its Python there: On this PC is listed
    register(client)
    desk = console(client)
    kinds = {p["kind"]: p for p in desk.get("/api/admin/providers").json()["providers"]}
    answer = desk.post("/api/admin/providers/keys/many", json={"provider_id": kinds["claude_local"]["id"], "text": "sa_live_alpha1234"})
    assert answer.status_code == 400 and "has no key" in answer.json()["detail"]
    answer = desk.post("/api/admin/providers/keys/many", json={"provider_id": kinds["local_tools"]["id"], "text": "sa_live_alpha1234"})
    assert answer.status_code == 400 and "needs no key" in answer.json()["detail"]


# ---------------------------------------------------------------- what makes what

@pytest.mark.no_models
def test_a_model_only_a_test_key_has_is_marked(client, monkeypatch):
    fake = FakeV1(live=(), test=("sa_test_beta5678",))
    through(monkeypatch, fake)
    register(client)
    desk = console(client)
    add_key(desk, "sa_test_beta5678")
    seen = next(r for r in desk.get("/api/admin/providers/capabilities").json()["capabilities"] if r["capability"] == "text_to_video")
    assert seen["state"] == "provider" and seen["live"] is False
    assert [k["mode"] for k in seen["models"][0]["keys"]] == ["test"]


# ---------------------------------------------------------------- voices

@pytest.mark.no_models
def test_the_providers_voices_are_listed_for_anyone_signed_in(client, monkeypatch):
    fake = FakeV1()
    through(monkeypatch, fake)
    register(client)
    none = client.get("/api/voices").json()
    assert none["voices"] == [] and "No provider key has the voiceover model" in none["words"]
    desk = console(client)
    add_key(desk, "sa_live_alpha1234")
    old = client.get("/api/voices").json()   # the provider has no list yet: 404
    assert old["voices"] == [] and "has no voice list yet" in old["words"]
    client.app.state.router._voices.clear()
    fake.voices = [{"id": "v_warm", "name": "Warm narrator", "language": "en-US", "gender": "female", "extra": "x"},
                   {"id": "v_bright", "name": "Bright", "language": "hi-IN"}, {"name": "no id"}]
    found = client.get("/api/voices", params={"q": "warm"}).json()
    assert found["voices"] == [{"id": "v_warm", "name": "Warm narrator", "language": "en-US", "gender": "female", "engine": "",
                                "preview_url": ""}]
    assert [c for c in fake.calls if c["path"] == "/v1/voices"][-1]["last4"] == "1234"
    fake.voices.append({"id": "v_late", "name": "Warm late"})
    assert len(client.get("/api/voices", params={"q": "warm"}).json()["voices"]) == 1   # kept 10 minutes


def test_the_agent_has_a_voices_tool():
    from scene import agent
    assert "voices" in agent.TOOLS and "voices" in agent_tools.TOOLS
    assert agent_tools.check() == []


def test_a_voice_engine_is_read_from_the_voice_list():
    import asyncio
    from scene.providers.router import Router
    router = Router.__new__(Router)
    router._voices = {("", ""): (0, [{"id": "v_11", "engine": "elevenlabs"}, {"id": "v_g", "engine": "gemini"}], "")}
    assert asyncio.run(router.voice_engine("v_11")) == "elevenlabs"
    assert asyncio.run(router.voice_engine("v_g")) == "gemini"
    assert asyncio.run(router.voice_engine("")) == ""
