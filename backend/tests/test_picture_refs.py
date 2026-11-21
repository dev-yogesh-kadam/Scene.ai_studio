"""Picture references of the providers' models (providers/workflows.py): a model's list of reference pictures becomes
the presets' list of references (ref_1, ref_2 ...), a job sends exactly the references given, in order and with no gaps
(an empty one is never sent), and the prompt's names for them and the count the list shows come from the model."""

import pytest

from studio_models import MODELS
from scene.comfy import workflows
from scene.providers.workflows import build, provider_input

USER = {"name": "Ada", "email": "ada@example.com", "password": "correct horse"}
WITH_REFS = {"nano_banana_pro": 6, "seedance_2_5": 9}   # model: the most reference pictures it takes
WORDS_ONLY = ["seedream_5", "kling_4_0"]
PROMPT = "2:value"


def load(model_id):
    model = next(m for m in MODELS if m["id"] == model_id)
    return build(dict(model, model_id=model_id))


def send(wf, refs):
    graph, _ = workflows.build_prompt(wf, {"workflow": wf["id"], "values": {PROMPT: "a test"}, "options": {}, "refs": refs})
    return provider_input(wf, graph)


@pytest.mark.parametrize("model_id", list(WITH_REFS))
def test_a_job_carries_exactly_the_references_given(model_id):
    most = WITH_REFS[model_id]
    wf = load(model_id)
    schema = workflows.describe(wf)
    listed = [r for r in schema["refs"] if r["kind"] == "image" and r.get("order")]
    assert [r["id"] for r in listed] == ["ref_{}".format(n) for n in range(1, most + 1)]
    assert not any(r.get("required") for r in listed)
    for count in (0, 1, most):
        given = {"ref_{}".format(n): {"comfy_name": "ref{}.png".format(n), "name": "r"} for n in range(1, count + 1)}
        sent = send(wf, given)
        if count:
            assert sent["reference_images"] == [{"file": "ref{}.png".format(n), "kind": "image"} for n in range(1, count + 1)]
        else:
            assert "reference_images" not in sent   # an empty reference is never sent


def test_the_prompt_names_each_reference_as_the_model_does():
    naming = workflows.describe(load("nano_banana_pro"))["ref_naming"]
    assert naming["tokens"] == ["image {}".format(n) for n in range(1, 7)] and naming["unique"]


def test_a_list_of_references_is_sent_with_no_gaps():
    """Files given in boxes 1 and 3 go in as the first and the second."""
    sent = send(load("nano_banana_pro"), {"ref_1": {"comfy_name": "a.png"}, "ref_3": {"comfy_name": "c.png"}})
    assert sent["reference_images"] == [{"file": "a.png", "kind": "image"}, {"file": "c.png", "kind": "image"}]


def test_a_first_frame_is_its_own_slot_beside_the_references():
    wf = load("seedance_2_5")
    schema = workflows.describe(wf)
    first = schema["slots"]["first_frame"]
    sent = send(wf, {first: {"comfy_name": "f.png"}, "ref_2": {"comfy_name": "b.png"}})
    assert sent["first_frame"] == {"file": "f.png", "kind": "image"}
    assert sent["reference_images"] == [{"file": "b.png", "kind": "image"}]
    assert "last_frame" not in sent


@pytest.mark.parametrize("model_id", WORDS_ONLY)
def test_a_model_with_no_reference_list_has_no_references(model_id):
    schema = workflows.describe(load(model_id))
    assert not [r for r in schema["refs"] if r.get("order")] and schema["ref_naming"]["tokens"] == []


def test_a_required_file_must_be_given():
    with pytest.raises(workflows.WorkflowError, match="Add a file"):
        workflows.build_prompt(load("lip_sync"), {"workflow": "video/@lip_sync", "values": {}, "options": {}, "refs": {}})


def test_the_list_says_how_many_pictures_each_model_takes(client):
    client.post("/api/auth/register", json=USER)
    listed = {w["id"]: w for w in client.get("/api/workflows").json()["workflows"]}
    assert listed["image/@nano_banana_pro"]["picture_refs"] == 6
    assert listed["video/@seedance_2_5"]["picture_refs"] == 9 + 2   # its references, and its first and last frame
    assert listed["video/@kling_4_0"]["picture_refs"] == 1          # a first frame only
    assert listed["image/@seedream_5"]["picture_refs"] == 0
