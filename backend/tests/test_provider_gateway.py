"""The generation server as the studio's gateway, by keys (docs/servers.md, "Providers and keys" and "Moving off
ComfyUI"): several keys pasted at once, what each key unlocks, What makes what with ComfyUI switched off one capability
at a time, and the provider's voices (for Create and the agent's voices tool)."""

import json

import pytest
from fastapi import HTTPException

from fake_v1 import SEEDANCE, SPEECH, FakeV1
from scene import agent_tools
from scene.api import studio
from scene.providers import registry, router as router_module
from scene.providers.comfyui import capability_of
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
    comfy = next(p for p in got["providers"] if p["kind"] == "comfyui")
    assert all(k["unlocks"] == [] for k in comfy["keys"])   # a ComfyUI server's "models" are its workflows: not listed


def test_comfyui_and_claude_keys_are_not_pasted_in_bulk(client):
    register(client)
    desk = console(client)
    comfy = next(p for p in desk.get("/api/admin/providers").json()["providers"] if p["kind"] == "comfyui")
    answer = desk.post("/api/admin/providers/keys/many", json={"provider_id": comfy["id"], "text": "sa_live_alpha1234"})
    assert answer.status_code == 400 and "one at a time" in answer.json()["detail"]


# ---------------------------------------------------------------- what makes what

def test_the_comfyui_workflows_are_sorted_into_finer_capabilities():
    assert [capability_of(w) for w in ("video/h3_all_in_one", "video/video_ltx2_5_t2v", "video/video_v2v_wan_vace",
                                       "video/video_outpaint_wan_vace", "video/video_wan_animate2",
                                       "video/talking_head_narration", "video/video_lipsync", "audio/audio_transcribe",
                                       "audio/audio_separate_voice", "upscaler/utility_seedvr2_3b_int8_upscale_video")] == [
        "text_to_video", "text_to_video", "video_to_video", "outpaint", "animate", "talking_head", "lip_sync",
        "transcribe", "separate_voice", "upscale_video"]


def test_comfyui_is_switched_off_for_a_capability_only_while_a_live_key_makes_it(client, monkeypatch):
    fake = FakeV1(models=(SEEDANCE, SPEECH, TRANSCRIBE))
    through(monkeypatch, fake)
    register(client)
    desk = console(client)
    add_key(desk, "sa_live_alpha1234", label="All")
    state = client.app.state

    def row(answer, capability="transcribe"):
        return next(r for r in answer["capabilities"] if r["capability"] == capability)

    seen = row(desk.get("/api/admin/providers/capabilities").json())
    assert [m["id"] for m in seen["models"]] == ["transcribe"] and seen["live"] is True
    assert "audio/audio_transcribe" in [w["id"] for w in seen["comfy"]]
    assert (seen["state"], seen["comfyui_on"], seen["can_switch_off"]) == ("comfyui", True, False)
    assert "router is not on" in seen["why_not"]
    refused = desk.put("/api/admin/providers/capabilities/transcribe", json={"comfyui": False})
    assert refused.status_code == 400 and "router is not on" in refused.json()["detail"]
    assert desk.put("/api/admin/providers/capabilities/flying", json={"comfyui": True}).status_code == 404
    assert desk.put("/api/admin/providers/capabilities/transcribe", json={"comfyui": "no"}).status_code == 400

    desk.put("/api/admin/providers/router", json={"mode": "on"})
    seen = row(desk.get("/api/admin/providers/capabilities").json())
    assert (seen["state"], seen["can_switch_off"]) == ("both", True)
    nothing = row(desk.get("/api/admin/providers/capabilities").json(), "outpaint")
    assert nothing["models"] == [] and "No provider key" in nothing["why_not"]   # only ComfyUI does it: it stays

    answer = desk.put("/api/admin/providers/capabilities/transcribe", json={"comfyui": False}).json()
    assert (row(answer)["state"], row(answer)["comfyui_on"]) == ("provider", False)
    assert state.credits.enabled("audio/audio_transcribe") is False
    assert state.credits.enabled("audio/audio_separate_voice") is True   # another capability: still ComfyUI's
    assert state.credits.enabled("audio/@transcribe") is True   # the provider's own model
    assert state.credits.enabled_of(["audio/audio_transcribe", "audio/audio_separate_voice"]) == {"audio/audio_separate_voice"}
    with pytest.raises(HTTPException) as refused:
        studio.switched_on(state, "audio/audio_transcribe", None)
    assert "Transcription is no longer made on ComfyUI" in refused.value.detail

    desk.put("/api/admin/providers/router", json={"mode": "off"})   # the router off: ComfyUI makes everything again
    assert state.credits.enabled("audio/audio_transcribe") is True
    assert row(desk.get("/api/admin/providers/capabilities").json())["state"] == "comfyui"
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    assert state.credits.enabled("audio/audio_transcribe") is False   # the choice was kept
    desk.put("/api/admin/providers/capabilities/transcribe", json={"comfyui": True})
    assert state.credits.enabled("audio/audio_transcribe") is True
    assert [e["action"] for e in desk.get("/api/admin/audit").json()["entries"]][:1] == ["Switched ComfyUI on for a capability"]


def test_a_test_key_alone_does_not_let_comfyui_go(client, monkeypatch):
    fake = FakeV1(live=(), test=("sa_test_beta5678",))
    through(monkeypatch, fake)
    register(client)
    desk = console(client)
    add_key(desk, "sa_test_beta5678")
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    seen = next(r for r in desk.get("/api/admin/providers/capabilities").json()["capabilities"] if r["capability"] == "text_to_video")
    assert seen["live"] is False and seen["can_switch_off"] is False and "Only test keys" in seen["why_not"]
    assert [k["mode"] for k in seen["models"][0]["keys"]] == ["test"]


# ---------------------------------------------------------------- voices

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
    assert found["voices"] == [{"id": "v_warm", "name": "Warm narrator", "language": "en-US", "gender": "female", "preview_url": ""}]
    assert [c for c in fake.calls if c["path"] == "/v1/voices"][-1]["last4"] == "1234"
    fake.voices.append({"id": "v_late", "name": "Warm late"})
    assert len(client.get("/api/voices", params={"q": "warm"}).json()["voices"]) == 1   # kept 10 minutes


def test_the_agent_has_a_voices_tool():
    from scene import agent
    assert "voices" in agent.TOOLS and "voices" in agent_tools.TOOLS
    assert agent_tools.check() == []
