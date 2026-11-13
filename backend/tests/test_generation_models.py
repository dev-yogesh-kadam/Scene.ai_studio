"""The generation server's models (generation_models.py): Seedance, Kling, Wan, MiniMax … as the Model setting of two
workflows, video/generation_video and image/generation_image, kept apart from ComfyUI's workflows.

The job's words, the agent's settings and the price only see the options shown for the chosen model; with the
generation server's list of models, what a model can't take is refused before the job is sent, and without it nothing
breaks."""

import asyncio
import json
import re

import pytest

from scene import agent, credits as credits_module, generation_models
from scene.comfy import workflows
from test_api import register

VIDEO, IMAGE = "video/generation_video", "image/generation_image"

# The generation server's list, as GET /generation/models gives it (a part of it).
LIVE = {
    "minimax_h3_max": {"id": "minimax_h3_max", "choice": "minimax_h3_max", "name": "MiniMax H3 Max", "seconds": {"min": 5, "max": 15},
                       "resolutions": [{"id": "480p", "credits_per_second": {"with_sound": 6}}], "frames": ["first", "last"],
                       "max_reference_images": 9, "sound": "always"},
    "wan_3_0": {"id": "wan_3.0", "choice": "wan_3_0", "name": "Wan 3.0", "seconds": {"min": 2, "max": 30},
                "resolutions": [{"id": "720p", "credits_per_second": {"with_sound": 20, "silent": 15}}], "frames": ["first", "last"],
                "max_reference_images": 4, "sound": "choice"},
    "kling_3_0_standard": {"id": "kling_3.0_standard", "choice": "kling_3_0_standard", "name": "Kling 3.0 Standard",
                           "seconds": {"min": 3, "max": 15}, "frames": ["first", "last"], "max_reference_images": 0},
}


def schema_of(workflow_id):
    root = workflows.Path(__file__).resolve().parents[2] / "workflows"
    return workflows.describe(workflows.load_workflow(root / (workflow_id + ".json"), None, workflow_id))


@pytest.fixture(scope="module")
def video():
    return schema_of(VIDEO)


@pytest.fixture(scope="module")
def image():
    return schema_of(IMAGE)


def settings(schema, prompt="A fox runs through snow.", **options):
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    return {"values": {roles["prompt"]["id"]: prompt}, "options": options, "refs": {}}


# ---------------------------------------------------------------- the two workflows


def test_the_video_workflow_holds_every_video_model(video):
    roles = {c["role"] for c in video["controls"] if c["role"]}
    assert {"prompt", "duration"} <= roles and video["chain"] and video["source"] == "generation"
    assert {"first_frame", "last_frame"} <= set(video["slots"])
    model = generation_models.model_option(video)
    assert len(model["choices"]) == 16 and model["default"] == "minimax_h3_max"
    assert {"seedance_2_5", "kling_4_0", "wan_3_0", "grok_imagine_video_1_5"} <= {c["id"] for c in model["choices"]}


def test_the_image_workflow_holds_every_picture_model(image):
    assert "prompt" in {c["role"] for c in image["controls"] if c["role"]} and image["source"] == "generation"
    assert len([r for r in image["refs"] if r.get("order")]) == 14 and not image["chain"]
    assert len(generation_models.model_option(image)["choices"]) == 11


def test_a_comfyui_workflow_is_no_model(client):
    schema = workflows.describe(asyncio.run(client.app.state.catalog.load("video/h3_all_in_one")))
    assert schema["source"] == "comfy" and generation_models.model_option(schema) is None and generation_models.catalog(schema) == []


@pytest.mark.parametrize("workflow_id, options, node_class, model, resolution, ratio", [
    (VIDEO, {}, "GenerationVideo", "minimax_h3_max", "480p", "16:9"),
    (VIDEO, {"model": "seedance_2_5", "resolution_1": "1080p", "shape_1": "r21x9"}, "GenerationVideo", "seedance_2_5", "1080p", "21:9"),
    (VIDEO, {"model": "kling_4_0", "resolution_5": "1080p", "shape_3": "r9x16"}, "GenerationVideo", "kling_4.0", "1080p", "9:16"),
    (VIDEO, {"model": "minimax_h3", "resolution_7": "2k", "shape_2": "r1x1"}, "GenerationVideo", "minimax_h3", "2k", "1:1"),
    (IMAGE, {"model": "nano_banana_pro", "resolution_1": "4K", "shape_1": "r3x4"}, "GenerationImage", "nano-banana-pro", "4K", "3:4"),
])
def test_a_model_builds_its_own_graph(workflow_id, options, node_class, model, resolution, ratio):
    schema = schema_of(workflow_id)
    wf = workflows.load_workflow(workflows.Path(__file__).resolve().parents[2] / "workflows" / (workflow_id + ".json"), None, workflow_id)
    prompt, _ = workflows.build_prompt(wf, settings(schema, **options))
    node = next(n for n in prompt.values() if n["class_type"] == node_class)
    assert re.sub(r"\W", "_", node["inputs"]["model"]) == re.sub(r"\W", "_", model)   # the provider's id: kling_4.0
    assert node["inputs"]["resolution"] == resolution and node["inputs"]["aspect_ratio"] == ratio


# ---------------------------------------------------------------- only the options shown for the model


def test_the_summary_names_the_model_and_only_its_own_settings(video):
    ctx = workflows.context(video, settings(video))
    assert workflows.summary(video, ctx) == "MiniMax H3 Max · 480p · 16:9 · 5 s" and ctx["resolution"] == "480p"
    ctx = workflows.context(video, settings(video, model="wan_3_0", resolution_1="720p", sound="off"))
    assert workflows.summary(video, ctx) == "Wan 3.0 · 720p · 16:9 · Silent · 5 s" and ctx["resolution"] == "720p"


def test_the_agent_sees_one_model_setting_and_one_of_each_other(video):
    found = agent.choosable_settings(video)
    assert [f["setting"] for f in found] == ["model", "resolution", "shape", "sound"]
    assert found[0]["default"] == "minimax_h3_max" and found[1]["default"] == "480p"
    offer = agent.offer(dict(video, models=generation_models.catalog(video, LIVE)))
    assert offer["source"] == "generation server" and len(offer["models"]) == 16
    wan = next(m for m in offer["models"] if m["model"] == "wan_3_0")
    assert wan["seconds"] == {"min": 2, "max": 30} and wan["references"] == 4 and "720p" in wan["resolutions"]
    assert len(next(m for m in offer["models"] if m["model"] == "seedance_2_5")["about"]) > 110   # a hint is not cut at 110


def test_a_setting_by_its_label_is_the_option_shown_for_the_chosen_model(video):
    job = {"options": {}, "values": {}}
    agent.apply_choices(video, job, [{"setting": "resolution", "value": "1080p"}, {"setting": "shape", "value": "21:9"},
                                     {"setting": "model", "value": "Kling 4"}])   # the model first, whatever the order
    assert job["options"] == {"model": "kling_4_0", "resolution_5": "1080p", "shape_3": "r21x9"}
    job = {"options": {}, "values": {}}
    agent.apply_choices(video, job, [{"setting": "model", "value": "seedance_2_5"}, {"setting": "Sound", "value": "Silent"}])
    assert job["options"] == {"model": "seedance_2_5", "sound": "off"}


def test_a_planned_shot_keeps_to_its_models_lengths_and_shape(video):
    step = {"tool": "generate", "workflow": VIDEO, "prompt": "A fox runs a long way through deep snow.", "duration": 25,
            "orientation": "portrait", "choices": [{"setting": "model", "value": "wan_3_0"}]}
    with_list = dict(video, models=generation_models.catalog(video, LIVE))
    made, _ = agent.settings_for(with_list, step, set(), None)
    assert made["options"]["model"] == "wan_3_0" and made["values"]["2:value"] == 25   # Wan 3.0 takes up to 30 s
    assert made["options"]["shape_1"] == "r9x16"   # portrait, in the model's own Shape
    made, _ = agent.settings_for(video, step, set(), None)   # no list: the agent's own bounds
    assert made["values"]["2:value"] == agent.SHOT_SECONDS[1]
    made, _ = agent.settings_for(with_list, dict(step, duration=40), set(), None)
    assert made["values"]["2:value"] == 30


def test_the_two_lists_are_never_mixed(client, video):
    comfy = agent.offer(workflows.describe(asyncio.run(client.app.state.catalog.load("video/h3_all_in_one"))))
    models = agent.offer(video)
    text = agent.workflows_part([comfy, models], [comfy, models])
    workflows_at, models_at = text.index("Workflows (ComfyUI"), text.index("Models (the generation server")
    assert workflows_at < text.index('"video/h3_all_in_one"') < models_at < text.index('"' + VIDEO + '"')


# ---------------------------------------------------------------- the generation server's list


def test_the_list_adds_lengths_references_and_prices(video):
    found = {m["model"]: m for m in generation_models.catalog(video, LIVE)}
    assert found["minimax_h3_max"]["seconds"] == {"min": 5, "max": 15} and found["minimax_h3_max"]["prices"] == {"480p": 6}
    assert found["kling_3_0_standard"]["references"] == 0
    assert "seconds" not in generation_models.catalog(video)[0]   # without the list: the presets file alone
    assert found["seedance_2_5"]["resolutions"] == ["480p", "720p", "1080p"] and found["seedance_2_5"]["sound"] == "choice"


def test_what_a_model_cant_take_is_said_before_the_job_is_sent(video):
    job = settings(video, model="minimax_h3_max")
    job["values"]["2:value"] = 20
    assert "5 to 15 seconds" in generation_models.problem(video, job, LIVE)
    assert generation_models.problem(video, job, None) == ""   # no list: the generation server says it
    kling = settings(video, model="kling_3_0_standard")
    kling["refs"] = {"ref_1": {"comfy_name": "a.png"}}
    assert "takes no reference pictures" in generation_models.problem(video, kling, LIVE)
    wan = settings(video, model="wan_3_0")
    wan["refs"] = {"ref_{}".format(n): {"comfy_name": "a.png"} for n in range(1, 6)}
    assert "at most 4 reference pictures" in generation_models.problem(video, wan, LIVE)
    wan["refs"] = {"ref_1": {"comfy_name": "a.png"}}
    assert generation_models.problem(video, wan, LIVE) == ""


def test_the_job_route_refuses_what_the_model_cant_take(client, monkeypatch):
    register(client)
    client.app.state.jobs.pause(True)

    async def live(workflow_id):
        return LIVE
    monkeypatch.setattr(client.app.state.generation_models, "live", live)
    body = {"workflow": VIDEO, "values": {"1:value": "A fox runs.", "2:value": 20}, "options": {"model": "minimax_h3_max"}}
    answer = client.post("/api/jobs", data={"settings": json.dumps(body)})
    assert answer.status_code == 400 and "5 to 15 seconds" in answer.json()["detail"]
    body["values"]["2:value"] = 10
    assert client.post("/api/jobs", data={"settings": json.dumps(body)}).status_code == 200
    models = client.get("/api/generation/models").json()["models"]
    assert set(models) == {VIDEO, IMAGE} and next(m for m in models[VIDEO] if m["model"] == "wan_3_0")["seconds"]["max"] == 30


def test_an_unreadable_list_breaks_nothing(client):
    """No generation server is set up in a test: the list is None and the presets file alone is used."""
    register(client)
    assert asyncio.run(client.app.state.generation_models.live(VIDEO)) is None
    models = client.get("/api/generation/models").json()["models"]
    assert len(models[VIDEO]) == 16 and len(models[IMAGE]) == 11


# ---------------------------------------------------------------- the price


def test_a_model_is_priced_at_the_consoles_price_for_its_resolution(client, video):
    credits = client.app.state.credits
    ctx = workflows.context(video, settings(video, model="wan_3_0", resolution_1="720p"))
    usual = credits.cost(VIDEO, 10, ctx)
    credits.set_model_prices(VIDEO, {"wan_3_0": {"720p": 3, "1080p": ""}, "seedance_2_5": {}})
    assert credits.model_prices(VIDEO) == {"wan_3_0": {"720p": 3.0}}
    assert credits.cost(VIDEO, 10, ctx) == 30   # 3 credits a second
    other = workflows.context(video, settings(video, model="wan_3_0", resolution_1="1080p"))
    assert credits.cost(VIDEO, 10, other) != 30 and usual != 30   # no price there: the workflow's own rate
    credits.set_model_prices(IMAGE, {"nano_banana_pro": {"4K": 18}})
    assert credits.cost(IMAGE, None, {"model": "nano_banana_pro", "resolution": "4K"}) == 18   # a picture's price
    assert credits_module.PER_JOB == ("image",)


def test_the_console_prices_each_model(client):
    from test_api import console
    register(client)
    desk = console(client)
    answer = desk.put("/api/admin/pricing/models", json={"workflow": VIDEO, "prices": {"kling_4_0": {"720p": 9}}})
    assert answer.status_code == 200
    row = next(w for w in answer.json()["workflows"] if w["id"] == VIDEO)
    assert row["model_prices"] == {"kling_4_0": {"720p": 9.0}} and len(row["models"]) == 16
    desk.put("/api/admin/pricing/workflow/factors", json={"workflow": VIDEO, "quality": {"high": 1.2}})
    assert client.app.state.credits.model_prices(VIDEO) == {"kling_4_0": {"720p": 9.0}}   # its own factors kept them
    assert desk.put("/api/admin/pricing/models", json={"workflow": "video/h3_all_in_one", "prices": {}}).status_code == 400


SOLO = ("audio/generation_speech", "audio/generation_music", "audio/generation_sound_effect", "video/generation_lipsync",
        "upscaler/generation_upscale")


def test_the_generation_servers_single_model_tools_are_models_too_with_no_model_setting():
    for workflow_id in SOLO:
        schema = schema_of(workflow_id)
        assert schema["source"] == "generation" and not generation_models.has_models(schema), workflow_id
        assert generation_models.catalog(schema) == [] and generation_models.problem(schema, {"options": {}}, LIVE) == ""
        offer = agent.offer(schema)
        assert offer["source"] == "generation server" and "models" not in offer, workflow_id
    speech = schema_of("audio/generation_speech")
    assert [s["setting"] for s in agent.choosable_settings(speech)][:2] == ["voice", "language"]
    # its words read by the labels, not the provider's ids
    words = workflows.summary(speech, workflows.context(speech, {"values": {}, "options": {}}))
    assert "Ashford Maid" in words and "v_vcl" not in words
    lipsync, upscale = schema_of("video/generation_lipsync"), schema_of("upscaler/generation_upscale")
    assert [r["label"] for r in lipsync["refs"] if r.get("required")] == ["Video with ONE clearly visible speaker",
                                                                          "Voice track: the voiceover to speak"]
    assert [r["label"] for r in upscale["refs"] if r.get("required")] == ["Video to upscale"]
    # the agent lists them with the models, never with ComfyUI's workflows
    offers = [agent.offer(schema_of(w)) for w in ("video/h3_all_in_one", *SOLO)]
    comfy, models = agent.workflows_part(offers, offers).split("\n\nModels (", 1)
    assert "generation_" not in comfy and all(w in models for w in SOLO)


def test_a_chat_pinned_to_models_offers_only_those(video):
    schema = dict(video, models=generation_models.catalog(video))
    kept = generation_models.only_models(schema, ["kling_4_0", "seedance_2_5"])
    model = generation_models.model_option(kept)
    assert [c["id"] for c in model["choices"]] == [c for c in (c["id"] for c in generation_models.model_option(video)["choices"])
                                                   if c in ("kling_4_0", "seedance_2_5")]   # the workflow's order
    assert model["default"] in ("kling_4_0", "seedance_2_5") and {m["model"] for m in kept["models"]} == {"kling_4_0", "seedance_2_5"}
    assert len(generation_models.model_option(video)["choices"]) == 16   # the catalog's own schema is left as it was
    assert generation_models.only_models(schema, ["no_such_model"]) is schema
    # the agent can't choose another one: a step's choice of an unpinned model keeps the pinned default
    settings = {"values": {}, "options": {o["id"]: o["default"] for o in kept["options"]}}
    agent.apply_choices(kept, settings, [{"setting": "model", "value": "minimax_h3_max"}])
    assert settings["options"]["model"] == model["default"]


def test_only_seedance_takes_a_frame_and_references_together(video):
    first = video["slots"]["first_frame"]
    h3 = {"model": "minimax_h3_max"}
    assert generation_models.clashes(video, h3, {first, "ref_1"})
    assert not generation_models.clashes(video, h3, {first}) and not generation_models.clashes(video, h3, {"ref_1", "ref_2"})
    assert not generation_models.clashes(video, {"model": "seedance_2_5"}, {first, "ref_1"})
    refused = generation_models.problem(video, {"options": h3, "refs": {first: {}, "ref_1": {}}}, None)
    assert refused.startswith("MiniMax H3 Max can't combine a first or last frame with reference images")
    assert "starts fresh from its references" in generation_models.clash_note(video, h3)


def test_a_planned_shot_that_would_clash_starts_fresh_when_it_is_queued(client):
    """A plan made before the studio knew: its MiniMax shot that goes on from the one before and has the cast's
    pictures is queued without the frame (and waits for nothing)."""
    runner = client.app.state.plans
    first = schema_of(VIDEO)["slots"]["first_frame"]
    settings = {"workflow": VIDEO, "options": {"model": "minimax_h3_max"}, "refs": {"ref_1": {"comfy_name": "a.png"}}}
    after = {"after": {"step": 0, "slot": first}}
    assert asyncio.run(runner._frame_clashes(after, settings))
    assert not asyncio.run(runner._frame_clashes(after, dict(settings, refs={})))
    assert not asyncio.run(runner._frame_clashes(after, dict(settings, options={"model": "seedance_2_5"})))
